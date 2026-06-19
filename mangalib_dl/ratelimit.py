"""Защита от лимитов: токен-бакет + разбор Retry-After + GET с ретраями."""
from __future__ import annotations

import asyncio
import email.utils
import time

import httpx

from . import config


class RateLimiter:
    """Асинхронный токен-бакет: не более `rate` запросов в секунду (с burst)."""

    def __init__(self, rate: float, capacity: float | None = None):
        self.rate = max(0.1, rate)
        self.capacity = capacity if capacity is not None else max(1.0, rate)
        self._tokens = self.capacity
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self._tokens = min(
                self.capacity, self._tokens + (now - self._updated) * self.rate
            )
            self._updated = now
            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) / self.rate
                await asyncio.sleep(wait)
                self._tokens = 0.0
                self._updated = time.monotonic()
            else:
                self._tokens -= 1.0


def parse_retry_after(value: str | None) -> float | None:
    """Разбирает заголовок Retry-After (секунды или HTTP-дата)."""
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return min(float(value), config.MAX_RETRY_AFTER)
    try:
        dt = email.utils.parsedate_to_datetime(value)
        if dt is not None:
            delta = dt.timestamp() - time.time()
            return min(max(0.0, delta), config.MAX_RETRY_AFTER)
    except (TypeError, ValueError):
        pass
    return None


async def request_with_retries(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    limiter: RateLimiter | None = None,
    params: dict | None = None,
    on_throttle=None,
) -> httpx.Response:
    """GET/POST с уважением лимитов: токен-бакет, ретраи, 429/Retry-After.

    on_throttle(seconds, attempt) — необязательный колбэк для логов UI.
    """
    last_exc: Exception | None = None
    for attempt in range(config.MAX_RETRIES):
        if limiter is not None:
            await limiter.acquire()
        try:
            resp = await client.request(method, url, params=params)
            if resp.status_code in config.RETRY_STATUS:
                retry_after = parse_retry_after(resp.headers.get("Retry-After"))
                # Если сервер не подсказал — экспоненциальная пауза.
                wait = retry_after if retry_after is not None else (
                    config.RETRY_BACKOFF ** attempt
                )
                if resp.status_code == 429 and retry_after is None:
                    wait = max(wait, 5.0)  # 429 без подсказки — подождём подольше
                if on_throttle:
                    on_throttle(wait, attempt)
                if attempt < config.MAX_RETRIES - 1:
                    await asyncio.sleep(wait)
                    continue
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as e:
            last_exc = e
            if e.response.status_code not in config.RETRY_STATUS:
                raise
            if attempt < config.MAX_RETRIES - 1:
                await asyncio.sleep(config.RETRY_BACKOFF ** attempt)
        except (httpx.TransportError, httpx.TimeoutException) as e:
            last_exc = e
            if attempt < config.MAX_RETRIES - 1:
                await asyncio.sleep(config.RETRY_BACKOFF ** attempt)
    raise RuntimeError(f"Запрос не удался после {config.MAX_RETRIES} попыток: "
                       f"{url} :: {last_exc}")

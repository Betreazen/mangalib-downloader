"""Скачивание страниц из абсолютных URL (мультисорс-путь).

Отдельно от ChapterDownloader: тот заточен под CDN MangaLib (относительные
пути + список серверов), а источники отдают уже готовые ссылки с нужными
заголовками (Referer и т.п.). Логику формата/конвертации переиспользуем.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable

import httpx

from .. import config
from ..downloader import _detect_ext
from ..packager import safe_name
from ..ratelimit import RateLimiter, request_with_retries
from .base import ChapterInfo, PageInfo

ProgressCb = Callable[[int, int, str], None]


async def download_chapter_pages(
    pages: list[PageInfo],
    chapter_dir: Path,
    *,
    concurrency: int = config.MAX_CONCURRENT_DOWNLOADS,
    rate_rps: float = config.IMAGE_RATE_RPS,
    progress: ProgressCb | None = None,
    on_throttle=None,
) -> int:
    """Качает страницы в chapter_dir/original. Возвращает число сохранённых."""
    original_dir = chapter_dir / "original"
    original_dir.mkdir(parents=True, exist_ok=True)

    limiter = RateLimiter(rate_rps)
    sem = asyncio.Semaphore(concurrency)
    total = len(pages)
    done = 0
    lock = asyncio.Lock()

    async with httpx.AsyncClient(
        timeout=config.REQUEST_TIMEOUT, follow_redirects=True
    ) as http:
        async def worker(p: PageInfo) -> None:
            nonlocal done
            async with sem:
                resp = await request_with_retries(
                    http, "GET", p.url,
                    limiter=limiter, headers=p.headers or None, on_throttle=on_throttle,
                )
                data = resp.content
                if data:
                    ext = _detect_ext(data)
                    await asyncio.to_thread(
                        (original_dir / f"{p.index:03d}.{ext}").write_bytes, data
                    )
            async with lock:
                done += 1
                if progress:
                    progress(done, total, f"Страница {done}/{total}")

        await asyncio.gather(*(worker(p) for p in pages))
    return done


def chapter_dirname(ch: ChapterInfo) -> str:
    return safe_name(ch.label)

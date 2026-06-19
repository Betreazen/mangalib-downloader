"""Скачивание страниц главы: оригиналы + конвертация, с параллелизмом."""
from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx
from PIL import Image

from . import config
from .api import MangaLibClient
from .models import Page
from .ratelimit import RateLimiter, request_with_retries

# Pillow 12 умеет AVIF нативно; этот импорт регистрирует плагин, если он есть.
try:  # pragma: no cover - просто на случай старого Pillow
    import pillow_avif  # noqa: F401
except Exception:  # noqa: BLE001
    pass


ProgressCb = Callable[[int, int, str], None]  # (done, total, message)


def _detect_ext(data: bytes) -> str:
    """Определяет реальное расширение по сигнатуре файла."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in (b"avif", b"avis"):
        return "avif"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return "bin"


@dataclass
class DownloadResult:
    chapter_dir: Path
    original_dir: Path
    converted_dir: Path | None
    page_count: int


class ChapterDownloader:
    def __init__(
        self,
        client: MangaLibClient,
        convert: bool = True,
        convert_format: str = config.CONVERT_FORMAT,
        concurrency: int = config.MAX_CONCURRENT_DOWNLOADS,
        rate_rps: float = config.IMAGE_RATE_RPS,
        limiter: RateLimiter | None = None,
        on_throttle=None,
    ):
        self.client = client
        self.convert = convert
        self.convert_format = convert_format
        self.concurrency = concurrency
        self.limiter = limiter or RateLimiter(rate_rps)
        self.on_throttle = on_throttle

    async def _fetch_page(
        self, page: Page, servers: list[str], http: httpx.AsyncClient
    ) -> bytes:
        last_exc: Exception | None = None
        # Перебираем CDN-серверы; на каждом — ретраи с уважением 429/Retry-After.
        for server in servers:
            url = MangaLibClient.build_image_url(server, page)
            try:
                resp = await request_with_retries(
                    http, "GET", url,
                    limiter=self.limiter, on_throttle=self.on_throttle,
                )
                if resp.content:
                    return resp.content
                last_exc = RuntimeError("пустой ответ")
            except Exception as e:  # noqa: BLE001
                last_exc = e
        raise RuntimeError(f"Не удалось скачать страницу {page.index}: {last_exc}")

    def _save_page(self, data: bytes, original_dir: Path, converted_dir: Path | None,
                   index: int) -> None:
        ext = _detect_ext(data)
        stem = f"{index:03d}"
        (original_dir / f"{stem}.{ext}").write_bytes(data)

        if converted_dir is not None:
            out_ext = "jpg" if self.convert_format.upper() in ("JPEG", "JPG") else "png"
            try:
                with Image.open(io.BytesIO(data)) as im:
                    if self.convert_format.upper() in ("JPEG", "JPG"):
                        im = im.convert("RGB")
                        im.save(converted_dir / f"{stem}.{out_ext}",
                                quality=config.CONVERT_QUALITY)
                    else:
                        im.save(converted_dir / f"{stem}.{out_ext}")
            except Exception:  # noqa: BLE001
                # Если конвертация не удалась — кладём оригинал в папку converted.
                (converted_dir / f"{stem}.{ext}").write_bytes(data)

    async def download_pages(
        self,
        pages: list[Page],
        chapter_dir: Path,
        progress: ProgressCb | None = None,
    ) -> DownloadResult:
        servers = await self.client.get_image_servers()
        original_dir = chapter_dir / "original"
        original_dir.mkdir(parents=True, exist_ok=True)
        converted_dir = None
        if self.convert:
            converted_dir = chapter_dir / "converted"
            converted_dir.mkdir(parents=True, exist_ok=True)

        total = len(pages)
        done = 0
        lock = asyncio.Lock()
        sem = asyncio.Semaphore(self.concurrency)

        # Отдельный http-клиент с браузерными заголовками для CDN картинок.
        async with httpx.AsyncClient(
            headers=config.DEFAULT_HEADERS,
            timeout=config.REQUEST_TIMEOUT,
            follow_redirects=True,
        ) as http:
            async def worker(page: Page) -> None:
                nonlocal done
                async with sem:
                    data = await self._fetch_page(page, servers, http)
                    # запись/конвертация в отдельном потоке, чтобы не блокировать loop
                    await asyncio.to_thread(
                        self._save_page, data, original_dir, converted_dir, page.index
                    )
                async with lock:
                    done += 1
                    if progress:
                        progress(done, total, f"Страница {done}/{total}")

            await asyncio.gather(*(worker(p) for p in pages))

        return DownloadResult(
            chapter_dir=chapter_dir,
            original_dir=original_dir,
            converted_dir=converted_dir,
            page_count=total,
        )

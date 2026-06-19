"""Асинхронный клиент публичного API MangaLib."""
from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from . import config
from .models import Chapter, Manga, Page
from .ratelimit import RateLimiter, request_with_retries


class MangaLibError(Exception):
    pass


class LicensedTitleError(MangaLibError):
    """Главы скрыты в публичном API (лицензия/18+) — нужен токен авторизации."""


class LockedChapterError(MangaLibError):
    """Платная глава (ранний доступ): требует покупки/подписки."""

    def __init__(self, message: str, price=None, expired_at=None):
        super().__init__(message)
        self.price = price
        self.expired_at = expired_at


class UnreleasedChapterError(MangaLibError):
    """Глава ещё не опубликована (publish_at в будущем)."""

    def __init__(self, message: str, publish_at=None):
        super().__init__(message)
        self.publish_at = publish_at


def _is_future_iso(value) -> bool:
    if not value:
        return False
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.timestamp() > datetime.now(timezone.utc).timestamp()
    except (ValueError, TypeError):
        return False


def parse_slug(url_or_slug: str) -> str:
    """Достаёт slug манги из ссылки читалки или принимает готовый slug.

    Поддерживает:
      https://mangalib.me/ru/247--shingeki-no-kyojin/read/v1/c1?bid=1
      https://mangalib.me/ru/manga/206--one-piece
      206--one-piece
    """
    s = url_or_slug.strip()
    if "://" not in s and "/" not in s:
        return s
    path = urlparse(s).path
    parts = [p for p in path.split("/") if p]
    # Ищем сегмент вида "<id>--<name>" (slug всегда начинается с числового id).
    for p in parts:
        if re.match(r"^\d+--", p):
            return p
    # запасной вариант: сегмент после 'manga' или языкового кода
    if "manga" in parts:
        i = parts.index("manga")
        if i + 1 < len(parts):
            return parts[i + 1]
    raise MangaLibError(f"Не удалось извлечь slug из: {url_or_slug}")


def parse_reader_url(url: str) -> dict:
    """Из ссылки-читалки достаёт slug, том, главу и branch_id (bid), если есть.

    Пример: .../247--shingeki-no-kyojin/read/v1/c1?bid=1 ->
        {slug, volume:'1', number:'1', branch_id:1}
    """
    parsed = urlparse(url)
    result: dict = {"slug": parse_slug(url), "volume": None, "number": None, "branch_id": None}
    m = re.search(r"/read/v([\d.]+)/c([\d.]+)", parsed.path)
    if m:
        result["volume"] = m.group(1)
        result["number"] = m.group(2)
    m = re.search(r"[?&]bid=(\d+)", url)
    if m:
        result["branch_id"] = int(m.group(1))
    return result


class MangaLibClient:
    def __init__(
        self,
        auth_token: str | None = None,
        rate_rps: float = config.API_RATE_RPS,
        on_throttle=None,
    ):
        headers = dict(config.DEFAULT_HEADERS)
        if auth_token:
            # JWT не содержит пробелов/переносов — вычищаем их (частая ошибка
            # копирования), кроме одного пробела после "Bearer".
            token = auth_token.strip()
            if token.lower().startswith("bearer "):
                token = "Bearer " + "".join(token[7:].split())
            else:
                token = "Bearer " + "".join(token.split())
            headers["Authorization"] = token
        self._client = httpx.AsyncClient(
            headers=headers,
            timeout=config.REQUEST_TIMEOUT,
            follow_redirects=True,
        )
        self.limiter = RateLimiter(rate_rps)
        self.on_throttle = on_throttle
        self._image_servers: list[str] | None = None

    async def __aenter__(self) -> "MangaLibClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get_json(self, url: str, params: dict | None = None) -> dict:
        try:
            resp = await request_with_retries(
                self._client, "GET", url,
                limiter=self.limiter, params=params, on_throttle=self.on_throttle,
            )
            return resp.json()
        except Exception as e:  # noqa: BLE001
            raise MangaLibError(f"Запрос не удался: {url} :: {e}")

    # ---- метаданные и главы ----

    async def get_manga(self, slug: str) -> Manga:
        data = await self._get_json(f"{config.API_BASE}/manga/{slug}")
        return Manga.from_api(slug, data)

    async def get_catalog(
        self,
        page: int = 1,
        *,
        query: str | None = None,
        types: list[int] | None = None,
        sort_by: str | None = None,
        sort_type: str = "desc",
        seed: str | None = None,
    ) -> tuple[list[dict], bool, str | None]:
        """Страница каталога. «Бесконечный скролл» на сайте — это просто page=1,2,3…

        Возвращает (items, has_next_page, seed). seed стоит передавать на
        следующих страницах, чтобы сохранить тот же порядок выдачи.
        """
        params: dict = {"site_id[]": [config.SITE_ID], "page": page,
                        "fields[]": ["rate_avg", "rate", "releaseDate"]}
        if query:
            params["q"] = query
        if types:
            params["types[]"] = types
        if sort_by:
            params["sort_by"] = sort_by
            params["sort_type"] = sort_type
        if seed:
            params["seed"] = seed
        data = await self._get_json(f"{config.API_BASE}/manga", params)
        meta = data.get("meta") or {}
        return (data.get("data") or [],
                bool(meta.get("has_next_page")),
                meta.get("seed"))

    async def get_chapters(self, slug: str) -> list[Chapter]:
        data = await self._get_json(f"{config.API_BASE}/manga/{slug}/chapters")
        items = data.get("data")
        if not isinstance(items, list):
            raise MangaLibError(f"Неожиданный ответ для глав: {slug}")
        if not items:
            raise LicensedTitleError(
                "Список глав пуст. Скорее всего тайтл лицензирован или 18+ — "
                "укажите токен авторизации из вашего аккаунта."
            )
        chapters: list[Chapter] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            try:
                chapters.append(Chapter.from_api(it))
            except Exception:  # noqa: BLE001 — пропускаем единичные битые записи
                continue
        return chapters

    async def get_chapter_detail(
        self,
        slug: str,
        volume: str | int,
        number: str | int,
        branch_id: int | None = None,
    ) -> dict:
        params: dict = {"number": str(number), "volume": str(volume)}
        if branch_id is not None:
            params["branch_id"] = branch_id
        data = await self._get_json(f"{config.API_BASE}/manga/{slug}/chapter", params)
        return data.get("data") or {}

    async def get_pages(
        self,
        slug: str,
        volume: str | int,
        number: str | int,
        branch_id: int | None = None,
    ) -> list[Page]:
        d = await self.get_chapter_detail(slug, volume, number, branch_id)
        pages_raw = d.get("pages") or []
        pages: list[Page] = []
        for i, p in enumerate(pages_raw, start=1):
            pages.append(
                Page(
                    index=i,
                    url_path=p.get("url", ""),
                    width=int(p.get("width") or 0),
                    height=int(p.get("height") or 0),
                )
            )
        if pages:
            return pages

        # Страниц нет — выясняем причину для понятного сообщения.
        if _is_future_iso(d.get("publish_at")):
            raise UnreleasedChapterError(
                f"Глава ещё не вышла (публикация {d.get('publish_at')}).",
                publish_at=d.get("publish_at"),
            )
        rv = d.get("restricted_view")
        is_locked = d.get("expired_type") == 1 or (
            isinstance(rv, dict) and not rv.get("is_open", True)
        )
        if is_locked:
            price = rv.get("price") if isinstance(rv, dict) else None
            expired_at = rv.get("expired_at") if isinstance(rv, dict) else d.get("expired_at")
            raise LockedChapterError(
                f"Платная глава (ранний доступ){f', цена {price}' if price else ''}"
                f"{f', открыта до {expired_at}' if expired_at else ''}.",
                price=price, expired_at=expired_at,
            )
        raise MangaLibError("В главе нет страниц (возможно, требуется токен).")

    # ---- серверы картинок ----

    async def get_image_servers(self) -> list[str]:
        if self._image_servers is not None:
            return self._image_servers
        servers: list[str] = []
        try:
            data = await self._get_json(
                f"{config.API_BASE}/constants", {"fields[]": "imageServers"}
            )
            for s in (data.get("data") or {}).get("imageServers", []):
                if config.SITE_ID in (s.get("site_ids") or []):
                    url = (s.get("url") or "").rstrip("/")
                    if url and url not in servers:
                        servers.append(url)
        except Exception:  # noqa: BLE001
            pass
        for fb in config.FALLBACK_IMAGE_SERVERS:
            if fb not in servers:
                servers.append(fb)
        self._image_servers = servers
        return servers

    @staticmethod
    def build_image_url(server: str, page: Page) -> str:
        return server.rstrip("/") + "/" + page.url_path.lstrip("/")

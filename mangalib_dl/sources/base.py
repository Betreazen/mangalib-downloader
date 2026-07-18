"""Базовые типы мультисорс-ядра: единый интерфейс источника манги.

Каждый сайт — это подкласс MangaSource с тремя обязательными методами:
search / get_chapters / get_pages. Всё остальное (агрегация, скачивание,
выбор лучшего источника) работает поверх этого интерфейса и не знает
о деталях конкретного сайта.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field

import httpx

from .. import config
from ..ratelimit import request_with_retries


class SourceError(Exception):
    """Ошибка источника (сеть, парсинг, недоступность)."""


class AuthRequiredError(SourceError):
    """Источник требует токен авторизации для этого действия."""


@dataclass
class SearchResult:
    """Найденный тайтл на конкретном сайте."""
    source_id: str                  # id источника из реестра ("remanga", ...)
    manga_id: str                   # внутренний id/slug тайтла на сайте
    title: str
    alt_titles: list[str] = field(default_factory=list)
    url: str = ""                   # страница тайтла в браузере
    cover: str = ""
    chapters_count: int | None = None   # если сайт отдаёт сразу в поиске
    extra: dict = field(default_factory=dict)  # прочее для адаптера

    @property
    def all_titles(self) -> list[str]:
        return [self.title, *self.alt_titles]


@dataclass
class ChapterInfo:
    """Глава тайтла в терминах источника."""
    chapter_id: str                 # внутренний id (или "vol/num")
    volume: str = ""
    number: str = ""
    name: str = ""
    team: str = ""                  # команда перевода, если известна
    branch_id: str | None = None    # ветка перевода, если сайт их различает

    @property
    def label(self) -> str:
        base = f"Том {self.volume} Глава {self.number}" if self.volume else f"Глава {self.number}"
        return f"{base} — {self.name}" if self.name else base


@dataclass
class PageInfo:
    """Страница главы: абсолютный URL + заголовки для скачивания."""
    index: int
    url: str
    headers: dict[str, str] = field(default_factory=dict)  # напр. Referer


class MangaSource(abc.ABC):
    """Абстрактный источник. Подклассы задают id/name/base_url и три метода."""

    id: str = ""
    name: str = ""
    base_url: str = ""
    lang: str = "ru"
    can_download: bool = True       # False = только метаданные (Shikimori)
    # Статус реализации: "verified" | "unverified" | "stub"
    status: str = "verified"
    notes: str = ""

    def __init__(self, token: str | None = None):
        self.token = token
        self._client: httpx.AsyncClient | None = None

    # ---- служебное ----

    def _headers(self) -> dict[str, str]:
        h = {
            "User-Agent": config.DEFAULT_HEADERS["User-Agent"],
            "Accept": "application/json, text/plain, */*",
        }
        if self.token:
            t = self.token.strip()
            h["Authorization"] = t if t.lower().startswith("bearer ") else f"Bearer {t}"
        return h

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers=self._headers(),
                timeout=config.REQUEST_TIMEOUT,
                follow_redirects=True,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.aclose()

    async def _get_json(self, url: str, params: dict | None = None):
        try:
            r = await request_with_retries(self.client, "GET", url, params=params)
            return r.json()
        except (httpx.HTTPError, ValueError, RuntimeError) as e:
            raise SourceError(f"{self.name}: запрос не удался: {url} :: {e}") from e

    async def _get_text(self, url: str, params: dict | None = None) -> str:
        try:
            r = await request_with_retries(self.client, "GET", url, params=params)
            return r.text
        except (httpx.HTTPError, RuntimeError) as e:
            raise SourceError(f"{self.name}: запрос не удался: {url} :: {e}") from e

    # ---- обязательный интерфейс ----

    @abc.abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Поиск тайтлов по названию."""

    @abc.abstractmethod
    async def get_chapters(self, manga_id: str) -> list[ChapterInfo]:
        """Полный список глав тайтла (все ветки перевода)."""

    @abc.abstractmethod
    async def get_pages(self, manga_id: str, chapter: ChapterInfo) -> list[PageInfo]:
        """Страницы конкретной главы (абсолютные URL картинок)."""

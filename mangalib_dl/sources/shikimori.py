"""Адаптер shikimori.one — база метаданных (без страниц-картинок).

Shikimori не хостит сканы: это каталог с рейтингами и числом глав. Полезен
как источник эталонного «сколько всего глав в тайтле», но не для скачивания.
"""
from __future__ import annotations

from .base import ChapterInfo, MangaSource, PageInfo, SearchResult

API = "https://shikimori.one/api"


class ShikimoriSource(MangaSource):
    id = "shikimori"
    name = "Shikimori"
    base_url = "https://shikimori.one"
    can_download = False
    notes = "Только метаданные (рейтинг, число глав). Сканы не хостятся."

    def _headers(self):
        h = super()._headers()
        # Shikimori требует осмысленный User-Agent приложения.
        h["User-Agent"] = "MangaAggregator/1.0"
        return h

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        data = await self._get_json(
            f"{API}/mangas", params={"search": query, "limit": limit}
        )
        out: list[SearchResult] = []
        for m in data[:limit]:
            img = m.get("image") or {}
            out.append(SearchResult(
                source_id=self.id,
                manga_id=str(m["id"]),
                title=m.get("russian") or m.get("name") or str(m["id"]),
                alt_titles=[m["name"]] if m.get("name") else [],
                url=self.base_url + m.get("url", ""),
                cover=self.base_url + (img.get("original") or ""),
                chapters_count=m.get("chapters") or None,
            ))
        return out

    async def get_chapters(self, manga_id: str) -> list[ChapterInfo]:
        # Число глав известно, но самих глав/страниц нет.
        return []

    async def get_pages(self, manga_id: str, chapter: ChapterInfo) -> list[PageInfo]:
        return []

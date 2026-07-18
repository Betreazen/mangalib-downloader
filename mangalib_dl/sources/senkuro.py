"""Адаптер senkuro.com (GraphQL API, Tachiyomi-совместимый срез).

Три запроса: mangaTachiyomiSearch -> mangaTachiyomiChapters ->
mangaTachiyomiChapterPages. Ветки перевода Senkuro в этом срезе не отдаёт —
главы приходят единым списком.
"""
from __future__ import annotations

import httpx

from .base import ChapterInfo, MangaSource, PageInfo, SearchResult, SourceError

GQL = "https://api.senkuro.com/graphql"

_SEARCH = """query($q:String!){mangaTachiyomiSearch(query:$q){mangas{id slug titles{lang content}}}}"""
_CHAPTERS = """query($m:ID!){mangaTachiyomiChapters(mangaId:$m){chapters{id name number volume}}}"""
_PAGES = """query($m:ID!,$c:ID!){mangaTachiyomiChapterPages(mangaId:$m,chapterId:$c){pages{url}}}"""


class SenkuroSource(MangaSource):
    id = "senkuro"
    name = "Senkuro"
    base_url = "https://senkuro.com"

    async def _gql(self, query: str, variables: dict) -> dict:
        try:
            r = await self.client.post(GQL, json={"query": query, "variables": variables})
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise SourceError(f"{self.name}: GraphQL запрос не удался :: {e}") from e
        if data.get("errors"):
            raise SourceError(f"{self.name}: {data['errors'][0].get('message')}")
        return data.get("data") or {}

    @staticmethod
    def _pick_title(titles: list[dict]) -> tuple[str, list[str]]:
        by_lang = {t.get("lang"): t.get("content") for t in titles if t.get("content")}
        main = by_lang.get("RU") or by_lang.get("EN") or next(iter(by_lang.values()), "")
        alts = [v for v in by_lang.values() if v and v != main]
        return main, alts

    async def search(self, query: str, limit: int = 10):
        data = await self._gql(_SEARCH, {"q": query})
        out = []
        for m in (data.get("mangaTachiyomiSearch") or {}).get("mangas", [])[:limit]:
            title, alts = self._pick_title(m.get("titles") or [])
            slug = m.get("slug", "")
            out.append(SearchResult(
                source_id=self.id, manga_id=m["id"], title=title or slug,
                alt_titles=alts, url=f"{self.base_url}/manga/{slug}",
            ))
        return out

    async def get_chapters(self, manga_id: str) -> list[ChapterInfo]:
        data = await self._gql(_CHAPTERS, {"m": manga_id})
        chs = (data.get("mangaTachiyomiChapters") or {}).get("chapters", [])
        return [
            ChapterInfo(
                chapter_id=c["id"],
                volume=str(c.get("volume") or ""),
                number=str(c.get("number") or ""),
                name=(c.get("name") or "").strip(),
            )
            for c in chs
        ]

    async def get_pages(self, manga_id: str, chapter: ChapterInfo) -> list[PageInfo]:
        data = await self._gql(_PAGES, {"m": manga_id, "c": chapter.chapter_id})
        pages = (data.get("mangaTachiyomiChapterPages") or {}).get("pages", [])
        return [
            PageInfo(index=i, url=p["url"]) for i, p in enumerate(pages, start=1) if p.get("url")
        ]

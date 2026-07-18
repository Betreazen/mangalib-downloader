"""Адаптер mangadex.org (официальный публичный REST API api.mangadex.org).

Документация стабильна и хорошо известна; из некоторых сетей хост отдаёт
заглушку (гео/прокси-блок), поэтому статус помечен как unverified —
логика написана по спецификации API v5.
"""
from __future__ import annotations

from .base import ChapterInfo, MangaSource, PageInfo, SearchResult

API = "https://api.mangadex.org"


class MangaDexSource(MangaSource):
    id = "mangadex"
    name = "MangaDex"
    base_url = "https://mangadex.org"
    lang = "en"
    status = "unverified"
    notes = "Из некоторых сетей API отдаёт HTML-заглушку; проверить на своей сети."

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        data = await self._get_json(
            f"{API}/manga",
            params={"title": query, "limit": min(limit, 10)},
        )
        out: list[SearchResult] = []
        for m in data.get("data", [])[:limit]:
            attr = m.get("attributes", {})
            titles = attr.get("title", {})
            main = titles.get("en") or next(iter(titles.values()), m["id"])
            alts = [next(iter(a.values())) for a in attr.get("altTitles", []) if a]
            out.append(SearchResult(
                source_id=self.id, manga_id=m["id"], title=main,
                alt_titles=alts[:5], url=f"{self.base_url}/title/{m['id']}",
            ))
        return out

    async def get_chapters(self, manga_id: str) -> list[ChapterInfo]:
        out: list[ChapterInfo] = []
        offset = 0
        while True:
            data = await self._get_json(
                f"{API}/manga/{manga_id}/feed",
                params={"limit": 500, "offset": offset,
                        "translatedLanguage[]": ["ru", "en"],
                        "order[chapter]": "asc",
                        "includes[]": ["scanlation_group"]},
            )
            items = data.get("data", [])
            for c in items:
                attr = c.get("attributes", {})
                team = ""
                for rel in c.get("relationships", []):
                    if rel.get("type") == "scanlation_group":
                        team = (rel.get("attributes") or {}).get("name", "")
                        break
                out.append(ChapterInfo(
                    chapter_id=c["id"],
                    volume=str(attr.get("volume") or ""),
                    number=str(attr.get("chapter") or ""),
                    name=(attr.get("title") or "").strip(),
                    team=team,
                    branch_id=attr.get("translatedLanguage"),
                ))
            if len(items) < 500:
                break
            offset += 500
        return out

    async def get_pages(self, manga_id: str, chapter: ChapterInfo) -> list[PageInfo]:
        at = await self._get_json(f"{API}/at-home/server/{chapter.chapter_id}")
        base = at["baseUrl"]
        ch = at["chapter"]
        h = ch["hash"]
        return [
            PageInfo(index=i, url=f"{base}/data/{h}/{fname}")
            for i, fname in enumerate(ch.get("data", []), start=1)
        ]

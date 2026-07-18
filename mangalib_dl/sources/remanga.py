"""Адаптер remanga.org (публичный JSON API api.remanga.org).

Поток: search -> titles/{dir} -> ветки (branches) -> titles/chapters?branch_id
-> titles/chapters/{id} (страницы). Тайтл различает ветки по издателю.
"""
from __future__ import annotations

from .base import ChapterInfo, MangaSource, PageInfo, SearchResult

API = "https://api.remanga.org/api"
IMG_CDN = "https://remanga.org"


class ReMangaSource(MangaSource):
    id = "remanga"
    name = "ReManga"
    base_url = "https://remanga.org"

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        data = await self._get_json(f"{API}/search/", params={"query": query, "count": limit})
        out: list[SearchResult] = []
        for it in (data.get("content") or [])[:limit]:
            cover = ""
            c = it.get("cover")
            if isinstance(c, dict):
                cover = IMG_CDN + (c.get("high") or c.get("mid") or c.get("low") or "")
            out.append(SearchResult(
                source_id=self.id,
                manga_id=it.get("dir", ""),
                title=it.get("main_name") or it.get("secondary_name") or it.get("dir", ""),
                alt_titles=[x for x in (it.get("secondary_name"),) if x],
                url=f"{self.base_url}/manga/{it.get('dir', '')}",
                cover=cover,
                chapters_count=it.get("count_chapters"),
            ))
        return out

    async def get_chapters(self, manga_id: str) -> list[ChapterInfo]:
        detail = await self._get_json(f"{API}/titles/{manga_id}/")
        content = detail.get("content") or {}
        out: list[ChapterInfo] = []
        for br in content.get("branches") or []:
            bid = br.get("id")
            team = ", ".join(p.get("name", "") for p in (br.get("publishers") or []) if p.get("name"))
            page = 1
            while True:
                chs = await self._get_json(
                    f"{API}/titles/chapters/",
                    params={"branch_id": bid, "count": 100, "page": page},
                )
                items = chs.get("content") or []
                if not items:
                    break
                for ch in items:
                    out.append(ChapterInfo(
                        chapter_id=str(ch.get("id")),
                        volume=str(ch.get("tome", "")),
                        number=str(ch.get("chapter", "")),
                        name=(ch.get("name") or "").strip(),
                        team=team,
                        branch_id=str(bid),
                    ))
                if len(items) < 100:
                    break
                page += 1
        return out

    async def get_pages(self, manga_id: str, chapter: ChapterInfo) -> list[PageInfo]:
        data = await self._get_json(f"{API}/titles/chapters/{chapter.chapter_id}/")
        content = data.get("content") or {}
        # pages бывает плоским списком или списком списков (развороты).
        raw = content.get("pages") or []
        flat: list[dict] = []
        for item in raw:
            if isinstance(item, list):
                flat.extend(item)
            elif isinstance(item, dict):
                flat.append(item)
        return [
            PageInfo(index=i, url=p.get("link", ""),
                     headers={"Referer": self.base_url + "/"})
            for i, p in enumerate(flat, start=1) if p.get("link")
        ]

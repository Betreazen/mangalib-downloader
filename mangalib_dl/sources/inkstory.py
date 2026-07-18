"""Адаптер inkstory.net / manga.ovh (общий API api.inkstory.net, срез v2).

Поток: /v2/books?search -> /v2/branches?bookId -> /v2/chapters?bookId
-> /v2/chapters/{id} (pages). Ветки — по издателю (publisher).
"""
from __future__ import annotations

from .base import ChapterInfo, MangaSource, PageInfo, SearchResult

API = "https://api.inkstory.net/v2"


class InkStorySource(MangaSource):
    id = "inkstory"
    name = "InkStory / manga.ovh"
    base_url = "https://inkstory.net"

    @staticmethod
    def _name(book: dict) -> tuple[str, list[str]]:
        n = book.get("name")
        if isinstance(n, dict):
            main = n.get("ru") or n.get("en") or n.get("original") or book.get("slug", "")
            alts = [v for v in (n.get("en"), n.get("original")) if v and v != main]
            return main, alts
        return (n or book.get("slug", "")), []

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        books = await self._get_json(f"{API}/books", params={"search": query})
        out: list[SearchResult] = []
        for b in (books or [])[:limit]:
            title, alts = self._name(b)
            out.append(SearchResult(
                source_id=self.id,
                manga_id=b["slug"],
                title=title,
                alt_titles=alts,
                url=f"{self.base_url}/book/{b['slug']}",
                cover=b.get("poster", ""),
                extra={"book_uuid": b["id"]},
            ))
        return out

    async def _book_uuid(self, manga_id: str) -> str:
        # manga_id может быть уже uuid или slug — если slug, резолвим в uuid.
        if "-" in manga_id and len(manga_id) == 36:
            return manga_id
        book = await self._get_json(f"{API}/books/{manga_id}")
        return book["id"]

    async def get_chapters(self, manga_id: str) -> list[ChapterInfo]:
        uuid = await self._book_uuid(manga_id)
        branches = await self._get_json(f"{API}/branches", params={"bookId": uuid})
        team_by_branch = {
            b["id"]: ", ".join(p.get("name", "") for p in (b.get("publishers") or []) if p.get("name"))
            for b in (branches or [])
        }
        chs = await self._get_json(f"{API}/chapters", params={"bookId": uuid})
        out: list[ChapterInfo] = []
        for c in chs or []:
            out.append(ChapterInfo(
                chapter_id=c["id"],
                volume=str(int(c["volume"])) if c.get("volume") is not None else "",
                number=_num(c.get("number")),
                name=(c.get("name") or "").strip(),
                team=team_by_branch.get(c.get("branchId"), ""),
                branch_id=c.get("branchId"),
            ))
        return out

    async def get_pages(self, manga_id: str, chapter: ChapterInfo) -> list[PageInfo]:
        ch = await self._get_json(f"{API}/chapters/{chapter.chapter_id}")
        pages = ch.get("pages") or []
        return [
            PageInfo(index=p.get("index", i) + 1, url=p["image"])
            for i, p in enumerate(pages) if p.get("image")
        ]


def _num(v) -> str:
    if v is None:
        return ""
    f = float(v)
    return str(int(f)) if f.is_integer() else str(f)

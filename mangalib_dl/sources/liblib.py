"""Адаптер семейства *Lib (MangaLib/YaoiLib/HentaiLib/RanobeLib/AnimeLib).

Все они делят один API-хост api.cdnlibs.org и различаются только site_id и
доменом читалки. Поэтому переиспользуем готовый MangaLibClient, а не пишем
парсинг заново — он уже умеет ветки перевода, платные/невышедшие главы и CDN.
"""
from __future__ import annotations

from ..api import LicensedTitleError, MangaLibClient
from .base import ChapterInfo, MangaSource, PageInfo, SearchResult

# Единый API для всего семейства.
LIB_API_BASE = "https://api.cdnlibs.org/api"


class _LibSource(MangaSource):
    site_id: int = 1
    reader_url: str = "https://mangalib.me"

    def __init__(self, token: str | None = None):
        super().__init__(token)
        self._api = MangaLibClient(
            auth_token=token, api_base=LIB_API_BASE, site_id=self.site_id
        )

    async def aclose(self) -> None:
        await self._api.aclose()

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        items, _, _ = await self._api.get_catalog(page=1, query=query)
        out: list[SearchResult] = []
        for it in items[:limit]:
            slug = it.get("slug_url") or it.get("slug") or str(it.get("id", ""))
            alts = [x for x in (it.get("name"), it.get("eng_name")) if x]
            cover = ""
            c = it.get("cover")
            if isinstance(c, dict):
                cover = c.get("default") or c.get("thumbnail") or ""
            out.append(SearchResult(
                source_id=self.id,
                manga_id=slug,
                title=it.get("rus_name") or it.get("name") or slug,
                alt_titles=alts,
                url=f"{self.reader_url}/ru/manga/{slug}",
                cover=cover,
                extra={"items_count": it.get("items_count")},
            ))
        return out

    async def get_chapters(self, manga_id: str) -> list[ChapterInfo]:
        chapters = await self._api.get_chapters(manga_id)
        out: list[ChapterInfo] = []
        for ch in chapters:
            for br in ch.branches:
                out.append(ChapterInfo(
                    chapter_id=f"{ch.volume}/{ch.number}",
                    volume=ch.volume,
                    number=ch.number,
                    name=ch.name,
                    team=br.team_label,
                    branch_id=str(br.branch_id) if br.branch_id is not None else None,
                ))
        return out

    async def get_pages(self, manga_id: str, chapter: ChapterInfo) -> list[PageInfo]:
        bid = int(chapter.branch_id) if chapter.branch_id else None
        pages = await self._api.get_pages(manga_id, chapter.volume, chapter.number, bid)
        servers = await self._api.get_image_servers()
        server = servers[0] if servers else ""
        return [
            PageInfo(index=p.index, url=MangaLibClient.build_image_url(server, p))
            for p in pages
        ]


class MangaLibSource(_LibSource):
    id = "mangalib"
    name = "MangaLib"
    base_url = "https://mangalib.me"
    site_id = 1
    reader_url = "https://mangalib.me"


class YaoiLibSource(_LibSource):
    id = "yaoilib"
    name = "YaoiLib / SlashLib"
    base_url = "https://v2.slashlib.me"
    site_id = 2
    reader_url = "https://v2.slashlib.me"


class RanobeLibSource(_LibSource):
    id = "ranobelib"
    name = "RanobeLib"
    base_url = "https://ranobelib.me"
    site_id = 3
    reader_url = "https://ranobelib.me"
    notes = "Ранобэ: главы текстовые, скачивание страниц-картинок неприменимо."
    can_download = False


class HentaiLibSource(_LibSource):
    id = "hentailib"
    name = "HentaiLib"
    base_url = "https://hentailib.me"
    site_id = 4
    reader_url = "https://hentailib.me"
    notes = "18+: почти всё требует токен авторизации."


class AnimeLibSource(_LibSource):
    id = "animelib"
    name = "AnimeLib"
    base_url = "https://anilib.me"
    site_id = 5
    reader_url = "https://anilib.me"
    can_download = False
    notes = "Аниме (видео), не манга — только метаданные/поиск."

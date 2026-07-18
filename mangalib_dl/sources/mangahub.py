"""Адаптер mangahub.ru — без публичного JSON API, парсим HTML.

Поиск: /suggestions?query — HTML-подсказки со ссылками /title/<slug>.
Главы: /title/<slug>/chapters — строки со ссылкой /read/<id> и «Том/Глава».
Страницы: /read/<id> — картинки в data-src.

Скрапинг хрупкий по своей природе: при смене вёрстки регулярки могут
перестать ловить. Помечен verified, но требует присмотра.
"""
from __future__ import annotations

import re

from .base import ChapterInfo, MangaSource, PageInfo, SearchResult

_TITLE_RE = re.compile(r'href="/title/([^"/]+)"[^>]*>', re.I)
_TITLE_NAME_RE = re.compile(r'href="/title/([^"/]+)"[^>]*>\s*(?:<[^>]+>\s*)*([^<]{2,120})', re.I)
_ROW_RE = re.compile(
    r'href="/read/(\d+)"[^>]*>(?:(?!/read/).)*?Том\s*([\d.]+)(?:(?!/read/).)*?Глава\s*([\d.]+)',
    re.I | re.S,
)
_IMG_RE = re.compile(r'data-src="(//[^"]+\.(?:png|jpe?g|webp)[^"]*)"', re.I)


class MangaHubSource(MangaSource):
    id = "mangahub"
    name = "MangaHub.ru"
    base_url = "https://mangahub.ru"
    notes = "HTML-скрапинг (нет JSON API); хрупко к смене вёрстки."

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        html = await self._get_text(
            f"{self.base_url}/suggestions", params={"query": query}
        )
        seen: set[str] = set()
        out: list[SearchResult] = []
        for m in _TITLE_NAME_RE.finditer(html):
            slug, name = m.group(1), m.group(2).strip()
            if slug in seen:
                continue
            seen.add(slug)
            out.append(SearchResult(
                source_id=self.id, manga_id=slug, title=name or slug,
                url=f"{self.base_url}/title/{slug}",
            ))
            if len(out) >= limit:
                break
        return out

    async def get_chapters(self, manga_id: str) -> list[ChapterInfo]:
        html = await self._get_text(f"{self.base_url}/title/{manga_id}/chapters")
        out: list[ChapterInfo] = []
        for m in _ROW_RE.finditer(html):
            read_id, volume, number = m.group(1), m.group(2), m.group(3)
            out.append(ChapterInfo(
                chapter_id=read_id, volume=volume, number=number,
            ))
        # На сайте главы идут сверху вниз (свежие первыми) — вернём по возрастанию.
        out.reverse()
        return out

    async def get_pages(self, manga_id: str, chapter: ChapterInfo) -> list[PageInfo]:
        html = await self._get_text(f"{self.base_url}/read/{chapter.chapter_id}")
        urls = _IMG_RE.findall(html)
        return [
            PageInfo(index=i, url="https:" + u, headers={"Referer": self.base_url + "/"})
            for i, u in enumerate(urls, start=1)
        ]

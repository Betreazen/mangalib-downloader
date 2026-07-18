"""Заглушки источников: сайты из ТЗ, для которых адаптер ещё не написан.

Они видны в реестре и UI (со статусом "stub" и заметкой, что выяснено при
разведке), но их методы поднимают SourceError. Так список сайтов честно
отражает ТЗ, а реализация добавляется по одному без правки реестра.
"""
from __future__ import annotations

from .base import ChapterInfo, MangaSource, PageInfo, SearchResult, SourceError


class _Stub(MangaSource):
    status = "stub"

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        raise SourceError(f"{self.name}: адаптер ещё не реализован ({self.notes})")

    async def get_chapters(self, manga_id: str) -> list[ChapterInfo]:
        raise SourceError(f"{self.name}: адаптер ещё не реализован")

    async def get_pages(self, manga_id: str, chapter: ChapterInfo) -> list[PageInfo]:
        raise SourceError(f"{self.name}: адаптер ещё не реализован")


class ReadmangaSource(_Stub):
    id = "readmanga"
    name = "ReadManga / MintManga"
    base_url = "https://readmanga.live"
    notes = "GroupLE-движок; /search/suggestion отдаёт 404, нужен разбор HTML каталога."


class MangaBuffSource(_Stub):
    id = "mangabuff"
    name = "MangaBuff"
    base_url = "https://mangabuff.ru"
    notes = "HTML-скрапинг; карточки грузятся JS, поиск /search?q — цель для парсера."


class NewMangaSource(_Stub):
    id = "newmanga"
    name = "NewManga (Zenmanga)"
    base_url = "https://newmanga.org"
    notes = "API-хост (api/neo.newmanga.org) из этой сети недоступен (502)."


class DesuSource(_Stub):
    id = "desu"
    name = "Desu.me"
    base_url = "https://desu.me"
    notes = "Домен desu.me из этой сети недоступен (502); есть JSON API /manga/api/."


class MangaPoiskSource(_Stub):
    id = "mangapoisk"
    name = "MangaPoisk"
    base_url = "https://mangapoisk.live"
    notes = "Из этой сети недоступен (502)."


class ComXSource(_Stub):
    id = "comx"
    name = "Com-x.life"
    base_url = "https://com-x.life"
    notes = "DLE-движок с антибот-редиректом (_c?t=...); нужен обход cookie-челленджа."


class MangaPlusSource(_Stub):
    id = "mangaplus"
    name = "MANGA Plus (Shueisha)"
    base_url = "https://mangaplus.shueisha.co.jp"
    notes = "Protobuf API; из этой сети аккаунт/IP забанен. Нужен свой IP + protobuf-разбор."


class WebtoonsSource(_Stub):
    id = "webtoons"
    name = "WEBTOON"
    base_url = "https://www.webtoons.com"
    notes = "HTML-скрапинг доступен; изображения требуют Referer webtoons при скачивании."


STUB_SOURCES: list[type[MangaSource]] = [
    ReadmangaSource,
    MangaBuffSource,
    NewMangaSource,
    DesuSource,
    MangaPoiskSource,
    ComXSource,
    MangaPlusSource,
    WebtoonsSource,
]

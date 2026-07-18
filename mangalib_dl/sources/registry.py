"""Реестр источников: единая точка «какие сайты умеем и как их создать».

Даёт переключение между ядрами: по id получаем класс источника и создаём
экземпляр (с токеном при необходимости). Агрегатор ходит сюда, а не знает
про конкретные модули.
"""
from __future__ import annotations

from .base import MangaSource
from .inkstory import InkStorySource
from .liblib import (
    AnimeLibSource,
    HentaiLibSource,
    MangaLibSource,
    RanobeLibSource,
    YaoiLibSource,
)
from .mangadex import MangaDexSource
from .mangahub import MangaHubSource
from .remanga import ReMangaSource
from .senkuro import SenkuroSource
from .shikimori import ShikimoriSource
from .stubs import STUB_SOURCES

# Порядок = приоритет по умолчанию в поиске/агрегации.
_ALL: list[type[MangaSource]] = [
    MangaLibSource,
    ReMangaSource,
    SenkuroSource,
    InkStorySource,
    MangaHubSource,
    MangaDexSource,
    YaoiLibSource,
    HentaiLibSource,
    ShikimoriSource,
    RanobeLibSource,
    AnimeLibSource,
    *STUB_SOURCES,
]

_BY_ID: dict[str, type[MangaSource]] = {cls.id: cls for cls in _ALL}


def all_source_ids(*, downloadable_only: bool = False) -> list[str]:
    return [
        cls.id for cls in _ALL
        if not downloadable_only or (cls.can_download and cls.status != "stub")
    ]


def source_meta() -> list[dict]:
    """Сводка по всем источникам для UI/документации."""
    return [
        {"id": c.id, "name": c.name, "base_url": c.base_url, "lang": c.lang,
         "can_download": c.can_download, "status": c.status, "notes": c.notes}
        for c in _ALL
    ]


def get_source_class(source_id: str) -> type[MangaSource]:
    if source_id not in _BY_ID:
        raise KeyError(f"Неизвестный источник: {source_id}")
    return _BY_ID[source_id]


def create_source(source_id: str, token: str | None = None) -> MangaSource:
    return get_source_class(source_id)(token=token)

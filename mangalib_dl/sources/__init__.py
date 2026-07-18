"""Мультисорс-ядро: единый интерфейс к разным сайтам-источникам манги.

Публичный API пакета:
    from mangalib_dl.sources import Aggregator, create_source, source_meta
"""
from .aggregator import Aggregator, AggregatedTitle, SourceMatch, normalize_title
from .base import (
    AuthRequiredError,
    ChapterInfo,
    MangaSource,
    PageInfo,
    SearchResult,
    SourceError,
)
from .registry import all_source_ids, create_source, get_source_class, source_meta

__all__ = [
    "Aggregator", "AggregatedTitle", "SourceMatch", "normalize_title",
    "MangaSource", "SearchResult", "ChapterInfo", "PageInfo",
    "SourceError", "AuthRequiredError",
    "all_source_ids", "create_source", "get_source_class", "source_meta",
]

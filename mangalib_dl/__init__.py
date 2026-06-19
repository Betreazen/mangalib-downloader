"""Загрузчик глав манги с MangaLib через публичный JSON API."""
from .api import (
    LicensedTitleError,
    LockedChapterError,
    MangaLibClient,
    MangaLibError,
    UnreleasedChapterError,
    parse_reader_url,
    parse_slug,
)
from .models import Branch, Chapter, Manga, Page
from .service import (
    BranchOption,
    DownloadOptions,
    DownloadReport,
    DownloadService,
    list_branches,
)
from . import storage

__all__ = [
    "MangaLibClient",
    "MangaLibError",
    "LicensedTitleError",
    "LockedChapterError",
    "UnreleasedChapterError",
    "parse_slug",
    "parse_reader_url",
    "Manga",
    "Chapter",
    "Branch",
    "Page",
    "DownloadService",
    "DownloadOptions",
    "DownloadReport",
    "BranchOption",
    "list_branches",
    "storage",
]

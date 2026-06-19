"""Загрузчик глав манги с MangaLib через публичный JSON API.

Ядро библиотеки не зависит от GUI: импорт `mangalib_dl` НЕ тянет PySide6.
Графический интерфейс лежит в `mangalib_dl.gui` (требует extra `[gui]`).
"""
__version__ = "0.1.0"

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
    "__version__",
]

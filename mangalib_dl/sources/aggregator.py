"""Агрегатор: поиск по всем сайтам сразу и выбор самого актуального источника.

Сценарий из ТЗ: пользователь ищет тайтл -> ищем по всем доступным сайтам ->
группируем результаты одного и того же тайтла -> для скачивания берём тот
сайт, где глав больше всего (самый актуальный перевод/выпуск).
"""
from __future__ import annotations

import asyncio
import re
import unicodedata
from dataclasses import dataclass, field

from .base import ChapterInfo, MangaSource, SearchResult, SourceError
from .registry import all_source_ids, create_source


@dataclass
class SourceMatch:
    """Один тайтл на одном сайте + фактическое число глав (после уточнения)."""
    result: SearchResult
    chapters_count: int | None = None   # None = ещё не уточняли

    @property
    def source_id(self) -> str:
        return self.result.source_id


@dataclass
class AggregatedTitle:
    """Один и тот же тайтл, найденный на нескольких сайтах."""
    key_title: str
    matches: list[SourceMatch] = field(default_factory=list)

    @property
    def best(self) -> SourceMatch:
        """Источник с наибольшим числом глав — для скачивания."""
        return max(self.matches, key=lambda m: (m.chapters_count or 0))

    @property
    def total_chapters(self) -> int:
        return max((m.chapters_count or 0) for m in self.matches)

    def sorted_matches(self) -> list[SourceMatch]:
        return sorted(self.matches, key=lambda m: -(m.chapters_count or 0))


def normalize_title(s: str) -> str:
    """Ключ для сопоставления тайтлов между сайтами: латиница/кириллица,
    без пунктуации, регистра и лишних пробелов."""
    s = unicodedata.normalize("NFKD", s).lower()
    s = re.sub(r"[^0-9a-zа-яё]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _titles_match(a: SearchResult, b: SearchResult) -> bool:
    # ponytail: сопоставление по полному совпадению любого из нормализованных
    # названий. Favors recall (лучше склеить лишнее, чем разбить один тайтл на
    # два). Ceiling: изредка склеивает разные тайтлы со схожими ромадзи
    # ("berserker"). Если станет мешать — добавить порог похожести (rapidfuzz).
    keys_a = {normalize_title(t) for t in a.all_titles if t}
    keys_b = {normalize_title(t) for t in b.all_titles if t}
    return bool(keys_a & keys_b)


class Aggregator:
    def __init__(self, tokens: dict[str, str] | None = None):
        """tokens: {source_id: bearer_token} для сайтов, где нужна авторизация.

        Если не переданы — подхватываем сохранённые токен-виндой (tokens.json).
        """
        if tokens is None:
            from .token_store import load_tokens
            tokens = load_tokens()
        self.tokens = tokens or {}

    def _make(self, source_id: str) -> MangaSource:
        return create_source(source_id, token=self.tokens.get(source_id))

    async def search_all(
        self,
        query: str,
        source_ids: list[str] | None = None,
        limit_per_source: int = 5,
        on_error=None,
    ) -> list[AggregatedTitle]:
        """Ищет по всем источникам параллельно и группирует одинаковые тайтлы."""
        ids = source_ids or all_source_ids(downloadable_only=True)

        async def one(sid: str) -> list[SearchResult]:
            src = self._make(sid)
            try:
                return await src.search(query, limit=limit_per_source)
            except SourceError as e:
                if on_error:
                    on_error(sid, str(e))
                return []
            except Exception as e:  # noqa: BLE001 — один сбойный сайт не валит поиск
                if on_error:
                    on_error(sid, repr(e))
                return []
            finally:
                await src.aclose()

        results = await asyncio.gather(*(one(sid) for sid in ids))
        flat = [r for group in results for r in group]
        return self._group(flat)

    @staticmethod
    def _group(results: list[SearchResult]) -> list[AggregatedTitle]:
        groups: list[AggregatedTitle] = []
        for r in results:
            placed = False
            for g in groups:
                if any(_titles_match(r, m.result) for m in g.matches):
                    g.matches.append(SourceMatch(result=r, chapters_count=r.chapters_count))
                    placed = True
                    break
            if not placed:
                groups.append(AggregatedTitle(
                    key_title=r.title,
                    matches=[SourceMatch(result=r, chapters_count=r.chapters_count)],
                ))
        return groups

    async def enrich_counts(
        self, title: AggregatedTitle, on_error=None
    ) -> AggregatedTitle:
        """Уточняет число глав там, где поиск его не отдал, — чтобы честно
        сравнить актуальность и выбрать best. Считаем уникальные номера глав
        (а не строки веток), иначе сайт с 3 переводами кажется «полнее»."""

        async def count(m: SourceMatch) -> None:
            if m.chapters_count is not None:
                return
            src = self._make(m.source_id)
            try:
                chapters = await src.get_chapters(m.result.manga_id)
                m.chapters_count = _unique_chapter_count(chapters)
            except Exception as e:  # noqa: BLE001
                if on_error:
                    on_error(m.source_id, repr(e))
                m.chapters_count = 0
            finally:
                await src.aclose()

        await asyncio.gather(*(count(m) for m in title.matches))
        return title


def _unique_chapter_count(chapters: list[ChapterInfo]) -> int:
    return len({(c.volume, c.number) for c in chapters})

"""Тесты агрегатора: нормализация, группировка, выбор лучшего источника.

Все офлайн — без сети (сетевые пути покрываются ручной проверкой CLI).
Запуск: pytest tests/test_aggregator.py
"""
from __future__ import annotations

from mangalib_dl.sources.aggregator import (
    AggregatedTitle,
    Aggregator,
    SourceMatch,
    normalize_title,
)
from mangalib_dl.sources.base import SearchResult


def sr(source_id: str, title: str, alts=None, chapters=None) -> SearchResult:
    return SearchResult(
        source_id=source_id, manga_id=title.lower(), title=title,
        alt_titles=alts or [], chapters_count=chapters,
    )


def test_normalize_strips_punctuation_and_case():
    assert normalize_title("Berserk!!!  ") == "berserk"
    assert normalize_title("Атака Титанов") == "атака титанов"
    assert normalize_title("One-Piece: Gold") == "one piece gold"


def test_group_merges_same_title_across_sources():
    results = [
        sr("mangalib", "Berserk", chapters=380),
        sr("senkuro", "Берсерк", alts=["Berserk"], chapters=390),
        sr("mangahub", "Naruto", chapters=700),
    ]
    groups = Aggregator._group(results)
    by_title = {g.key_title for g in groups}
    # Berserk и Берсерк(alt=Berserk) склеиваются в одну группу.
    assert len(groups) == 2
    berserk = next(g for g in groups if "erserk" in g.key_title or "ерсерк" in g.key_title)
    assert len(berserk.matches) == 2
    assert {"mangalib", "senkuro"} == {m.source_id for m in berserk.matches}


def test_best_picks_source_with_most_chapters():
    g = AggregatedTitle(
        key_title="Berserk",
        matches=[
            SourceMatch(sr("a", "Berserk"), chapters_count=50),
            SourceMatch(sr("b", "Berserk"), chapters_count=380),
            SourceMatch(sr("c", "Berserk"), chapters_count=200),
        ],
    )
    assert g.best.source_id == "b"
    assert g.total_chapters == 380
    # sorted_matches по убыванию глав
    assert [m.chapters_count for m in g.sorted_matches()] == [380, 200, 50]


def test_best_handles_unknown_counts():
    g = AggregatedTitle(
        key_title="X",
        matches=[SourceMatch(sr("a", "X"), None), SourceMatch(sr("b", "X"), 5)],
    )
    assert g.best.source_id == "b"


def test_no_match_keeps_titles_separate():
    groups = Aggregator._group([sr("a", "Naruto"), sr("b", "Bleach")])
    assert len(groups) == 2

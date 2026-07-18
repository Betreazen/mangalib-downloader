"""Мультисорс-CLI: поиск по всем сайтам, авто-выбор лучшего, скачивание.

    python -m mangalib_dl.sources.cli search "berserk"
    python -m mangalib_dl.sources.cli sources
    python -m mangalib_dl.sources.cli download "berserk" --out ./downloads

Реализует сценарий из ТЗ: ищем везде -> берём сайт с самым полным переводом
-> показываем чей перевод и сколько глав -> качаем оттуда.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from . import Aggregator, create_source, source_meta
from .download import chapter_dirname, download_chapter_pages


def _err(sid: str, msg: str) -> None:
    print(f"  · {sid}: {msg[:100]}", file=sys.stderr)


async def cmd_sources() -> None:
    print(f"{'ID':12} {'СТАТУС':10} {'DL':3} НАЗВАНИЕ")
    for m in source_meta():
        print(f"{m['id']:12} {m['status']:10} {('да' if m['can_download'] else '—'):3} {m['name']}")
        if m["notes"]:
            print(f"{'':12} └ {m['notes']}")


async def _resolve_best(agg: Aggregator, query: str):
    print(f"🔎 Ищу «{query}» по всем сайтам…")
    titles = await agg.search_all(query, limit_per_source=5, on_error=_err)
    if not titles:
        print("Ничего не найдено.")
        return None
    titles.sort(key=lambda t: -len(t.matches))
    top = titles[0]
    print(f"📚 «{top.key_title}» найдена на {len(top.matches)} сайт(ах). "
          f"Уточняю число глав…")
    await agg.enrich_counts(top, on_error=_err)
    return top


async def cmd_search(query: str) -> None:
    agg = Aggregator()
    top = await _resolve_best(agg, query)
    if not top:
        return
    for m in top.sorted_matches():
        mark = "⭐" if m is top.best else "  "
        team = m.result.extra.get("team", "")
        print(f"{mark} {m.source_id:11} {str(m.chapters_count):>4} гл.  {m.result.url}")
    best = top.best
    print(f"\n➡  Актуальнее всего: {best.source_id} — {best.chapters_count} глав.")


async def cmd_download(query: str, out: Path, limit: int | None) -> None:
    agg = Aggregator()
    top = await _resolve_best(agg, query)
    if not top:
        return
    best = top.best
    print(f"\n⬇  Качаю с {best.source_id} ({best.chapters_count} глав)…")
    src = create_source(best.source_id, token=agg.tokens.get(best.source_id))
    try:
        chapters = await src.get_chapters(best.result.manga_id)
        # уникальные главы по номеру, первая встретившаяся ветка
        seen: set[tuple[str, str]] = set()
        uniq = []
        for ch in chapters:
            key = (ch.volume, ch.number)
            if key not in seen:
                seen.add(key)
                uniq.append(ch)
        if limit:
            uniq = uniq[:limit]
        root = out / chapter_dirname_root(top.key_title) / best.source_id
        for i, ch in enumerate(uniq, start=1):
            pages = await src.get_pages(best.result.manga_id, ch)
            ch_dir = root / chapter_dirname(ch)
            n = await download_chapter_pages(pages, ch_dir)
            print(f"  [{i}/{len(uniq)}] {ch.label}: {n} стр. -> {ch_dir}")
    finally:
        await src.aclose()
    print(f"\n✅ Готово: {out}")


def chapter_dirname_root(title: str) -> str:
    from ..packager import safe_name
    return safe_name(title)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="mangalib_dl.sources", description="Мультисорс загрузчик манги")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sources", help="список источников")
    s = sub.add_parser("search", help="поиск и выбор лучшего источника")
    s.add_argument("query")
    d = sub.add_parser("download", help="скачать лучший источник")
    d.add_argument("query")
    d.add_argument("--out", type=Path, default=Path("downloads"))
    d.add_argument("--limit", type=int, default=None, help="макс. глав (для теста)")
    args = p.parse_args(argv)

    if args.cmd == "sources":
        asyncio.run(cmd_sources())
    elif args.cmd == "search":
        asyncio.run(cmd_search(args.query))
    elif args.cmd == "download":
        asyncio.run(cmd_download(args.query, args.out, args.limit))


if __name__ == "__main__":
    main()

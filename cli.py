"""Простой CLI для загрузчика MangaLib (и для проверки ядра).

Примеры:
    python cli.py info "https://mangalib.me/ru/manga/206--one-piece"
    python cli.py branches 7965--chainsaw-man
    python cli.py download 7965--chainsaw-man --chapters 1 --branch 4666 -o downloads
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from mangalib_dl import (
    DownloadOptions,
    DownloadService,
    MangaLibClient,
    MangaLibError,
    list_branches,
    parse_slug,
)


def _filter_chapters(chapters, spec: str | None):
    if not spec:
        return chapters
    wanted: set[str] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            try:
                for n in range(int(float(a)), int(float(b)) + 1):
                    wanted.add(str(n))
            except ValueError:
                wanted.add(part)
        else:
            wanted.add(part)
    return [c for c in chapters if c.number in wanted]


async def cmd_info(args) -> None:
    async with MangaLibClient(args.token) as client:
        slug = parse_slug(args.url)
        manga = await client.get_manga(slug)
        chapters = await client.get_chapters(slug)
        print(f"Тайтл: {manga.title}  ({slug})")
        print(f"Глав: {len(chapters)}")
        for c in chapters[:10]:
            teams = " | ".join(b.team_label for b in c.branches)
            print(f"  {c.label}   [{teams}]")
        if len(chapters) > 10:
            print(f"  … ещё {len(chapters) - 10}")


async def cmd_branches(args) -> None:
    async with MangaLibClient(args.token) as client:
        slug = parse_slug(args.url)
        chapters = await client.get_chapters(slug)
        for opt in list_branches(chapters):
            print(f"branch_id={opt.branch_id!s:<8} глав:{opt.chapter_count:<5} {opt.label}")


async def cmd_download(args) -> None:
    async with MangaLibClient(args.token) as client:
        slug = parse_slug(args.url)
        manga = await client.get_manga(slug)
        chapters = await client.get_chapters(slug)
        chapters = _filter_chapters(chapters, args.chapters)
        if not chapters:
            print("Нет глав по заданному фильтру.")
            return
        branch_label = "default"
        for opt in list_branches(chapters):
            if opt.branch_id == args.branch:
                branch_label = opt.teams_summary
                break

        options = DownloadOptions(
            output_root=Path(args.output),
            make_cbz_files=not args.no_cbz,
            convert=not args.no_convert,
        )
        service = DownloadService(client, options)

        def progress(msg, cd, ct, dp, tp):
            bar = f"[{cd}/{ct} глав]"
            if tp:
                bar += f" {dp}/{tp} стр."
            print(f"\r{bar} {msg[:60]:<60}", end="", flush=True)

        report = await service.download(
            manga, chapters, args.branch, branch_label, progress=progress
        )
        print()
        print(f"Готово: {report.chapters_done} глав, ошибок: {report.chapters_failed}")
        print(f"Папка: {report.output_dir}")
        for err in report.errors:
            print("  !", err)


def main() -> None:
    p = argparse.ArgumentParser(description="MangaLib downloader")
    p.add_argument("--token", help="Bearer-токен (для лицензированных/18+)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("info", help="инфо о тайтле")
    pi.add_argument("url")
    pi.set_defaults(func=cmd_info)

    pb = sub.add_parser("branches", help="список переводов")
    pb.add_argument("url")
    pb.set_defaults(func=cmd_branches)

    pd = sub.add_parser("download", help="скачать главы")
    pd.add_argument("url")
    pd.add_argument("--chapters", help="напр. 1 или 1-5 или 1,3,7")
    pd.add_argument("--branch", type=int, default=None, help="branch_id перевода")
    pd.add_argument("-o", "--output", default="downloads")
    pd.add_argument("--no-cbz", action="store_true")
    pd.add_argument("--no-convert", action="store_true")
    pd.set_defaults(func=cmd_download)

    args = p.parse_args()
    try:
        asyncio.run(args.func(args))
    except MangaLibError as e:
        print(f"\nОшибка: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

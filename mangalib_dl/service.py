"""Высокоуровневая оркестрация: скачать выбранные главы выбранного перевода."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import config
from .api import (
    LockedChapterError,
    MangaLibClient,
    UnreleasedChapterError,
)
from .downloader import ChapterDownloader
from .models import Branch, Chapter, Manga
from .packager import make_cbz, safe_name
from .ratelimit import RateLimiter

# (текст события, done_chapters, total_chapters, done_pages, total_pages)
ProgressFn = Callable[[str, int, int, int, int], None]


@dataclass
class BranchOption:
    """Уникальный перевод (ветка) в рамках тайтла — для выпадающего списка.

    Идентичность перевода — это branch_id. Команды (teams) внутри одной
    ветки могут меняться от главы к главе и/или отсутствовать, поэтому здесь
    хранится сводка всех встретившихся команд, а не одна подпись.
    """
    branch_id: int | None
    teams_summary: str          # напр. "Rikudou-Sennin Clan, Bloody Rain"
    chapter_count: int = 0
    first_number: str = ""
    last_number: str = ""

    @property
    def coverage(self) -> str:
        if self.first_number == self.last_number:
            return f"гл. {self.first_number}"
        return f"гл. {self.first_number}–{self.last_number}"

    @property
    def label(self) -> str:
        return f"{self.teams_summary}  ·  {self.chapter_count} гл. ({self.coverage})"


@dataclass
class DownloadOptions:
    output_root: Path
    make_cbz_files: bool = True
    convert: bool = True
    convert_format: str = config.CONVERT_FORMAT
    keep_folders: bool = True  # оставлять папки с картинками
    skip_existing: bool = True  # пропускать уже скачанные главы (докачка)
    # настройки скорости / защиты от лимитов
    concurrency: int = config.MAX_CONCURRENT_DOWNLOADS
    image_rate_rps: float = config.IMAGE_RATE_RPS
    inter_chapter_delay: float = config.INTER_CHAPTER_DELAY


@dataclass
class DownloadReport:
    manga_title: str
    chapters_done: int = 0
    chapters_failed: int = 0
    chapters_locked: int = 0       # платные/ранний доступ
    chapters_unreleased: int = 0   # ещё не вышли
    chapters_skipped: int = 0      # уже скачаны (докачка)
    errors: list[str] = field(default_factory=list)
    output_dir: Path | None = None


def list_branches(chapters: list[Chapter]) -> list[BranchOption]:
    """Собирает уникальные переводы (ветки) по всем главам тайтла.

    Группировка строго по branch_id. Команды агрегируются в порядке
    появления; охват = первая..последняя глава, где встречается ветка.
    """
    order: list[int | None] = []
    teams_by_branch: dict[int | None, list[str]] = {}
    chapters_by_branch: dict[int | None, list[str]] = {}

    for ch in chapters:
        for br in ch.branches:
            bid = br.branch_id
            if bid not in chapters_by_branch:
                order.append(bid)
                chapters_by_branch[bid] = []
                teams_by_branch[bid] = []
            chapters_by_branch[bid].append(ch.number)
            for name in br.teams:
                if name and name not in teams_by_branch[bid]:
                    teams_by_branch[bid].append(name)

    options: list[BranchOption] = []
    for bid in order:
        nums = chapters_by_branch[bid]
        teams = teams_by_branch[bid]
        options.append(
            BranchOption(
                branch_id=bid,
                teams_summary=", ".join(teams) if teams else config.UNSIGNED_LABEL,
                chapter_count=len(nums),
                first_number=nums[0],
                last_number=nums[-1],
            )
        )
    # Самый полный перевод — сверху.
    return sorted(options, key=lambda o: -o.chapter_count)


def _pick_branch(chapter: Chapter, branch_id: int | None) -> Branch | None:
    """Находит в главе нужную ветку перевода; иначе None."""
    if branch_id is None:
        return chapter.branches[0] if chapter.branches else None
    for br in chapter.branches:
        if br.branch_id == branch_id:
            return br
    return None


class DownloadService:
    def __init__(self, client: MangaLibClient, options: DownloadOptions,
                 log: Callable[[str], None] | None = None):
        self.client = client
        self.options = options
        self.log = log
        throttle = self._make_throttle_logger()
        # Общий лимитер картинок на всю сессию скачивания.
        img_limiter = RateLimiter(options.image_rate_rps)
        self.downloader = ChapterDownloader(
            client,
            convert=options.convert,
            convert_format=options.convert_format,
            concurrency=options.concurrency,
            limiter=img_limiter,
            on_throttle=throttle,
        )
        # тот же обработчик троттлинга и для API-запросов
        client.on_throttle = throttle

    def _make_throttle_logger(self):
        def _throttle(seconds: float, attempt: int) -> None:
            if self.log:
                self.log(f"⏳ Лимит сервера: пауза {seconds:.0f}с "
                         f"(попытка {attempt + 1})")
        return _throttle

    async def download(
        self,
        manga: Manga,
        chapters: list[Chapter],
        branch_id: int | None,
        branch_label: str,
        progress: ProgressFn | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> DownloadReport:
        report = DownloadReport(manga_title=manga.title)
        manga_dir = self.options.output_root / safe_name(manga.title) / safe_name(branch_label)
        manga_dir.mkdir(parents=True, exist_ok=True)
        report.output_dir = manga_dir

        total = len(chapters)
        for i, ch in enumerate(chapters, start=1):
            if should_cancel and should_cancel():
                report.errors.append("Отменено пользователем.")
                break

            br = _pick_branch(ch, branch_id)
            if br is None:
                report.chapters_failed += 1
                report.errors.append(f"{ch.label}: нет выбранного перевода, пропущено.")
                if progress:
                    progress(f"⏭ {ch.label}: перевод недоступен", i, total, 0, 0)
                continue

            ch_dir = manga_dir / safe_name(ch.label)

            if self.options.skip_existing and self._already_downloaded(ch, manga_dir):
                report.chapters_skipped += 1
                if progress:
                    progress(f"↪ {ch.label}: уже скачана, пропуск", i, total, 0, 0)
                continue

            try:
                if progress:
                    progress(f"📖 {ch.label}: получаю страницы…", i - 1, total, 0, 0)
                pages = await self.client.get_pages(
                    manga.slug, ch.volume, ch.number, br.branch_id
                )

                def page_progress(done: int, tot: int, _msg: str, _i=i, _ch=ch) -> None:
                    if progress:
                        progress(f"⬇ {_ch.label}", _i - 1, total, done, tot)

                result = await self.downloader.download_pages(
                    pages, ch_dir, progress=page_progress
                )

                if self.options.make_cbz_files:
                    self._package(ch, ch_dir, result)

                if not self.options.keep_folders:
                    self._cleanup_folders(result)

                report.chapters_done += 1
                if progress:
                    progress(f"✅ {ch.label} готова", i, total, result.page_count,
                             result.page_count)
            except UnreleasedChapterError as e:
                report.chapters_unreleased += 1
                report.errors.append(f"{ch.label}: ⏰ {e}")
                if progress:
                    progress(f"⏰ {ch.label}: ещё не вышла", i, total, 0, 0)
            except LockedChapterError as e:
                report.chapters_locked += 1
                report.errors.append(f"{ch.label}: 🔒 {e}")
                if progress:
                    progress(f"🔒 {ch.label}: платная (ранний доступ)", i, total, 0, 0)
            except Exception as e:  # noqa: BLE001
                report.chapters_failed += 1
                report.errors.append(f"{ch.label}: {e}")
                if progress:
                    progress(f"❌ {ch.label}: {e}", i, total, 0, 0)

            # Пауза между главами — мягче к лимитам сервера.
            if i < total and self.options.inter_chapter_delay > 0:
                await asyncio.sleep(self.options.inter_chapter_delay)

        return report

    def _already_downloaded(self, ch: Chapter, manga_dir: Path) -> bool:
        """Глава считается скачанной, если есть её CBZ или непустая папка original."""
        base = safe_name(ch.label)
        if self.options.make_cbz_files:
            cbz = manga_dir / f"{base} [original].cbz"
            if cbz.exists() and cbz.stat().st_size > 0:
                return True
        if self.options.keep_folders:
            od = manga_dir / base / "original"
            if od.is_dir() and any(od.iterdir()):
                return True
        return False

    def _package(self, ch: Chapter, ch_dir: Path, result) -> None:
        base = safe_name(ch.label)
        if result.original_dir and any(result.original_dir.iterdir()):
            make_cbz(result.original_dir, ch_dir.parent / f"{base} [original].cbz")
        if result.converted_dir and any(result.converted_dir.iterdir()):
            make_cbz(result.converted_dir, ch_dir.parent / f"{base} [converted].cbz")

    @staticmethod
    def _cleanup_folders(result) -> None:
        import shutil
        for d in (result.original_dir, result.converted_dir):
            if d and d.exists():
                shutil.rmtree(d, ignore_errors=True)

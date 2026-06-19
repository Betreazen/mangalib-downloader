"""Десктоп-GUI загрузчика MangaLib на PySide6."""
from __future__ import annotations

import asyncio
import sys
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QObject, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mangalib_dl import (
    DownloadOptions,
    DownloadService,
    LicensedTitleError,
    MangaLibClient,
    list_branches,
    parse_slug,
    storage,
)
from mangalib_dl import config

DEFAULT_OUTPUT = str(Path.home() / "Downloads" / "MangaLib")


# ----------------------- фоновые задачи (asyncio в QThread) -----------------------

class LoaderWorker(QObject):
    loaded = Signal(object, object, object)   # manga, chapters, branch_options
    failed = Signal(str)

    def __init__(self, url: str, token: str | None):
        super().__init__()
        self.url = url
        self.token = token

    def run(self) -> None:
        try:
            asyncio.run(self._load())
        except LicensedTitleError as e:
            self.failed.emit(str(e))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"Ошибка: {e}")

    async def _load(self) -> None:
        async with MangaLibClient(self.token) as client:
            slug = parse_slug(self.url)
            manga = await client.get_manga(slug)
            chapters = await client.get_chapters(slug)
            branches = list_branches(chapters)
            self.loaded.emit(manga, chapters, branches)


class DownloadWorker(QObject):
    progress = Signal(str, int, int, int, int)  # msg, cd, ct, dp, tp
    log = Signal(str)
    done = Signal(object)                        # DownloadReport
    failed = Signal(str)

    def __init__(self, token, manga, chapters, branch_id, branch_label, options):
        super().__init__()
        self.token = token
        self.manga = manga
        self.chapters = chapters
        self.branch_id = branch_id
        self.branch_label = branch_label
        self.options = options
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"Ошибка скачивания: {e}")

    async def _run(self) -> None:
        async with MangaLibClient(self.token) as client:
            service = DownloadService(client, self.options, log=self.log.emit)
            report = await service.download(
                self.manga, self.chapters, self.branch_id, self.branch_label,
                progress=lambda *a: self.progress.emit(*a),
                should_cancel=self._cancel.is_set,
            )
            self.done.emit(report)


class CatalogWorker(QObject):
    result = Signal(list, bool, object)   # items, has_next, seed
    failed = Signal(str)

    def __init__(self, token, page, query, types, sort_by, seed):
        super().__init__()
        self.token = token
        self.page = page
        self.query = query
        self.types = types
        self.sort_by = sort_by
        self.seed = seed

    def run(self) -> None:
        try:
            asyncio.run(self._run())
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"Ошибка каталога: {e}")

    async def _run(self) -> None:
        async with MangaLibClient(self.token) as client:
            items, has_next, seed = await client.get_catalog(
                self.page, query=self.query or None, types=self.types or None,
                sort_by=self.sort_by, seed=self.seed,
            )
            self.result.emit(items, has_next, seed)


# Сортировки каталога: ярлык -> sort_by API
CATALOG_SORTS = [
    ("Популярные", "views"),
    ("По рейтингу", "rate_avg"),
    ("Последнее обновление", "last_chapter_at"),
    ("Новинки", "created_at"),
]
CATALOG_TYPES = [
    ("Все типы", None),
    ("Манга", 1),
    ("Манхва", 5),
    ("Маньхуа", 6),
]


class CatalogDialog(QDialog):
    """Браузер каталога: поиск, фильтры, бесконечная подгрузка по страницам."""

    def __init__(self, parent, token):
        super().__init__(parent)
        self.token = token
        self.selected_slug: str | None = None
        self._page = 1
        self._seed = None
        self._thread = None
        self._worker = None
        self.setWindowTitle("Каталог MangaLib")
        self.resize(640, 600)

        root = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск по названию (пусто = весь каталог)")
        self.search_edit.returnPressed.connect(self._new_search)
        self.sort_combo = QComboBox()
        for label, _ in CATALOG_SORTS:
            self.sort_combo.addItem(label)
        self.type_combo = QComboBox()
        for label, _ in CATALOG_TYPES:
            self.type_combo.addItem(label)
        self.search_btn = QPushButton("Искать")
        self.search_btn.clicked.connect(self._new_search)
        top.addWidget(self.search_edit, 1)
        top.addWidget(self.sort_combo)
        top.addWidget(self.type_combo)
        top.addWidget(self.search_btn)
        root.addLayout(top)

        self.status = QLabel("")
        root.addWidget(self.status)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _i: self._accept_selected())
        root.addWidget(self.list, 1)

        self.more_btn = QPushButton("Загрузить ещё")
        self.more_btn.clicked.connect(self._load_more)
        self.more_btn.setEnabled(False)
        root.addWidget(self.more_btn)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_selected)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._new_search()

    def _new_search(self) -> None:
        self._page = 1
        self._seed = None
        self.list.clear()
        self._fetch()

    def _load_more(self) -> None:
        self._page += 1
        self._fetch()

    def _fetch(self) -> None:
        self.search_btn.setEnabled(False)
        self.more_btn.setEnabled(False)
        self.status.setText("Загрузка…")
        sort_by = CATALOG_SORTS[self.sort_combo.currentIndex()][1]
        types_val = CATALOG_TYPES[self.type_combo.currentIndex()][1]
        types = [types_val] if types_val else None

        self._thread = QThread()
        self._worker = CatalogWorker(
            self.token, self._page, self.search_edit.text().strip(),
            types, sort_by, self._seed,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.result.connect(self._on_result)
        self._worker.failed.connect(self._on_failed)
        self._worker.result.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.start()

    def _on_result(self, items, has_next, seed) -> None:
        self._seed = seed or self._seed
        for it in items:
            title = it.get("rus_name") or it.get("name") or it.get("eng_name") or "?"
            slug = it.get("slug_url") or f'{it.get("id")}--{it.get("slug")}'
            type_name = ""
            t = it.get("type")
            if isinstance(t, dict):
                type_name = t.get("label") or t.get("name") or ""
            row = QListWidgetItem(f"{title}    ·    {type_name}")
            row.setData(Qt.ItemDataRole.UserRole, slug)
            self.list.addItem(row)
        self.search_btn.setEnabled(True)
        self.more_btn.setEnabled(bool(has_next))
        self.status.setText(f"Показано: {self.list.count()}"
                            + ("" if has_next else "  (конец каталога)"))

    def _on_failed(self, msg: str) -> None:
        self.search_btn.setEnabled(True)
        self.status.setText(msg)

    def _accept_selected(self) -> None:
        item = self.list.currentItem()
        if item is None and self.list.count():
            item = self.list.item(0)
        if item is not None:
            self.selected_slug = item.data(Qt.ItemDataRole.UserRole)
            self.accept()


# ------------------------------- главное окно -------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MangaLib Downloader")
        self.resize(960, 860)

        self.manga = None
        self.chapters: list = []
        self.branch_options: list = []
        self._load_thread = None
        self._load_worker = None
        self._dl_thread = None
        self._dl_worker = None

        self._build_ui()
        self._load_saved()

    # ---------- построение интерфейса ----------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)

        # строка ссылки
        url_row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText(
            "https://mangalib.me/ru/manga/7965--chainsaw-man  (или slug)"
        )
        self.url_edit.returnPressed.connect(self.on_load)
        self.catalog_btn = QPushButton("Каталог…")
        self.catalog_btn.clicked.connect(self.on_open_catalog)
        self.load_btn = QPushButton("Загрузить")
        self.load_btn.clicked.connect(self.on_load)
        url_row.addWidget(self.url_edit)
        url_row.addWidget(self.catalog_btn)
        url_row.addWidget(self.load_btn)
        root.addLayout(url_row)

        # строка токена
        token_row = QHBoxLayout()
        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_edit.setPlaceholderText(
            "Bearer-токен (только для лицензированных / 18+); не обязательно"
        )
        self.show_token_btn = QPushButton("Показать")
        self.show_token_btn.setCheckable(True)
        self.show_token_btn.toggled.connect(self._toggle_token_visible)
        self.remember_token_cb = QCheckBox("Запомнить токен")
        token_row.addWidget(self.token_edit)
        token_row.addWidget(self.show_token_btn)
        token_row.addWidget(self.remember_token_cb)
        root.addLayout(token_row)

        self.status_label = QLabel("")
        root.addWidget(self.status_label)

        self.title_label = QLabel("")
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        self.title_label.setFont(f)
        root.addWidget(self.title_label)

        # выбор перевода
        branch_row = QHBoxLayout()
        branch_row.addWidget(QLabel("Перевод:"))
        self.branch_combo = QComboBox()
        self.branch_combo.currentIndexChanged.connect(self._rebuild_chapter_table)
        branch_row.addWidget(self.branch_combo, 1)
        root.addLayout(branch_row)

        # выбор глав
        sel_row = QHBoxLayout()
        self.select_all_btn = QPushButton("Выделить все")
        self.select_all_btn.clicked.connect(lambda: self._set_all_checks(True))
        self.clear_all_btn = QPushButton("Снять все")
        self.clear_all_btn.clicked.connect(lambda: self._set_all_checks(False))
        self.range_edit = QLineEdit()
        self.range_edit.setPlaceholderText("Диапазон: 1-10, 15, 20")
        self.range_edit.returnPressed.connect(self.on_apply_range)
        self.range_btn = QPushButton("Выбрать диапазон")
        self.range_btn.clicked.connect(self.on_apply_range)
        sel_row.addWidget(self.select_all_btn)
        sel_row.addWidget(self.clear_all_btn)
        sel_row.addWidget(self.range_edit, 1)
        sel_row.addWidget(self.range_btn)
        root.addLayout(sel_row)

        # таблица глав
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["✓", "Глава", "Команда (перевод)"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.table, 1)

        # папка
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Папка:"))
        self.output_edit = QLineEdit(DEFAULT_OUTPUT)
        self.browse_btn = QPushButton("Обзор…")
        self.browse_btn.clicked.connect(self.on_browse)
        out_row.addWidget(self.output_edit, 1)
        out_row.addWidget(self.browse_btn)
        root.addLayout(out_row)

        # опции формата
        opt_row = QHBoxLayout()
        self.convert_cb = QCheckBox("Конвертировать AVIF → JPG")
        self.convert_cb.setChecked(True)
        self.cbz_cb = QCheckBox("Собирать CBZ")
        self.cbz_cb.setChecked(True)
        self.keep_cb = QCheckBox("Оставлять папки с картинками")
        self.keep_cb.setChecked(True)
        self.skip_cb = QCheckBox("Пропускать уже скачанные (докачка)")
        self.skip_cb.setChecked(True)
        opt_row.addWidget(self.convert_cb)
        opt_row.addWidget(self.cbz_cb)
        opt_row.addWidget(self.keep_cb)
        opt_row.addWidget(self.skip_cb)
        opt_row.addStretch(1)
        root.addLayout(opt_row)

        # скорость / лимиты
        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("Параллельно:"))
        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(1, 32)
        self.concurrency_spin.setValue(config.MAX_CONCURRENT_DOWNLOADS)
        speed_row.addWidget(self.concurrency_spin)
        speed_row.addWidget(QLabel("Картинок/сек:"))
        self.rate_spin = QDoubleSpinBox()
        self.rate_spin.setRange(0.5, 50.0)
        self.rate_spin.setSingleStep(0.5)
        self.rate_spin.setValue(config.IMAGE_RATE_RPS)
        speed_row.addWidget(self.rate_spin)
        speed_row.addWidget(QLabel("Пауза между главами, с:"))
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.0, 30.0)
        self.delay_spin.setSingleStep(0.1)
        self.delay_spin.setValue(config.INTER_CHAPTER_DELAY)
        speed_row.addWidget(self.delay_spin)
        speed_row.addStretch(1)
        root.addLayout(speed_row)

        # кнопки скачивания
        dl_row = QHBoxLayout()
        self.download_btn = QPushButton("⬇  Скачать выбранное")
        self.download_btn.clicked.connect(self.on_download)
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self.on_cancel)
        self.cancel_btn.setEnabled(False)
        dl_row.addWidget(self.download_btn)
        dl_row.addWidget(self.cancel_btn)
        root.addLayout(dl_row)

        # прогресс
        self.overall_bar = QProgressBar()
        self.overall_bar.setFormat("Главы: %v / %m")
        self.page_bar = QProgressBar()
        self.page_bar.setFormat("Страницы: %v / %m")
        root.addWidget(self.overall_bar)
        root.addWidget(self.page_bar)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(1000)
        self.log_view.setFixedHeight(150)
        root.addWidget(self.log_view)

    # ---------- сохранённые настройки ----------

    def _load_saved(self) -> None:
        cfg = storage.load_config()
        token = cfg.get("token")
        if token:
            self.token_edit.setText(token)
            self.remember_token_cb.setChecked(True)
        if cfg.get("output"):
            self.output_edit.setText(cfg["output"])
        if cfg.get("concurrency"):
            self.concurrency_spin.setValue(int(cfg["concurrency"]))
        if cfg.get("image_rate"):
            self.rate_spin.setValue(float(cfg["image_rate"]))
        if cfg.get("inter_chapter_delay") is not None:
            self.delay_spin.setValue(float(cfg["inter_chapter_delay"]))
        if cfg.get("skip_existing") is not None:
            self.skip_cb.setChecked(bool(cfg["skip_existing"]))

    def _persist(self) -> None:
        data = {
            "output": self.output_edit.text().strip(),
            "concurrency": self.concurrency_spin.value(),
            "image_rate": self.rate_spin.value(),
            "inter_chapter_delay": self.delay_spin.value(),
            "skip_existing": self.skip_cb.isChecked(),
        }
        if self.remember_token_cb.isChecked() and self.token_edit.text().strip():
            data["token"] = self.token_edit.text().strip()
        else:
            data["token"] = ""
        storage.update_config(**data)

    # ---------- утилиты ----------

    def _log(self, msg: str) -> None:
        self.log_view.appendPlainText(msg)

    def _set_status(self, msg: str, color: str = "#e0a800") -> None:
        self.status_label.setText(msg)
        self.status_label.setStyleSheet(f"color: {color};")

    def _toggle_token_visible(self, on: bool) -> None:
        self.token_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
        )
        self.show_token_btn.setText("Скрыть" if on else "Показать")

    def _selected_branch_id(self):
        idx = self.branch_combo.currentIndex()
        if idx < 0 or idx >= len(self.branch_options):
            return None
        return self.branch_options[idx].branch_id

    def _selected_branch_label(self) -> str:
        idx = self.branch_combo.currentIndex()
        if 0 <= idx < len(self.branch_options):
            return self.branch_options[idx].teams_summary
        return "default"

    # ---------- загрузка тайтла ----------

    def on_load(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            self._set_status("Введите ссылку или slug.", "#d9534f")
            return
        self.load_btn.setEnabled(False)
        self._set_status("Загружаю данные тайтла…")
        token = self.token_edit.text().strip() or None

        self._load_thread = QThread()
        self._load_worker = LoaderWorker(url, token)
        self._load_worker.moveToThread(self._load_thread)
        self._load_thread.started.connect(self._load_worker.run)
        self._load_worker.loaded.connect(self._on_loaded)
        self._load_worker.failed.connect(self._on_load_failed)
        self._load_worker.loaded.connect(self._load_thread.quit)
        self._load_worker.failed.connect(self._load_thread.quit)
        self._load_thread.start()

    def _on_loaded(self, manga, chapters, branches) -> None:
        self.manga = manga
        self.chapters = chapters
        self.branch_options = branches
        self.title_label.setText(f"{manga.title}   ·   глав: {len(chapters)}")
        self.branch_combo.blockSignals(True)
        self.branch_combo.clear()
        for o in branches:
            self.branch_combo.addItem(o.label)
        self.branch_combo.blockSignals(False)
        self.branch_combo.setCurrentIndex(0)
        self._rebuild_chapter_table()
        self._set_status(
            f"Готово. Переводов: {len(branches)}. Выберите перевод и главы.", "#5cb85c"
        )
        self.load_btn.setEnabled(True)

    def _on_load_failed(self, msg: str) -> None:
        self._set_status(msg, "#d9534f")
        self.load_btn.setEnabled(True)

    # ---------- таблица глав ----------

    def _rebuild_chapter_table(self) -> None:
        bid = self._selected_branch_id()
        rows = [ch for ch in self.chapters if ch.has_branch(bid)]
        self.table.setRowCount(len(rows))
        self._row_chapters = rows
        for r, ch in enumerate(rows):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(r, 0, chk)
            self.table.setItem(r, 1, QTableWidgetItem(ch.label))
            self.table.setItem(r, 2, QTableWidgetItem(ch.team_label_for(bid)))

    def _set_all_checks(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for r in range(self.table.rowCount()):
            self.table.item(r, 0).setCheckState(state)

    def on_apply_range(self) -> None:
        spec = self.range_edit.text().strip()
        wanted: set[str] = set()
        for part in spec.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                a, b = part.split("-", 1)
                try:
                    for n in range(int(float(a)), int(float(b)) + 1):
                        wanted.add(str(n))
                except ValueError:
                    wanted.add(part)
            else:
                wanted.add(part)
        for r, ch in enumerate(self._row_chapters):
            state = Qt.CheckState.Checked if ch.number in wanted else Qt.CheckState.Unchecked
            self.table.item(r, 0).setCheckState(state)

    def on_open_catalog(self) -> None:
        token = self.token_edit.text().strip() or None
        dlg = CatalogDialog(self, token)
        if dlg.exec() and dlg.selected_slug:
            self.url_edit.setText(dlg.selected_slug)
            self.on_load()

    def on_browse(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Выберите папку для сохранения", self.output_edit.text().strip()
        )
        if path:
            self.output_edit.setText(path)

    # ---------- скачивание ----------

    def _selected_chapters(self) -> list:
        result = []
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).checkState() == Qt.CheckState.Checked:
                result.append(self._row_chapters[r])
        return result

    def on_download(self) -> None:
        if not self.manga:
            self._set_status("Сначала загрузите тайтл.", "#d9534f")
            return
        selected = self._selected_chapters()
        if not selected:
            self._set_status("Не выбрано ни одной главы.", "#d9534f")
            return
        if not (self.cbz_cb.isChecked() or self.keep_cb.isChecked()):
            self._set_status("Нечего сохранять: включите CBZ или папки.", "#d9534f")
            return

        self._persist()
        options = DownloadOptions(
            output_root=Path(self.output_edit.text().strip() or DEFAULT_OUTPUT),
            make_cbz_files=self.cbz_cb.isChecked(),
            convert=self.convert_cb.isChecked(),
            keep_folders=self.keep_cb.isChecked(),
            skip_existing=self.skip_cb.isChecked(),
            concurrency=self.concurrency_spin.value(),
            image_rate_rps=self.rate_spin.value(),
            inter_chapter_delay=self.delay_spin.value(),
        )
        self.overall_bar.setRange(0, len(selected))
        self.overall_bar.setValue(0)
        self.page_bar.setRange(0, 1)
        self.page_bar.setValue(0)
        self.download_btn.setEnabled(False)
        self.load_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self._set_status(f"Скачивание {len(selected)} глав…")

        token = self.token_edit.text().strip() or None
        self._dl_thread = QThread()
        self._dl_worker = DownloadWorker(
            token, self.manga, selected,
            self._selected_branch_id(), self._selected_branch_label(), options,
        )
        self._dl_worker.moveToThread(self._dl_thread)
        self._dl_thread.started.connect(self._dl_worker.run)
        self._dl_worker.progress.connect(self._on_progress)
        self._dl_worker.log.connect(self._log)
        self._dl_worker.done.connect(self._on_download_done)
        self._dl_worker.failed.connect(self._on_download_failed)
        self._dl_worker.done.connect(self._dl_thread.quit)
        self._dl_worker.failed.connect(self._dl_thread.quit)
        self._dl_thread.start()

    def _on_progress(self, msg, cd, ct, dp, tp) -> None:
        self.overall_bar.setRange(0, ct or 1)
        self.overall_bar.setValue(cd)
        self.page_bar.setRange(0, tp or 1)
        self.page_bar.setValue(dp)
        self.status_label.setText(msg)
        if msg[:1] in ("✅", "❌", "⏭"):
            self._log(msg)

    def _on_download_done(self, report) -> None:
        ok = report.chapters_failed == 0
        extra = ""
        if report.chapters_skipped:
            extra += f", ↪ уже было: {report.chapters_skipped}"
        if report.chapters_locked:
            extra += f", 🔒 платных: {report.chapters_locked}"
        if report.chapters_unreleased:
            extra += f", ⏰ не вышло: {report.chapters_unreleased}"
        self._set_status(
            f"Готово: {report.chapters_done} глав, ошибок: {report.chapters_failed}"
            f"{extra}. → {report.output_dir}",
            "#5cb85c" if ok else "#e0a800",
        )
        self._log(f"📁 {report.output_dir}")
        for err in report.errors:
            self._log("  ! " + err)
        self._reset_buttons()

    def _on_download_failed(self, msg: str) -> None:
        self._set_status(msg, "#d9534f")
        self._log(msg)
        self._reset_buttons()

    def _reset_buttons(self) -> None:
        self.download_btn.setEnabled(True)
        self.load_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def on_cancel(self) -> None:
        if self._dl_worker:
            self._dl_worker.cancel()
            self._log("⏹ Запрошена отмена (завершу текущую главу)…")
            self.cancel_btn.setEnabled(False)

    def closeEvent(self, event) -> None:
        self._persist()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

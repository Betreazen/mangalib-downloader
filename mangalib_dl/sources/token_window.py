"""Dev-окно браузера для логина на сайтах и захвата их bearer-токенов.

Запуск:  python -m mangalib_dl.sources.token_window

Как работает: встроенный Chromium (QtWebEngine) с постоянным профилем —
логинишься/регистрируешься как обычно. Перехватчик запросов ловит заголовок
`Authorization: Bearer …`, который сайт сам шлёт своему API, и показывает его.
Кнопка «Сохранить» кладёт токен в tokens.json (конфиг-папка, не в репозиторий).

Это инструмент разработки. В проде вместо ручного логина предполагается
один мастер-аккаунт на сайт (см. SITES.md).
"""
from __future__ import annotations

import re
import sys

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWebEngineCore import (
    QWebEngineProfile,
    QWebEngineUrlRequestInfo,
    QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .registry import source_meta
from .token_store import load_tokens, save_token

# Стартовые страницы логина по источникам.
LOGIN_URLS = {
    "mangalib": "https://mangalib.me/ru",
    "yaoilib": "https://v2.slashlib.me/ru",
    "hentailib": "https://hentailib.me/ru",
    "ranobelib": "https://ranobelib.me/ru",
    "animelib": "https://anilib.me/ru",
    "remanga": "https://remanga.org/",
    "senkuro": "https://senkuro.com/",
    "inkstory": "https://inkstory.net/",
    "mangahub": "https://mangahub.ru/",
    "mangadex": "https://mangadex.org/",
}

_JWT_RE = re.compile(r"^Bearer\s+[A-Za-z0-9._-]{20,}$")


class _TokenInterceptor(QWebEngineUrlRequestInterceptor):
    """Читает заголовок Authorization из исходящих запросов страницы."""

    def __init__(self, on_token):
        super().__init__()
        self._on_token = on_token
        self._last = ""

    def interceptRequest(self, info: QWebEngineUrlRequestInfo) -> None:
        try:
            raw = bytes(info.httpHeaders().get(b"Authorization", b"")).decode()
        except Exception:  # noqa: BLE001 — API отличается между версиями Qt
            raw = ""
        if raw and raw != self._last and _JWT_RE.match(raw.strip()):
            self._last = raw.strip()
            self._on_token(self._last)


class TokenWindow(QMainWindow):
    token_captured = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Захват токенов источников (dev)")
        self.resize(1200, 850)
        self._current_token = ""

        # Постоянный профиль: логин сохраняется между запусками.
        self.profile = QWebEngineProfile("mangadl_dev", self)
        self.profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )
        self.interceptor = _TokenInterceptor(self._on_token)
        self.profile.setUrlRequestInterceptor(self.interceptor)

        self.view = QWebEngineView()
        page_cls = self.view.page().__class__
        self.view.setPage(page_cls(self.profile, self.view))

        # --- панель управления ---
        self.source_box = QComboBox()
        for m in source_meta():
            if m["id"] in LOGIN_URLS:
                self.source_box.addItem(f"{m['name']} ({m['id']})", m["id"])
        self.source_box.currentIndexChanged.connect(self._open_login)

        open_btn = QPushButton("Открыть логин")
        open_btn.clicked.connect(self._open_login)

        self.token_field = QLineEdit()
        self.token_field.setPlaceholderText("Токен появится здесь после входа на сайт…")
        self.token_field.setReadOnly(True)

        save_btn = QPushButton("💾 Сохранить токен")
        save_btn.clicked.connect(self._save)

        dump_btn = QPushButton("Показать localStorage")
        dump_btn.clicked.connect(self._dump_storage)

        self.status = QLabel("Выбери сайт, войди в аккаунт — токен поймается сам.")

        top = QHBoxLayout()
        top.addWidget(QLabel("Сайт:"))
        top.addWidget(self.source_box, 2)
        top.addWidget(open_btn)
        top.addWidget(dump_btn)

        mid = QHBoxLayout()
        mid.addWidget(self.token_field, 4)
        mid.addWidget(save_btn)

        layout = QVBoxLayout()
        layout.addLayout(top)
        layout.addLayout(mid)
        layout.addWidget(self.status)
        layout.addWidget(self.view, 1)

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        self._show_saved()
        self._open_login()

    # ---- логика ----

    def _current_source_id(self) -> str:
        return self.source_box.currentData() or "mangalib"

    def _open_login(self) -> None:
        sid = self._current_source_id()
        self._current_token = ""
        self.token_field.clear()
        self.interceptor._last = ""
        url = LOGIN_URLS.get(sid, "https://mangalib.me/ru")
        self.view.load(QUrl(url))
        self.status.setText(f"Открыт {sid}. Войди/зарегистрируйся — токен поймается.")

    def _on_token(self, token: str) -> None:
        self._current_token = token
        # Signal + обновление UI из главного потока Qt (interceptor зовётся в нём же).
        self.token_field.setText(token)
        self.status.setText("✅ Токен пойман! Нажми «Сохранить», чтобы записать.")
        self.token_captured.emit(token)

    def _save(self) -> None:
        if not self._current_token:
            QMessageBox.warning(self, "Нет токена",
                                "Токен ещё не пойман. Войди в аккаунт на сайте.")
            return
        sid = self._current_source_id()
        save_token(sid, self._current_token)
        self.status.setText(f"💾 Сохранён токен для {sid}.")
        self._show_saved()

    def _dump_storage(self) -> None:
        js = "JSON.stringify(Object.assign({}, window.localStorage))"
        self.view.page().runJavaScript(js, self._show_storage)

    def _show_storage(self, data) -> None:
        # Ищем в localStorage что-то похожее на токен (запасной путь).
        text = str(data or "")
        m = re.search(r'(eyJ[A-Za-z0-9._-]{20,})', text)
        if m:
            tok = "Bearer " + m.group(1)
            self._on_token(tok)
        else:
            QMessageBox.information(self, "localStorage",
                                    text[:1500] or "Пусто.")

    def _show_saved(self) -> None:
        saved = ", ".join(load_tokens().keys()) or "—"
        self.setWindowTitle(f"Захват токенов (dev) · сохранены: {saved}")


def main() -> None:
    app = QApplication(sys.argv)
    w = TokenWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

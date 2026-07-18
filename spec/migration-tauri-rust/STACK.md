# STACK.md — выбор технологий и крейтов

Принцип (ponytail): брать зрелые крейты, не изобретать. Один рантайм, один
HTTP-клиент, минимум зависимостей.

## Ядро (Rust)

| Задача | Крейт | Почему / что заменяет из Python |
|--------|-------|--------------------------------|
| Async-рантайм | `tokio` (rt-multi-thread) | замена asyncio; параллельный fan-out по сайтам |
| HTTP | `reqwest` (rustls, gzip, brotli) | замена httpx; без OpenSSL (rustls — статически) |
| JSON | `serde` + `serde_json` | замена ручного разбора dict; типобезопасные DTO |
| Трейты async | `async-trait` | `MangaSource` как объект-трейт (dyn) |
| Ошибки | `thiserror` | замена иерархии Exception (`SourceError` и потомки) |
| Rate-limit | `governor` | токен-бакет вместо ручного `RateLimiter` |
| Ретраи/бэкофф | `backon` (или свой, 30 строк) | замена `request_with_retries` (429/Retry-After) |
| HTML-парсинг | `scraper` | замена регэкспов mangahub (CSS-селекторы надёжнее) |
| Картинки/AVIF | `image` + `ravif`/`libavif` decode | замена Pillow; AVIF→JPEG статически |
| ZIP/CBZ | `zip` | замена `make_cbz` |
| Логи | `tracing` + `tracing-subscriber` | структурные логи + таймингов для dev-панели |
| Время/ISO | `chrono` | `publish_at`/`expired_at` разбор |
| Файлы конфигурации | `directories` + `serde_json` | замена `storage.py` (папка пользователя) |

GraphQL (senkuro) — **без отдельного клиента**: обычный `reqwest` POST с JSON-телом,
как сейчас в Python. Схему не тянем.

## Оболочка (Tauri 2)

- **`tauri` 2.x** — вебвью-оболочка, IPC-команды, сборка в один бинарь, авто-апдейтер
  (опц.), нативные диалоги выбора папки.
- **Захват токенов:** `tauri` `WebviewWindow` + инъекция JS (чтение `localStorage`,
  `Authorization`) — план в ARCHITECTURE.md §7.
- Плагины: `tauri-plugin-dialog` (выбор папки), `tauri-plugin-fs` (запись),
  `tauri-plugin-shell` (открыть папку, desktop), `tauri-plugin-store` (настройки/токены).

## Мобильная сборка (Android) — решено (PRD D2)

Tauri 2 собирает Android из того же проекта (`cargo tauri android build` → APK/AAB).
Rust-core и Svelte-фронт общие; различия — через абстракцию платформы:

| Аспект | Desktop | Android |
|--------|---------|---------|
| Хранилище | прямой путь | scoped storage: app-dir или папка через SAF (`tauri-plugin-fs` + пикер) |
| Выбор папки | нативный диалог | системный пикер (SAF) |
| «Открыть папку» | `tauri-plugin-shell` | intent/через файловый менеджер (или пропустить) |
| Фоновая скачка | обычная задача | foreground-service/keep-awake на время скачки |
| Токены | webview-окно | webview-экран (тот же JS-путь, D3) |

**AVIF на Android — риск-точка.** `image`+`dav1d` требует кросс-компиляции под NDK.
План: проверить на Фазе 1b; если тяжело — на мобиле по умолчанию **хранить оригинал
AVIF без конвертации** (Android/читалки его показывают), конвертацию сделать
опциональной. На desktop конвертация как сейчас.

**Портируемость крейтов:** tokio, reqwest(rustls), serde, governor, zip, scraper,
chrono — все собираются под Android NDK. Точка внимания только AVIF-декод (выше).
Требование к коду: никаких desktop-only вызовов в `mangadl-core` — платформенное
только в `mangadl-tauri` за `#[cfg(...)]`.

## Фронтенд (решено: Svelte 5)

**Svelte 5 + TypeScript + Vite** — зафиксировано (PRD D1). Один фронт на desktop и
Android, адаптивная вёрстка (медиазапросы/контейнер-квери: на телефоне — одна
колонка, на десктопе — мастер-деталь). Список глав бывает 1000+ (One Piece 1191) —
виртуализация (`@tanstack/virtual`, работает и на мобиле), как это было важно в
текущем PySide6-GUI ([[gui-prefers-pyside6]] в памяти).

UI-стиль: без тяжёлого UI-кита. Свои компоненты + минимальный CSS. Тач-таргеты и
жесты учесть для Android. Никакого Electron-класса бандла.

## Что НЕ берём

- Не Electron (тяжёлый, противоречит цели «лёгкий бинарь»).
- Не diesel/SQL — состояние маленькое, JSON-файлов достаточно (YAGNI).
- Не отдельный GraphQL-клиент — один POST.
- Не свой HTTP/ретраи, если `reqwest`+`governor`+`backon` закрывают.

## Матрица версий (закрепить при старте)

- Rust: stable (edition 2021, MSRV зафиксировать при инициализации).
- Tauri: 2.x latest на момент старта.
- Node: LTS для фронт-сборки (Vite).
- Точные версии крейтов — в `Cargo.toml`, лок-файл в репозиторий.

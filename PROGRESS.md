# PROGRESS.md — журнал работ

Живой лог: что сделано, что дальше. Свежее — сверху.

## 2026-07-18 — Фаза 1: контракт + движок в mangadl-core (СДЕЛАНО, AC-1 почти весь зелёный)

Порт ядра 1:1 с Python (паритет прежде красоты). Новые модули `mangadl-core/src/`:
- `source.rs` — трейт `MangaSource` + DTO `SearchResult/ChapterInfo/PageInfo`
  (serde, `label()`), `SourceStatus`. Дословно по ARCHITECTURE §2.
- `error.rs` — `SourceError` (thiserror): Http/Parse/AuthRequired/Locked/
  Unreleased/NotImplemented + явный `Io` (в Python это OSError).
- `config.rs` — константы config.py 1:1 (RPS, ретраи, таймауты, quality).
- `http.rs` — порт ratelimit.py: `rate_limiter` (governor, burst=ceil(rps)),
  `parse_retry_after` (секунды/HTTP-дата, потолок 120с), `request_with_retries`
  (429/5xx, Retry-After, экспонента 1.6^n, 429 без подсказки ≥5с, ретраи
  транспортных ошибок). `RetryPolicy` с Default=Python (тесты дают малые паузы).
- `convert.rs` — `detect_ext` (magic-байты, порт `_detect_ext`) + `to_jpeg`
  (image). AVIF-декод за фичей `avif` (dav1d) — см. «Известное» ниже.
- `package.rs` — `safe_name` + `make_cbz` (zip, STORED) — порт packager.py.
- `storage.rs` — трейт `OutputStorage` (ARCHITECTURE §11.1) + `FsStorage`;
  ядро пишет на диск только через трейт (Android SAF станет второй реализацией).
- `download.rs` — `download_chapter_pages`: Semaphore+join_all, лимитер картинок,
  per-request заголовки (Referer), имена `NNN.ext` по сигнатуре, прогресс-колбэк.

Тесты (22, все зелёные; wiremock как mock-сервер из TESTING §5):
429+Retry-After (реальное ожидание), экспонента 5xx, отказ после max_retries,
404 без ретраев, token-bucket не превышает RPS (замер), parse_retry_after (4),
detect_ext на magic-байтах, PNG/WebP→JPEG валидный, скачка 2 страниц с Referer +
раскладка original/ + CBZ, битая страница роняет скачку (как gather).

`cargo fmt --check`, `clippy -D warnings`, `cargo test` — зелёные.

**Известное / хвосты AC-1:**
- [ ] AVIF→JPEG: код готов (`to_jpeg` формат-агностичен), тест за фичей `avif`,
  но dav1d на этой машине не собран (нет pkg-config/системной либы) — это ровно
  spike Фазы 1b. reqwest 0.13: фича `query` нужна для `.query()` (добавлена).
- [ ] Android-изоляция: локально нет NDK; в CI добавлен job `android-core`
  (`cargo check -p mangadl-core --target aarch64-linux-android`) — подтвердится
  первым push. Риск: aws-lc-sys (rustls) под NDK; если упрётся — сменить
  TLS-провайдер на ring.
- ponytail: backon в ретраях не используется (ручной цикл = построчный паритет
  с Python); get_json/get_text-обёртки появятся с первым источником (Фаза 2).

Дальше — Фаза 1b (AVIF/NDK spike) или Фаза 2 (реестр + агрегатор + senkuro/liblib).

## 2026-07-18 — Фаза 0: каркас cargo workspace (СДЕЛАНО, AC-0 зелёный)

Пользователь дал «да» на исполнение — спека в работе. Создан `mangadl/`:
- Крейты `mangadl-core` (lib, без Tauri), `mangadl-cli`, `mangadl-tauri` (bin) —
  компилируются; cli/tauri зависят от core.
- Версии зафиксированы: Rust 1.96 stable (`rust-toolchain.toml`, MSRV в
  workspace), крейты STACK.md подключены к core и запинены в `Cargo.lock`
  (tokio 1.53, reqwest 0.13.4 rustls, serde, thiserror 2, governor 0.10,
  scraper, image 0.25, zip 8, tracing, chrono, directories, backon).
  Внимание: в reqwest 0.13 фича называется `rustls`, не `rustls-tls`.
- CI `.github/workflows/ci.yml`: fmt-check + clippy `-D warnings` + build + test
  на PR/push (paths-фильтр `mangadl/**`).
- **ponytail:** зависимость `tauri` отложена до Фазы 4 (`cargo tauri init`) —
  пустому крейту вебвью-стек не нужен.
- Проверено локально: `cargo build`, `cargo clippy -D warnings`, `cargo fmt
  --check`, `cargo test` — зелёные. **AC-0 выполнен.**

Дальше — Фаза 1: `source.rs` (трейт+DTO), `error.rs`, `http.rs`, `convert.rs`,
`package.rs`, `download.rs` + mock-тесты (AC-1).

## 2026-07-18 — Спека миграции на Tauri + Rust (черновик на утверждение)

Собрана через graphify (граф кодовой базы: 330 AST-узлов, god-nodes = мультисорс-
контракт) + spec-pilot (порядок: интервью→спека→делегирование→проверка). Документы
в `spec/migration-tauri-rust/`: README, PRD, STACK, ARCHITECTURE, TZ, TESTING,
MIGRATION-PLAN. Ключевое: целевая crate-раскладка (ядро отдельно от Tauri), трейт
`MangaSource` 1:1 с Python, **кастомные тест-инструменты** (per-site GUI-режим со
switcher’ом, `doctor` health-чек, CLI `test-source/test-all/record`, golden-фикстуры,
mock-сервер). **Статус: НЕ УТВЕРЖДЕНО — код не переписывается до явного «да»**
(spec-pilot Гард 2). Открытые вопросы — PRD §7 (фронт-фреймворк, целевые ОС, судьба
токен-окна).

## 2026-07-18 — Мультисорс-ядро + захват токенов

### Сделано
- **Разведка 20 сайтов** из ТЗ — см. `docs/SITES.md` (эндпоинты, статусы).
- **Мультисорс-ядро** `mangalib_dl/sources/`:
  - `base.MangaSource` — единый контракт (search/get_chapters/get_pages) + DTO.
  - `registry.py` — переключение между источниками по id.
  - `aggregator.py` — поиск по всем, группировка одинаковых тайтлов, выбор
    источника с максимумом уникальных глав («самый актуальный»).
  - `download.py` — скачивание страниц по абсолютным URL.
  - `cli.py` — `search` / `download` / `sources`.
- **Адаптеры (verified):** mangalib, yaoilib, hentailib, ranobelib, animelib
  (семейство *Lib на общем `api.cdnlibs.org`), remanga, senkuro, inkstory/manga.ovh,
  mangahub. **unverified:** mangadex (из этой сети блок). **meta-only:** shikimori.
- **Заглушки (разведаны):** readmanga, mangabuff, newmanga, desu, mangapoisk,
  comx, mangaplus, webtoons — видны в реестре со статусом `stub` и заметкой.
- **Dev-окно захвата токенов** `token_window.py` (QtWebEngine): логин на сайте →
  перехват `Bearer` из запросов + запасной разбор localStorage → `tokens.json`.
- **Тесты** `tests/` — 12 passed (нормализация, группировка, выбор best, парсеры).
- **api.py** параметризован `api_base`/`site_id` — обратно совместимо (старый
  MangaLib UI/CLI работают без изменений).
- **Документация**: CLAUDE.md, docs/SITES.md, docs/ARCHITECTURE.md.

### Проверено вживую
- Кросс-сайт группировка «Берсерк»: senkuro+inkstory → best senkuro (50 гл.).
- Полный путь скачивания через Senkuro: search→chapters(700)→pages(24)→файлы на диск.
- Старые модули MangaLib импортируются и конструируются с дефолтами.

### Дальше (не сделано)
- [ ] Реализовать адаптеры-заглушки (начать с webtoons/readmanga — доступны).
- [ ] Проверить mangadex/newmanga/desu/mangapoisk на не-заблокированной сети.
- [ ] Мультисорс в UI (сейчас UI трогать нельзя — только CLI).
- [ ] Кэш результатов поиска (повторный enrich дорогой).
- [ ] Порог похожести названий (rapidfuzz), если склейка начнёт мешать.
- [ ] Решение по стеку — см. раздел ниже / отдельное предложение.

## Ранее
- MangaLib-загрузчик: PySide6 GUI + CLI, ветки перевода, CBZ, ретраи. (см. git)

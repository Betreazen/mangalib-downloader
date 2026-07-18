# PROGRESS.md — журнал работ

Живой лог: что сделано, что дальше. Свежее — сверху.

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

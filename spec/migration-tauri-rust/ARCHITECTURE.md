# ARCHITECTURE.md — целевая архитектура (Tauri 2 + Rust)

Проектируется как прямой перенос уже существующего мультисорс-ядра
(`mangalib_dl/sources/`) на Rust с сохранением контракта. Названия трейтов/полей
намеренно повторяют Python — чтобы паритет проверялся построчно.

## 1. Раскладка (cargo workspace)

Один workspace, ядро отделено от оболочки — ядро тестируется и запускается без Tauri
(как сейчас `mangalib_dl` не тянет PySide6).

```
mangadl/                        # cargo workspace
├── Cargo.toml                  # [workspace] members
├── crates/
│   ├── mangadl-core/           # ← ЯДРО, без Tauri (аналог mangalib_dl.sources)
│   │   ├── src/
│   │   │   ├── lib.rs
│   │   │   ├── source.rs        # trait MangaSource + DTO (god-nodes!)
│   │   │   ├── error.rs         # SourceError и потомки (thiserror)
│   │   │   ├── http.rs          # общий reqwest-клиент + ретраи + rate-limit
│   │   │   ├── registry.rs      # реестр источников (switch по id)
│   │   │   ├── aggregator.rs    # поиск по всем + группировка + best
│   │   │   ├── download.rs      # скачивание страниц по абсолютным URL
│   │   │   ├── convert.rs       # AVIF→JPEG (image), детекция формата
│   │   │   ├── package.rs       # CBZ, safe_name
│   │   │   ├── tokens.rs        # tokens.json (dev)
│   │   │   └── sources/
│   │   │       ├── mod.rs
│   │   │       ├── liblib.rs     # семейство *Lib (site_id 1..5)
│   │   │       ├── remanga.rs
│   │   │       ├── senkuro.rs    # GraphQL POST
│   │   │       ├── inkstory.rs   # inkstory + manga.ovh
│   │   │       ├── mangahub.rs   # scraper (HTML)
│   │   │       ├── mangadex.rs
│   │   │       ├── shikimori.rs  # meta-only
│   │   │       └── stubs.rs
│   │   ├── tests/               # офлайн-тесты на фикстурах (см. TESTING.md)
│   │   └── fixtures/            # записанные ответы API/HTML
│   │
│   ├── mangadl-cli/            # headless CLI (аналог sources/cli.py + doctor/test)
│   │   └── src/main.rs
│   │
│   └── mangadl-tauri/          # оболочка: IPC-команды + встроенный фронт
│       ├── src/
│       │   ├── main.rs
│       │   ├── commands.rs      # #[tauri::command] обёртки над ядром
│       │   ├── devtools.rs      # per-site тест-режим (см. TESTING.md)
│       │   └── token_capture.rs # захват Bearer из вебвью
│       ├── tauri.conf.json
│       └── ui/                  # Svelte + Vite фронтенд
│           ├── src/
│           └── package.json
└── ...
```

## 2. Несущий контракт — `source.rs` (god-nodes)

Прямое отражение `sources/base.py`. Эти типы — самые связные в графе, менять их
семантику нельзя.

```rust
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SearchResult {
    pub source_id: String,
    pub manga_id: String,
    pub title: String,
    pub alt_titles: Vec<String>,
    pub url: String,
    pub cover: String,
    pub chapters_count: Option<u32>,
    #[serde(default)] pub extra: serde_json::Value,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ChapterInfo {
    pub chapter_id: String,
    pub volume: String,
    pub number: String,
    pub name: String,
    pub team: String,
    pub branch_id: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PageInfo {
    pub index: u32,
    pub url: String,
    pub headers: HashMap<String, String>, // напр. Referer
}

#[async_trait::async_trait]
pub trait MangaSource: Send + Sync {
    fn id(&self) -> &'static str;
    fn name(&self) -> &'static str;
    fn base_url(&self) -> &'static str;
    fn can_download(&self) -> bool { true }
    fn status(&self) -> SourceStatus { SourceStatus::Verified }

    async fn search(&self, query: &str, limit: usize) -> Result<Vec<SearchResult>, SourceError>;
    async fn get_chapters(&self, manga_id: &str) -> Result<Vec<ChapterInfo>, SourceError>;
    async fn get_pages(&self, manga_id: &str, chapter: &ChapterInfo)
        -> Result<Vec<PageInfo>, SourceError>;
}
```

`label()` (Python `ChapterInfo.label`) → метод/хелпер `fn label(&self) -> String`.

## 3. Ошибки — `error.rs`

```rust
#[derive(thiserror::Error, Debug)]
pub enum SourceError {
    #[error("{0}: сеть/HTTP: {1}")] Http(String, String),
    #[error("{0}: разбор ответа: {1}")] Parse(String, String),
    #[error("{0}: требуется авторизация")] AuthRequired(String),
    #[error("{0}: платная глава")] Locked(String),
    #[error("{0}: ещё не вышла")] Unreleased(String),
    #[error("{0}: не реализовано ({1})")] NotImplemented(String, String),
}
```

Отражает `MangaLibError`/`LockedChapterError`/`UnreleasedChapterError`/`AuthRequiredError`.

## 4. HTTP + rate-limit + ретраи — `http.rs`

Единый на приложение `reqwest::Client` (пул соединений). Обёртка `get_json` /
`get_text` / `post_json` с:
- `governor`-лимитером (RPS как в `config`),
- ретраями на `{429,500,502,503,504}` с уважением `Retry-After` и экспонентой
  (порт `request_with_retries`),
- поддержкой per-request заголовков (Referer для картинок).

## 5. Реестр и агрегатор

- `registry.rs`: `fn all_sources(tokens) -> Vec<Box<dyn MangaSource>>` +
  `fn create(id, token) -> Option<Box<dyn MangaSource>>`. Порядок = приоритет.
  Заглушки возвращают `NotImplemented`.
- `aggregator.rs`: порт `Aggregator`:
  - `search_all(query)` — `futures::future::join_all` по источникам; сбой одного
    не роняет остальных (собираем в `on_error`).
  - `group()` — склейка по нормализованному названию (лат+кир, без пунктуации).
  - `enrich_counts()` — досчёт уникальных глав по `(volume, number)`.
  - `AggregatedTitle::best()` — максимум глав.

  **Инвариант (перенести дословно):** «актуальнее» = уникальные главы по
  `(том, номер)`, НЕ по строкам веток. Это защищённый бизнес-правилом момент —
  в тестах закрепить (как `test_best_picks_source_with_most_chapters`).

## 6. Скачивание, конвертация, упаковка

- `download.rs`: качает `PageInfo` в `chapter_dir/original/`, параллельность через
  `tokio::sync::Semaphore`, лимитер картинок. Порт `download_chapter_pages`.
- `convert.rs`: детекция формата по сигнатуре (порт `_detect_ext`), AVIF/WebP/PNG →
  JPEG через `image`. Кладёт в `converted/`.
- `package.rs`: `zip` → `… [original].cbz` / `… [converted].cbz`; `safe_name`
  (Windows-безопасные имена).

## 7. Захват токенов из вебвью — `token_capture.rs`

Аналог `token_window.py` (QtWebEngine) на Tauri. **Решение D3: один путь —
webview + чтение хранилища через JS** (одинаково на desktop и Android; перехват
HTTP-заголовков НЕ делаем — лишняя платформенная сложность).

- Webview (окно на desktop / экран на Android) грузит страницу логина источника
  (URLы из `LOGIN_URLS`). Пользователь логинится/регистрируется как обычно.
- После входа — инъекция скрипта / `eval`, читающий `localStorage`,
  `sessionStorage` и доступные cookie; ищем `eyJ…`-JWT (как в текущем
  `token_window._show_storage`). Результат — через IPC-событие в основной UI.
- Найденный токен → `tauri-plugin-store` (`tokens.json`), агрегатор подхватывает.

> Прод-режим: токены мастер-аккаунтов вшиваются через конфиг/ENV, экран логина
> скрыт. Это dev-инструмент (см. PRD не-цели).

## 8. IPC-контракт (Tauri commands) — `commands.rs`

Фронт общается с ядром только через эти команды (тонкие обёртки). Контракт
фиксируется тестами (TESTING.md §5).

| Команда | Вход | Выход |
|---------|------|-------|
| `search_all` | `query, source_ids?` | `Vec<AggregatedTitle>` |
| `enrich_title` | `title` | `AggregatedTitle` (с числами глав) |
| `list_sources` | — | `Vec<SourceMeta>` (id/name/status/can_download) |
| `get_chapters` | `source_id, manga_id` | `Vec<ChapterInfo>` |
| `download_chapters` | `source_id, manga_id, chapter_ids, opts` | стрим прогресса (event) |
| `save_token` / `list_tokens` | `source_id, token` | ok |
| `dev_run_site_test` | `source_id, query` | `SiteTestReport` (см. TESTING.md) |
| `doctor` | — | `Vec<SourceHealth>` |

Прогресс скачивания — через `emit`/`Channel` (событие `download://progress`),
как `ProgressFn` в Python.

## 9. Фронтенд (Svelte 5)

Экраны:
1. **Поиск** — строка запроса → `search_all` → карточки сгруппированных тайтлов;
   у каждого «⭐ лучший источник: N глав, перевод такой-то» + разворот по всем сайтам.
2. **Тайтл** — список глав выбранного (best) источника, выбор диапазона, кнопка скачать.
3. **Загрузки** — прогресс по событиям.
4. **Настройки/токены** — кнопка «Открыть браузер логина» → окно захвата.
5. **Dev / QA** (скрыт, включается режимом — см. TESTING.md) — per-site тест.

Длинные списки глав — виртуализированы.

## 10. Соответствие Python → Rust (карта паритета)

| Python (`mangalib_dl/…`) | Rust (`mangadl-core/…`) | Сообщество графа |
|---|---|---|
| `sources/base.py` | `source.rs`, `error.rs` | 5, 8 |
| `sources/registry.py` | `registry.rs` | 6 |
| `sources/aggregator.py` | `aggregator.rs` | 6 |
| `sources/download.py` | `download.rs` | 1 |
| `downloader.py` (`_detect_ext`, convert) | `convert.rs` | 1 |
| `packager.py` | `package.rs` | 1 |
| `ratelimit.py` | `http.rs` | 0/3 |
| `sources/liblib.py` (+`api.py`) | `sources/liblib.rs` | 4, 0, 3 |
| `sources/remanga.py` | `sources/remanga.rs` | 7 |
| `sources/senkuro.py` | `sources/senkuro.rs` | 5 |
| `sources/inkstory.py` | `sources/inkstory.rs` | 9 |
| `sources/mangahub.py` | `sources/mangahub.rs` | 7 |
| `sources/mangadex.py` / `shikimori.py` / `stubs.py` | одноимённые | 5 |
| `sources/token_window.py` | `mangadl-tauri/token_capture.rs` | — |
| `gui.py` / `cli.py` (PySide6) | `mangadl-tauri/ui` (Svelte) | 2, 3 |
| `storage.py` | `tokens.rs` + `tauri-plugin-store` | 11 |

Импорт-циклы (`__init__` ↔ `api`/`models`), отмеченные графом, в Rust исчезают
естественно — модули не создают циклов через `lib.rs`.

## 11. Кроссплатформенность: Windows + Android (решение D2)

Один `mangadl-core` и один Svelte-фронт на обе платформы. Платформенные различия
изолированы в `mangadl-tauri` за `#[cfg(...)]` и в тонком слое хранилища — **ядро
платформонезависимо** (иначе Android-сборка сломается).

### 11.1 Абстракция хранилища — `storage` (порт `storage.py` + платформа)

```rust
#[async_trait]
pub trait OutputStorage: Send + Sync {
    async fn write_page(&self, chapter_dir: &str, name: &str, bytes: &[u8]) -> Result<()>;
    async fn make_cbz(&self, chapter_dir: &str, out_name: &str) -> Result<()>;
    fn exists(&self, chapter_dir: &str) -> bool; // для skip-existing/докачки
}
```

- **Desktop:** реализация поверх обычного пути (как сейчас) — `original/`,
  `converted/`, CBZ рядом.
- **Android:** реализация поверх выбранной SAF-папки / app-dir через
  `tauri-plugin-fs`. Та же логическая раскладка, но корень — разрешённый URI.
  «Произвольный путь» на Android недоступен — пользователь один раз выбирает
  папку назначения, дальше пишем в неё.

Ядро (`download.rs`, `package.rs`) работает через трейт, не зная платформы.

### 11.2 Конвертация AVIF (риск, решение отложено на Фазу 1b)

- **Desktop:** AVIF→JPEG через `image`+`dav1d`, как в PRD.
- **Android:** если `dav1d` под NDK собирается — то же; если сложно — по умолчанию
  **хранить оригинал AVIF без конвертации** (Android и большинство читалок его
  показывают), конвертацию оставить опцией. Решается замером на Фазе 1b, не
  блокирует остальную миграцию.

### 11.3 Фоновая скачка на Android

Длинная скачка не должна убиваться ОС: foreground-service / keep-awake на время
загрузки; чанкование; докачка (skip-existing уже в логике) даёт устойчивость к
обрывам. Прогресс — те же события `download://progress`.

### 11.4 Токены и dev-панель на мобиле

Экран webview-логина (§7) и per-site тест-панель (TESTING §1) доступны и в
Android-сборке (тот же Svelte-роут `devtools`, включается тем же режимом). На
телефоне это же — способ проверить конкретный сайт «в поле».

### 11.5 Что остаётся строго в ядре (платформонезависимо)

`source.rs`, `error.rs`, `http.rs`, `registry.rs`, `aggregator.rs`, все
`sources/*` — используют только `reqwest`/`serde`/`scraper`/`governor`, которые
собираются под NDK. Запрет: никаких `std::fs`-путей и desktop-API в ядре — только
через трейт `OutputStorage`.

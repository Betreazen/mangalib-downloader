# ТЗ — техническое задание на миграцию

Помодульно, фазами. У каждой фазы — вход, работы, критерий приёмки (Acceptance).
Порядок фаз = порядок безопасной сборки: сначала контракт и движок, потом
источники пачками, GUI и токены в конце. Каждая фаза оставляет систему рабочей.

Обозначения: **AC** — acceptance criteria; ссылки на файлы — по
[ARCHITECTURE.md](ARCHITECTURE.md).

---

## Фаза 0 — Каркас workspace

**Работы:**
- Создать cargo workspace `mangadl/` с крейтами `mangadl-core`, `mangadl-cli`,
  `mangadl-tauri` (пустые, компилируются).
- Настроить `clippy`, `rustfmt`, базовый CI (сборка + линт).
- Зафиксировать версии (Rust stable, Tauri 2.x, крейты из STACK.md), лок-файлы в git.

**AC-0:** `cargo build` и `cargo clippy` зелёные; CI гоняет их на PR.

---

## Фаза 1 — Несущий контракт + движок (без источников)

**Работы:**
- `source.rs`: трейт `MangaSource` + DTO `SearchResult/ChapterInfo/PageInfo`
  (serde) — дословно по ARCHITECTURE §2. `ChapterInfo::label()`.
- `error.rs`: `SourceError` (thiserror) — все варианты Python-иерархии.
- `http.rs`: общий `reqwest::Client`, `governor`-лимитер, ретраи 429/5xx/Retry-After
  (порт `ratelimit.py`), per-request заголовки.
- `convert.rs`: `detect_ext` (сигнатуры) + AVIF/WebP/PNG→JPEG (`image`).
- `package.rs`: CBZ (`zip`) + `safe_name`.
- `download.rs`: параллельная скачка `PageInfo` (`Semaphore` + лимитер), пишет
  через трейт `OutputStorage` (ARCHITECTURE §11.1), не через `std::fs` напрямую.
- **Требование кроссплатформенности:** ядро НЕ использует desktop-only API —
  только `reqwest`/`serde`/`governor`/`image`/`zip` (собираются под Android NDK).

**AC-1:**
- Mock-сервер (TESTING §5): 429/Retry-After и экспонента ретраев — как в Python.
- Token-bucket не превышает RPS (замер).
- `detect_ext` покрыт юнит-тестами на magic-байтах (порт Python-теста).
- AVIF→JPEG конвертация на эталонной картинке даёт валидный JPEG (desktop).
- `mangadl-core` компилируется под target `aarch64-linux-android` (без линковки
  desktop-крейтов) — проверка изоляции платформы.

---

## Фаза 1b — Spike: AVIF/NDK под Android (риск-разведка)

Короткая проверка до массового портирования: собирается ли AVIF-декод под
Android NDK.

**Работы:** собрать `image`+`dav1d` под `aarch64-linux-android`; если тяжело —
зафиксировать fallback «на мобиле хранить оригинал AVIF без конвертации»
(ARCHITECTURE §11.2), сделать конвертацию опцией платформы.

**AC-1b:** решение зафиксировано — либо AVIF-конвертация работает на Android,
либо включён fallback-режim «оригиналы без конвертации». Не блокирует Фазы 2–3.

---

## Фаза 2 — Реестр + агрегатор + 2 эталонных источника

Берём два **разнотипных** источника для проверки контракта: **Senkuro** (GraphQL,
стабилен) и **семейство *Lib** (JSON, `site_id`).

**Работы:**
- `registry.rs`: реестр + `create(id, token)` + `all_sources`.
- `aggregator.rs`: `search_all` (join_all, сбой-изоляция) → `group` (нормализация
  названий) → `enrich_counts` (уникальные главы по `(vol,num)`) → `best`.
- `sources/senkuro.rs`, `sources/liblib.rs` (site_id 1..5, общий `api.cdnlibs.org`).
- `tokens.rs` + чтение сохранённых токенов агрегатором.

**AC-2 (паритет с Python — критично):**
- `test_best_picks_source_with_most_chapters`, `test_group_merges…`,
  `normalize_title` — порт Python-тестов, зелёные.
- **DoD-1:** на 5 эталонных тайтлах `search_all`+`best` совпадает с Python-версией
  (те же источники, те же числа глав). Сверка через `mangadl-cli search` vs
  `python -m mangalib_dl.sources.cli search`.
- Golden-фикстуры Senkuro/*Lib записаны и проходят офлайн (TESTING §4).

---

## Фаза 3 — Остальные источники (пачками)

Портировать по образцу Фазы 2, каждый с чистой `parse_*` и фикстурой:

- **Пачка A (JSON):** `remanga.rs`, `inkstory.rs` (inkstory+manga.ovh), `mangadex.rs`.
- **Пачка B (HTML/meta):** `mangahub.rs` (`scraper` вместо регэкспов — но поведение
  1:1), `shikimori.rs` (meta-only, `can_download=false`).
- **`stubs.rs`:** заглушки (readmanga/mangabuff/newmanga/desu/mangapoisk/comx/
  mangaplus/webtoons) — видны в реестре, методы → `NotImplemented`.

**AC-3:**
- **DoD-2:** per-site харнесс (`test-source`) для каждого `verified` даёт корректный
  pipeline (search→chapters→pages→download) на эталонном тайтле.
- Golden-фикстуры для каждого источника; офлайн-парсер-тесты зелёные.
- `doctor` показывает верный статус по всем (verified/unverified/stub).

---

## Фаза 4 — Оболочка Tauri + IPC + фронт

**Работы:**
- `commands.rs`: все команды из ARCHITECTURE §8 (тонкие обёртки над ядром).
- Прогресс скачки через события (`download://progress`).
- Svelte-фронт: экраны Поиск / Тайтл / Загрузки / Настройки (ARCHITECTURE §9),
  виртуализация длинных списков глав. **Адаптивная вёрстка** (desktop: мастер-
  деталь; телефон: одна колонка, тач-таргеты) — один фронт на обе платформы.
- `OutputStorage`: desktop-реализация (прямой путь) + нативный выбор папки.

**AC-4:**
- IPC-контракт тесты (TESTING §6) зелёные.
- Ручной прогон: поиск → выбор тайтла → скачка → файлы на диске (те же
  `original/`+`converted/`+CBZ, что Python — **DoD-3**).
- UI корректно раскладывается на узком экране (мобильный брейкпоинт).

---

## Фаза 5 — Dev-инструменты тестирования (ключевое требование)

**Работы:**
- `devtools.rs` + Svelte QA-роут: **per-site тест-панель** со switcher’ом
  источника, шагами pipeline, таймингами, превью первой страницы, «Save as fixture»
  (TESTING §1).
- Включение: `--mode site-test` / `MANGADL_MODE=site-test` / фича `devtools` /
  хоткей — все способы из TESTING §1.
- `mangadl-cli`: `test-source`, `test-all`, `record`, `doctor` (TESTING §2–4).
- Nightly-CI матрицей по сайтам + офлайн-гейт на PR.

**AC-5 (DoD-5, DoD-7):**
- Приложение запускается в режиме `site-test` и прогоняет полный pipeline
  выбранного сайта с отчётом.
- `cargo test` (офлайн) зелёный; `--features live` прогоняет per-site smoke.
- `doctor` даёт корректный ненулевой exit при падении `verified`-сайта.

---

## Фаза 6 — Захват токенов из вебвью

**Работы:**
- `token_capture.rs` + окно логина (ARCHITECTURE §7): путь A (перехват заголовка)
  и путь B (чтение localStorage через eval), сохранение в store.
- URLы логина источников (порт `LOGIN_URLS`).

**AC-6:**
- Для *Lib-семейства пойман валидный `Bearer` после логина; агрегатор его
  использует (лицензированный/18+ тайтл начинает отдавать главы).

---

## Фаза 7 — Сборка (Windows + Android), паритет-гейт, архивирование Python

**Работы:**
- **Windows:** сборка десктоп-бинаря.
- **Android:** `OutputStorage` поверх SAF/app-dir (ARCHITECTURE §11.1), foreground-
  service для скачки (§11.3), выбор папки через системный пикер; сборка APK
  (`cargo tauri android build`), подпись.
- Прогон полного паритет-чеклиста (MIGRATION-PLAN) на обеих платформах.
- Python-версию пометить архивной (эталон сохранить до закрытия всех DoD — D4).

**AC-7 (DoD-6):** Windows-бинарь ставится и работает на чистой машине без Python;
паритет-чеклист зелёный.
**AC-7b (DoD-8):** APK ставится на устройство/эмулятор; поиск → тайтл → скачка →
файлы в выбранной папке; мультисорс-поиск и per-site тест-панель работают.

---

## Сквозные требования (ко всем фазам)

- **Паритет прежде красоты.** Имена/поля/пороги переносим 1:1; рефакторинг — потом.
- **Каждый нетривиальный парсер** имеет чистую `parse_*` + фикстуру.
- **Инвариант «актуальнее = уникальные главы по (том,номер)»** закреплён тестом.
- **Один сбойный сайт не роняет поиск** (изоляция ошибок в агрегаторе).
- **Секреты не в репозитории** (токены — в store/ENV; фикстуры чистить от токенов).
- **Не трогать формат вывода на диск** (совместимость с уже скачанным).
- **Verify-слой** (spec-pilot Шаг 4): перед сдачей фазы — прогон её AC.

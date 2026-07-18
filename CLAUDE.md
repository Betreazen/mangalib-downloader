# CLAUDE.md — mangalib-manga-downloader

Гид по проекту для Claude Code и людей. Держи коротким и актуальным.

## Что это

Загрузчик глав манги. Начинался как клиент MangaLib (PySide6 GUI + CLI),
сейчас расширяется в **мультисорс**: поиск по многим сайтам сразу и скачивание
с того, где перевод/выпуск самый актуальный (больше всего глав).

## Карта кода

```
mangalib_dl/
  api.py            MangaLib-клиент (переиспользуется семейством *Lib через api_base/site_id)
  models.py         Chapter/Branch/Manga/Page (MangaLib)
  downloader.py     Скачивание страниц по CDN MangaLib (относительные пути)
  service.py        Оркестрация скачивания выбранной ветки перевода
  gui.py / cli.py   UI MangaLib — НЕ ТРОГАЕМ без явной просьбы
  ratelimit.py      Токен-бакет + ретраи (429/5xx/Retry-After)
  packager.py       CBZ + безопасные имена файлов
  storage.py        Конфиг/токен пользователя (~/.mangalib_downloader)
  sources/          ← МУЛЬТИСОРС-ЯДРО (новое)
    base.py         MangaSource + SearchResult/ChapterInfo/PageInfo
    registry.py     Реестр источников: switch между сайтами по id
    aggregator.py   Поиск по всем + группировка + выбор best (макс. глав)
    download.py     Скачивание страниц по абсолютным URL (мультисорс-путь)
    cli.py          python -m mangalib_dl.sources.cli search|download|sources
    token_window.py Dev-окно: логин на сайте -> захват bearer-токена
    token_store.py  tokens.json в конфиг-папке (не в репозитории)
    liblib/remanga/senkuro/inkstory/mangahub/mangadex/shikimori.py — адаптеры
    stubs.py        Сайты из ТЗ без адаптера (видны, но поднимают SourceError)
```

## Как запускать

```bash
# мультисорс
python -m mangalib_dl.sources.cli sources            # список сайтов и статусы
python -m mangalib_dl.sources.cli search "berserk"   # найти + показать лучший
python -m mangalib_dl.sources.cli download "berserk" --out ./downloads --limit 3
python -m mangalib_dl.sources.token_window           # захват токенов (dev, GUI)

# тесты
python -m pytest tests/ -q

# старый MangaLib UI (без изменений)
python app.py
```

## Ключевые решения

- **Идентичность источника** — `MangaSource.id`. Реестр (`registry.py`) — единая
  точка переключения; агрегатор не знает про конкретные модули.
- **«Актуальнее» = больше уникальных глав** (по (volume, number), не по строкам
  веток), см. `aggregator._unique_chapter_count`.
- **Семейство *Lib** (mangalib/yaoilib/hentailib/ranobelib/animelib) делит один
  API `api.cdnlibs.org`; различие — `site_id`. Переиспользуем `MangaLibClient`.
- **Токены** — только dev-удобство. В проде: мастер-аккаунт на сайт (см. SITES.md).

## Скиллы и правила (что применяем)

Активны глобально (в `~/.claude/skills`, `~/.claude/rules`), релевантны здесь:

- **ponytail** — писать минимальный работающий код (применялось при разработке ядра).
- **ECC python-rules** — PEP8, type hints, pytest, black/ruff, immutability.
- **spec-pilot** — для крупных новых фич собирать спеку до кодинга.
- **graphify** — навигация по кодовой базе как по графу.

Неприменимо к проекту: `Anthropic-Cybersecurity-Skills` (offensive-security,
не относится к загрузчику манги) — намеренно не подключались.

## Конвенции

- Комментарии и сообщения — по-русски (как в существующем коде).
- Python: type hints, dataclasses для DTO, async/httpx для сети.
- Один сбойный сайт не должен ронять поиск (agg ловит ошибки по источнику).
- Не трогать `gui.py`/`cli.py`/`service.py` без явной просьбы.

См. также: `PROGRESS.md`, `docs/SITES.md`, `docs/ARCHITECTURE.md`.

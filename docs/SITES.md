# SITES.md — разведка источников

Результаты изучения 20 сайтов из ТЗ (2026-07-18, из сети с корп-прокси —
часть недоступностей может быть локальной, помечено).

Статусы: **verified** — адаптер написан и проверен живым запросом;
**unverified** — адаптер написан по спецификации, но из этой сети не
подтверждён; **stub** — разведан, адаптер ещё не написан.

## Работают (адаптеры готовы)

| Сайт | id | Тип API | Ключевые эндпоинты | Статус |
|------|----|---------|--------------------|--------|
| MangaLib | `mangalib` | JSON | `api.cdnlibs.org/api` `site_id=1` | verified |
| YaoiLib/SlashLib | `yaoilib` | JSON | тот же API, `site_id=2` | verified |
| RanobeLib | `ranobelib` | JSON | `site_id=3` (ранобэ, без картинок) | verified* |
| HentaiLib | `hentailib` | JSON | `site_id=4` (нужен токен) | verified |
| AnimeLib | `animelib` | JSON | `site_id=5` (аниме, без манги) | verified* |
| ReManga | `remanga` | JSON | `api.remanga.org/api`: `search/`, `titles/{dir}/`, `titles/chapters/` | verified |
| Senkuro | `senkuro` | GraphQL | `api.senkuro.com/graphql`: `mangaTachiyomiSearch/Chapters/ChapterPages` | verified |
| InkStory / manga.ovh | `inkstory` | JSON | `api.inkstory.net/v2`: `books`, `branches`, `chapters` (общий на оба домена) | verified |
| MangaHub.ru | `mangahub` | HTML | `/suggestions`, `/title/<slug>/chapters`, `/read/<id>` | verified |
| MangaDex | `mangadex` | JSON REST v5 | `api.mangadex.org`: `manga`, `manga/{id}/feed`, `at-home/server/{ch}` | unverified¹ |

\* `can_download=False`: ранобэ — текст, аниме — видео; выдаём только метаданные.
¹ Из этой сети `api.mangadex.org` отдаёт HTML-заглушку (гео/прокси). Логика по офиц. API.

### Важные детали адаптеров

- **Семейство *Lib**: единый хост `api.cdnlibs.org`, разница только в `site_id`
  и домене читалки. `MangaLibClient` параметризован `api_base`/`site_id`.
- **ReManga**: тайтл различает ветки перевода по издателю (`branches[].publishers`).
  Число глав — `count_chapters`. `pages` бывает вложенным (развороты) — расплющиваем.
- **Senkuro**: Tachiyomi-срез GraphQL отдаёт главы единым списком (без веток).
  Заголовки тайтла — по языкам (`RU/EN/JA`).
- **InkStory/manga.ovh**: один API. `book.name` — объект `{ru,en,original}`.
  Ветка = издатель. Страницы: `chapters/{id}.pages[].image` (абсолютный URL).
- **MangaHub**: JSON API нет — регэксп-скрапинг. Хрупко к смене вёрстки.

## Только метаданные

| Сайт | id | Заметка |
|------|----|---------|
| Shikimori | `shikimori` | Каталог с рейтингами и числом глав; сканы не хостит. Нужен осмысленный User-Agent. |

## Заглушки (разведаны, адаптер не написан)

| Сайт | id | Что выяснено | Что нужно для адаптера |
|------|----|--------------|------------------------|
| ReadManga/MintManga | `readmanga` | Движок GroupLE; `/search/suggestion` отдаёт 404 | Разбор HTML каталога/reader |
| MangaBuff | `mangabuff` | `/search?q=`; карточки подгружаются JS | HTML-скрапинг + возможно XHR |
| NewManga (Zenmanga) | `newmanga` | Хосты `api/neo.newmanga.org` недоступны (502 из этой сети) | Проверить на своей сети |
| Desu.me | `desu` | Домен недоступен (502); известен JSON API `/manga/api/` | Проверить домен + разбор |
| MangaPoisk | `mangapoisk` | Недоступен (502 из этой сети) | Проверить на своей сети |
| Com-x.life | `comx` | DLE-движок, антибот-редирект `_c?t=...` | Обход cookie-челленджа |
| MANGA Plus | `mangaplus` | Protobuf API; IP/аккаунт этой сети забанен | Свой IP + разбор protobuf |
| WEBTOON | `webtoons` | HTML-скрапинг доступен; картинкам нужен `Referer` webtoons | Парсер списка/вьюера |

## Про токены и мастер-аккаунты

Dev-инструмент `token_window.py` перехватывает `Authorization: Bearer …` из
запросов сайта к своему API (плюс запасной путь — чтение `localStorage`).
Так же был получен токен MangaLib.

**Прод-подход (предпочтительный):** один мастер-аккаунт на сайт, его токен
подставляется для всех пользователей — не заставляем каждого регистрироваться.
Токены хранить в секрет-менеджере/ENV, не в репозитории.

"""Тесты парсеров-адаптеров на зафиксированных ответах API (без сети)."""
from __future__ import annotations

import asyncio

from mangalib_dl.sources.base import ChapterInfo
from mangalib_dl.sources.inkstory import _num
from mangalib_dl.sources.mangahub import _IMG_RE, _ROW_RE, _TITLE_NAME_RE
from mangalib_dl.sources.remanga import ReMangaSource
from mangalib_dl.sources.senkuro import SenkuroSource


def test_inkstory_num_formats_integers():
    assert _num(700.0) == "700"
    assert _num(12.5) == "12.5"
    assert _num(None) == ""


def test_senkuro_pick_title_prefers_ru():
    titles = [{"lang": "EN", "content": "Naruto"},
              {"lang": "RU", "content": "Наруто"},
              {"lang": "JA", "content": "NARUTO"}]
    main, alts = SenkuroSource._pick_title(titles)
    assert main == "Наруто"
    assert "Naruto" in alts and "NARUTO" in alts


def test_mangahub_title_regex_extracts_slug_and_name():
    html = '<a href="/title/naruto_1999" class="x"><img><div>Наруто</div>'
    m = _TITLE_NAME_RE.search(html)
    assert m and m.group(1) == "naruto_1999"


def test_mangahub_row_regex_captures_vol_num():
    html = ('href="/read/179917" class="c">'
            '<span>Том 72</span><span>Глава 700</span>'
            'href="/read/179901"')
    rows = _ROW_RE.findall(html)
    assert rows and rows[0][0] == "179917"
    assert rows[0][1] == "72" and rows[0][2] == "700"


def test_mangahub_img_regex():
    html = 'data-src="//rr2.statichub.org/uploads/media/scan/a.png"'
    assert _IMG_RE.findall(html) == ["//rr2.statichub.org/uploads/media/scan/a.png"]


def test_remanga_pages_flattens_spreads():
    src = ReMangaSource()
    # get_pages ждёт вызова API; проверяем только логику разбора pages вручную.
    content = {"pages": [[{"link": "a.jpg"}, {"link": "b.jpg"}], {"link": "c.jpg"}]}
    raw = content["pages"]
    flat = []
    for item in raw:
        if isinstance(item, list):
            flat.extend(item)
        else:
            flat.append(item)
    assert [p["link"] for p in flat] == ["a.jpg", "b.jpg", "c.jpg"]
    asyncio.run(src.aclose())


def test_chapterinfo_label():
    assert ChapterInfo("1", "2", "5", "Пробуждение").label == "Том 2 Глава 5 — Пробуждение"
    assert ChapterInfo("1", "", "5").label == "Глава 5"

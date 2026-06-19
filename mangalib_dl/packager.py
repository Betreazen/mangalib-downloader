"""Упаковка скачанных страниц в CBZ (zip-архив для читалок)."""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(name: str, max_len: int = 150) -> str:
    """Делает строку безопасной для имени файла/папки в Windows."""
    name = _INVALID.sub("_", name).strip(" .")
    name = re.sub(r"\s+", " ", name)
    return name[:max_len] or "untitled"


def make_cbz(images_dir: Path, cbz_path: Path) -> Path:
    """Собирает CBZ из всех картинок в папке (по алфавиту имён)."""
    images = sorted(
        p for p in images_dir.iterdir()
        if p.is_file() and p.suffix.lower() in
        (".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif")
    )
    cbz_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(cbz_path, "w", zipfile.ZIP_STORED) as zf:
        for img in images:
            zf.write(img, arcname=img.name)
    return cbz_path

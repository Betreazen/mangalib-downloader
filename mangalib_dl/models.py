"""Модели данных MangaLib (без зависимости от UI)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import config


@dataclass
class Branch:
    """Ветка перевода главы (конкретная команда переводчиков)."""
    branch_id: int | None          # None означает «единственная ветка»
    teams: list[str] = field(default_factory=list)

    @property
    def team_label(self) -> str:
        names = [t for t in self.teams if t]
        return ", ".join(names) if names else config.UNSIGNED_LABEL


@dataclass
class Chapter:
    """Глава манги. Может содержать несколько веток-переводов."""
    volume: str
    number: str
    name: str
    branches: list[Branch] = field(default_factory=list)

    @property
    def label(self) -> str:
        base = f"Том {self.volume} Глава {self.number}"
        return f"{base} — {self.name}" if self.name else base

    def has_branch(self, branch_id: int | None) -> bool:
        return any(b.branch_id == branch_id for b in self.branches)

    def branch_ids(self) -> list[int | None]:
        return [b.branch_id for b in self.branches]

    def team_label_for(self, branch_id: int | None) -> str:
        """Команда(ы), переводившая именно эту главу в данной ветке."""
        for b in self.branches:
            if b.branch_id == branch_id:
                return b.team_label
        return ""

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "Chapter":
        branches: list[Branch] = []
        for b in data.get("branches", []) or []:
            # Данные MangaLib местами «грязные»: элемент ветки или команды
            # может быть строкой, а не объектом — иначе парсинг падает.
            if not isinstance(b, dict):
                continue
            teams: list[str] = []
            for t in (b.get("teams") or []):
                if isinstance(t, dict):
                    name = t.get("name")
                elif isinstance(t, str):
                    name = t
                else:
                    name = None
                if name:
                    teams.append(name)
            branches.append(Branch(branch_id=b.get("branch_id"), teams=teams))
        if not branches:
            branches.append(Branch(branch_id=None, teams=[]))
        return cls(
            volume=str(data.get("volume", "")),
            number=str(data.get("number", "")),
            name=(data.get("name") or "").strip(),
            branches=branches,
        )


@dataclass
class Page:
    """Одна страница главы."""
    index: int          # порядковый номер (1..N) для имени файла
    url_path: str       # относительный путь, напр. //manga/.../00.png_res.jpg
    width: int = 0
    height: int = 0


@dataclass
class Manga:
    """Метаданные тайтла."""
    slug: str
    name: str
    rus_name: str
    eng_name: str
    cover: str = ""

    @property
    def title(self) -> str:
        """Предпочитаем русское название, затем оригинальное."""
        return self.rus_name or self.name or self.eng_name or self.slug

    @classmethod
    def from_api(cls, slug: str, data: dict[str, Any]) -> "Manga":
        d = data.get("data", data)
        cover = ""
        c = d.get("cover")
        if isinstance(c, dict):
            cover = c.get("default") or c.get("thumbnail") or ""
        return cls(
            slug=slug,
            name=d.get("name", "") or "",
            rus_name=d.get("rus_name", "") or "",
            eng_name=d.get("eng_name", "") or "",
            cover=cover,
        )

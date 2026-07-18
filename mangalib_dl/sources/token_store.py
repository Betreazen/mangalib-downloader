"""Хранилище токенов источников: {source_id: bearer}. Только для dev-удобства.

Токены лежат в конфиг-папке пользователя, не в репозитории. В проде вместо
этого предполагается один мастер-аккаунт на сайт (см. заметку в SITES.md).
"""
from __future__ import annotations

import json
from pathlib import Path

from ..storage import CONFIG_DIR


def _path() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR / "tokens.json"


def load_tokens() -> dict[str, str]:
    p = _path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {k: v for k, v in data.items() if isinstance(v, str) and v}
    except (json.JSONDecodeError, OSError):
        return {}


def save_token(source_id: str, token: str) -> None:
    tokens = load_tokens()
    tokens[source_id] = token.strip()
    _path().write_text(json.dumps(tokens, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_token(source_id: str) -> None:
    tokens = load_tokens()
    tokens.pop(source_id, None)
    _path().write_text(json.dumps(tokens, ensure_ascii=False, indent=2), encoding="utf-8")

"""Хранение настроек и токена между запусками (в домашней папке пользователя)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".mangalib_downloader"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> dict[str, Any]:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_config(data: dict[str, Any]) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # Права только для владельца (где поддерживается).
        try:
            CONFIG_FILE.chmod(0o600)
        except OSError:
            pass
    except OSError:
        pass


def update_config(**values: Any) -> dict[str, Any]:
    cfg = load_config()
    cfg.update(values)
    save_config(cfg)
    return cfg


def clear_token() -> None:
    cfg = load_config()
    cfg.pop("token", None)
    save_config(cfg)

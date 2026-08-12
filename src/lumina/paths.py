"""Filesystem locations. Never write next to the executable — it may live in
Program Files, where the process has no write permission."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "Lumina"


def _env_dir(var: str, fallback: Path) -> Path:
    value = os.environ.get(var)
    return Path(value) if value else fallback


CONFIG_DIR = _env_dir("APPDATA", Path.home() / "AppData" / "Roaming") / APP_DIR_NAME
DATA_DIR = _env_dir("LOCALAPPDATA", Path.home() / "AppData" / "Local") / APP_DIR_NAME
LOG_DIR = DATA_DIR / "logs"

CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE = LOG_DIR / "lumina.log"


def resource_dir() -> Path:
    """Bundled read-only assets (icons, stylesheet)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "resources"
    return Path(__file__).resolve().parent / "resources"


def resource(name: str) -> str:
    return str(resource_dir() / name)


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

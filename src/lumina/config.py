"""Settings as one JSON file under %APPDATA%\\Lumina.

The v1 app kept schedules as pickled QVariant lists in the registry, which
silently lost data whenever the shape changed. A plain file is inspectable,
portable, and survives a reinstall.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field

from .paths import CONFIG_FILE, ensure_dirs

log = logging.getLogger(__name__)

CONFIG_VERSION = 2


@dataclass
class ScheduleRule:
    start: str = "22:00"     # HH:MM
    end: str = "06:00"
    value: int = 30          # target percent
    enabled: bool = True


@dataclass
class Config:
    version: int = CONFIG_VERSION
    sync: bool = False
    fade_enabled: bool = True
    fade_duration_ms: int = 2000
    minimize_to_tray: bool = True
    schedules: list[ScheduleRule] = field(default_factory=list)
    monitor_cache: list[dict] = field(default_factory=list)

    def to_json(self) -> str:
        data = asdict(self)
        return json.dumps(data, indent=2, ensure_ascii=False)

    @staticmethod
    def from_dict(data: dict) -> "Config":
        cfg = Config()
        cfg.sync = bool(data.get("sync", cfg.sync))
        cfg.fade_enabled = bool(data.get("fade_enabled", cfg.fade_enabled))
        cfg.fade_duration_ms = max(0, int(data.get("fade_duration_ms", cfg.fade_duration_ms)))
        cfg.minimize_to_tray = bool(data.get("minimize_to_tray", cfg.minimize_to_tray))
        cfg.schedules = [
            ScheduleRule(
                start=str(r.get("start", "22:00")),
                end=str(r.get("end", "06:00")),
                value=max(0, min(100, int(r.get("value", 30)))),
                enabled=bool(r.get("enabled", True)),
            )
            for r in data.get("schedules", []) if isinstance(r, dict)
        ]
        cfg.monitor_cache = [m for m in data.get("monitor_cache", []) if isinstance(m, dict)]
        return cfg


def load() -> Config:
    try:
        with open(CONFIG_FILE, encoding="utf-8") as handle:
            return Config.from_dict(json.load(handle))
    except FileNotFoundError:
        return Config()
    except (json.JSONDecodeError, ValueError, TypeError, OSError) as exc:
        # A corrupt file must not stop the app from starting; keep it for
        # inspection and carry on with defaults.
        log.warning("Config unreadable (%s), starting from defaults", exc)
        _quarantine()
        return Config()


def save(cfg: Config) -> None:
    ensure_dirs()
    tmp = CONFIG_FILE.with_suffix(".json.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(cfg.to_json())
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, CONFIG_FILE)   # atomic: no half-written config
    except OSError as exc:
        log.error("Could not save config: %s", exc)


def _quarantine() -> None:
    try:
        os.replace(CONFIG_FILE, CONFIG_FILE.with_suffix(".json.bad"))
    except OSError:
        pass

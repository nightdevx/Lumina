"""Run at logon via HKCU\\...\\Run - no admin rights, no scheduled task."""
from __future__ import annotations

import logging
import sys
import winreg
from pathlib import Path

log = logging.getLogger(__name__)

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "LUMINA"


def dev_entry() -> Path:
    """Project root launcher: src/lumina/features/autostart.py -> ../../../"""
    return Path(__file__).resolve().parents[3] / "run_lumina.py"


def _command() -> str:
    """--tray so a logon start goes straight to the notification area."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --tray'
    return f'"{sys.executable}" "{dev_entry()}" --tray'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, _VALUE_NAME)
            return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _command())
            else:
                try:
                    winreg.DeleteValue(key, _VALUE_NAME)
                except FileNotFoundError:
                    pass
        log.info("Autostart set to %s", enabled)
        return True
    except OSError as exc:
        log.error("Autostart change failed: %s", exc)
        return False


def refresh_if_enabled() -> None:
    """Rewrite the path after an in-place upgrade moved the executable."""
    if is_enabled():
        set_enabled(True)

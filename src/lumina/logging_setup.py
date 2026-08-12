"""Rotating log under %LOCALAPPDATA%. v1 wrote next to the executable with
filemode='w' at DEBUG level: unwritable once installed, and it threw away the
previous run's evidence every launch."""
from __future__ import annotations

import logging
import logging.handlers
import sys

from .paths import LOG_FILE, ensure_dirs

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup(debug: bool = False) -> None:
    ensure_dirs()
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    try:
        handler = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=512 * 1024, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(handler)
    except OSError:
        pass  # read-only profile: console handler below still applies

    if not getattr(sys, "frozen", False):
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(console)


def install_excepthook() -> None:
    """v1 died silently on an unhandled exception. Log it, always."""
    def hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logging.getLogger("lumina").critical(
            "Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))

    sys.excepthook = hook

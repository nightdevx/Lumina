"""Backend worker thread with write coalescing.

v1 pushed every slider tick onto a queue and executed all of them, so one drag
produced nine sequential DDC writes and the monitor kept changing for a second
after the user let go. Here a pending write is a *slot per monitor*: while a
60 ms bus write is in flight, later values overwrite the slot instead of
queueing behind it, so the monitor always lands on the value the user stopped
on and never replays the path taken to get there.
"""
from __future__ import annotations

import logging
import threading
from collections import deque

from PySide6.QtCore import QThread, Signal

from .backend import Monitor, MonitorBackend

log = logging.getLogger(__name__)

_REFRESH = "refresh"
_READ = "read"

# Qt's screenAdded/screenRemoved missed display changes that add no screen,
# so the worker watches the display set itself while idle.
TOPOLOGY_POLL_SECONDS = 2.0


class BrightnessService(QThread):
    monitorsChanged = Signal(list)   # list[Monitor] - topology changed
    valuesChanged = Signal(dict)     # {key: percent} - values re-read
    busyChanged = Signal(bool)       # a scan is running
    failed = Signal(str)             # user-visible failure

    def __init__(self, parent=None, backend_factory=MonitorBackend) -> None:
        super().__init__(parent)
        self._backend_factory = backend_factory
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._targets: dict[str, int] = {}
        self._commands: deque[str] = deque()
        self._stopping = False

    # ---- called from the GUI thread ------------------------------------
    def set_brightness(self, key: str, percent: int) -> None:
        with self._lock:
            self._targets[key] = max(0, min(100, int(percent)))
        self._wake.set()

    def set_many(self, values: dict[str, int]) -> None:
        with self._lock:
            for key, percent in values.items():
                self._targets[key] = max(0, min(100, int(percent)))
        self._wake.set()

    def request_refresh(self) -> None:
        self._enqueue(_REFRESH)

    def request_read(self) -> None:
        self._enqueue(_READ)

    def shutdown(self) -> None:
        self._stopping = True
        self._wake.set()
        if not self.wait(3000):
            log.warning("Backend thread did not stop in time")

    def _enqueue(self, command: str) -> None:
        with self._lock:
            if command not in self._commands:
                self._commands.append(command)
        self._wake.set()

    # ---- worker thread --------------------------------------------------
    def run(self) -> None:
        backend = self._backend_factory()   # COM apartment belongs to this thread
        try:
            self._scan(backend)
            while not self._stopping:
                woke = self._wake.wait(timeout=TOPOLOGY_POLL_SECONDS)
                self._wake.clear()
                if self._stopping:
                    break
                if not woke and backend.topology_changed():
                    self._scan(backend)
                self._drain(backend)
        except Exception as exc:
            log.exception("Backend thread crashed")
            self.failed.emit(str(exc))
        finally:
            backend.close()

    def _drain(self, backend: MonitorBackend) -> None:
        with self._lock:
            commands = list(self._commands)
            self._commands.clear()
            targets = self._targets
            self._targets = {}

        for key, percent in targets.items():
            if not backend.set_percent(key, percent):
                log.debug("Write rejected for %s -> %s%%", key, percent)

        for command in commands:
            if command == _REFRESH:
                self._scan(backend)
            elif command == _READ:
                self._emit_values(backend.read_all())

    def _scan(self, backend: MonitorBackend) -> None:
        self.busyChanged.emit(True)
        try:
            monitors = backend.refresh()
            self.monitorsChanged.emit(monitors)
            self._emit_values(monitors)
        finally:
            self.busyChanged.emit(False)

    def _emit_values(self, monitors: list[Monitor]) -> None:
        self.valuesChanged.emit(
            {m.key: m.brightness for m in monitors if m.controllable})

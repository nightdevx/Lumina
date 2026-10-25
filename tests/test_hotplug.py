"""A monitor that turns up after the scan, or whose handles go stale, must not
wait for the user to press refresh.

Both used to: a monitor device attaching late at logon added no Qt screen, so
no rescan ran, and a display mode change left every DDC/CI write failing with
ERROR_GRAPHICS_MONITOR_NO_LONGER_EXISTS.
"""
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PySide6.QtCore import QCoreApplication  # noqa: E402

import lumina.core.backend as backend_module  # noqa: E402
import lumina.core.service as service_module  # noqa: E402
from lumina.core.backend import EXTERNAL, INTERNAL, Monitor, MonitorBackend  # noqa: E402

LAPTOP = Monitor("DISPLAY#A#1", "Laptop", INTERNAL, 40, True)
LG = Monitor("DISPLAY#B#1", "LG", EXTERNAL, 60, True)


class LateMonitorBackend:
    def __init__(self):
        self.attached = [LAPTOP]
        self.scanned = []

    def refresh(self):
        self.scanned = list(self.attached)
        return list(self.attached)

    def read_all(self):
        return list(self.scanned)

    def topology_changed(self):
        return self.scanned != self.attached

    def set_percent(self, key, percent):
        return True

    def close(self):
        pass


def _pump(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)


def test_monitor_attaching_after_the_scan_is_picked_up(qt_app, monkeypatch):
    monkeypatch.setattr(service_module, "TOPOLOGY_POLL_SECONDS", 0.05)
    backend = LateMonitorBackend()
    service = service_module.BrightnessService(backend_factory=lambda: backend)
    seen = []
    service.monitorsChanged.connect(seen.append)
    service.start()
    _pump(0.2)
    assert seen and seen[-1] == [LAPTOP]

    backend.attached = [LAPTOP, LG]
    _pump(0.3)
    service.shutdown()

    assert seen[-1] == [LAPTOP, LG]


class FakeHandle:
    def __init__(self, works):
        self.works = works
        self.closed = False

    def set_percent(self, percent):
        return self.works

    def close(self):
        self.closed = True


def test_failed_write_reacquires_handles_and_retries(monkeypatch):
    stale, fresh = FakeHandle(False), FakeHandle(True)
    monkeypatch.setattr(backend_module, "enumerate_displays",
                        lambda: [SimpleNamespace(identity=LG.key, hmonitor=1)])
    monkeypatch.setattr(backend_module.ddcci, "open_physical_monitors",
                        lambda hmonitor: [fresh])
    backend = MonitorBackend()
    backend._handles[LG.key] = [stale]

    assert backend.set_percent(LG.key, 30)
    assert stale.closed
    assert backend._handles[LG.key] == [fresh]

"""The service must collapse a drag into the value the user stopped on.

v1 executed every queued slider tick, so releasing the slider was followed by
a second of the monitor catching up. This is the check that stops that
regression coming back.
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PySide6.QtCore import QCoreApplication  # noqa: E402

from lumina.core.backend import EXTERNAL, Monitor  # noqa: E402
from lumina.core.service import BrightnessService  # noqa: E402

KEY = "DISPLAY#TEST#1"
BUS_DELAY = 0.02   # stands in for the ~60 ms DDC/CI write


class FakeBackend:
    """Mimics the real bus: writes are slow, so values pile up behind them."""

    def __init__(self):
        self.writes = []
        self.lock = threading.Lock()

    def refresh(self):
        return [Monitor(KEY, "Fake", EXTERNAL, 50, True)]

    def read_all(self):
        return self.refresh()

    def set_percent(self, key, percent):
        time.sleep(BUS_DELAY)
        with self.lock:
            self.writes.append((key, percent))
        return True

    def close(self):
        pass


def _run(service, seconds=1.5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)


def test_drag_collapses_to_final_value(qt_app):
    backend = FakeBackend()
    service = BrightnessService(backend_factory=lambda: backend)
    service.start()
    time.sleep(0.1)

    for value in range(100, 0, -1):     # a fast drag, 100 ticks
        service.set_brightness(KEY, value)
        time.sleep(0.001)

    _run(service, 1.0)
    service.shutdown()

    assert backend.writes, "nothing was written"
    assert backend.writes[-1] == (KEY, 1), "must land on the value the drag ended at"
    # 100 ticks at a 20 ms bus delay could only ever be ~50 writes; coalescing
    # should cut it far below that. The exact count is timing dependent.
    assert len(backend.writes) < 30, f"no coalescing: {len(backend.writes)} writes"


def test_intermediate_values_are_dropped_not_replayed(qt_app):
    backend = FakeBackend()
    service = BrightnessService(backend_factory=lambda: backend)
    service.start()
    time.sleep(0.1)

    # Three values inside one bus write window: only the last should survive.
    service.set_brightness(KEY, 10)
    service.set_brightness(KEY, 20)
    service.set_brightness(KEY, 30)

    _run(service, 0.5)
    service.shutdown()

    written = [v for _, v in backend.writes]
    assert written[-1] == 30
    assert 20 not in written, "a superseded value reached the bus"


def test_separate_monitors_are_not_collapsed_into_each_other(qt_app):
    backend = FakeBackend()
    service = BrightnessService(backend_factory=lambda: backend)
    service.start()
    time.sleep(0.1)

    service.set_many({"A": 10, "B": 90})
    _run(service, 0.5)
    service.shutdown()

    assert dict(backend.writes) == {"A": 10, "B": 90}


def test_shutdown_is_clean_when_idle(qt_app):
    backend = FakeBackend()
    service = BrightnessService(backend_factory=lambda: backend)
    service.start()
    time.sleep(0.1)
    service.shutdown()
    assert service.isFinished()

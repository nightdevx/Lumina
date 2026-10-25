"""End-to-end wiring with a fake backend: does moving a slider actually reach
the monitor, and do the two views stay in step?

No production seam is added for this - the real BrightnessService is swapped
out at import site, so the app is exercised exactly as it ships.
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import lumina.app as app_module  # noqa: E402
import lumina.config as config_module  # noqa: E402
from lumina.core.backend import EXTERNAL, INTERNAL, Monitor  # noqa: E402
from lumina.core.service import BrightnessService  # noqa: E402

A = "DISPLAY#A#1"
B = "DISPLAY#B#1"

MONITORS = [
    Monitor(A, "Laptop", INTERNAL, 40, True),
    Monitor(B, "LG", EXTERNAL, 60, True),
    Monitor("DISPLAY#C#1", "Dead", EXTERNAL, -1, False, "DDC/CI yanıt vermiyor"),
]


class FakeBackend:
    def __init__(self):
        self.writes = []
        self.lock = threading.Lock()

    def refresh(self):
        return list(MONITORS)

    def read_all(self):
        return list(MONITORS)

    def topology_changed(self):
        return False

    def set_percent(self, key, percent):
        with self.lock:
            self.writes.append((key, percent))
        return True

    def close(self):
        pass


@pytest.fixture
def lumina(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(app_module.config_module, "CONFIG_FILE", tmp_path / "config.json")
    backend = FakeBackend()
    monkeypatch.setattr(
        app_module, "BrightnessService",
        lambda parent=None: BrightnessService(parent, backend_factory=lambda: backend))

    controller = app_module.LuminaApp(qt_app, start_hidden=True)
    _pump(0.4)
    yield controller, backend
    controller.service.shutdown()
    controller.tray.hide()
    controller.window.deleteLater()
    controller.quick.deleteLater()


def _pump(seconds=0.3):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.005)


def test_scan_populates_both_views(lumina):
    controller, _ = lumina
    assert controller.window.monitors.controllable_keys() == [A, B]
    assert controller.quick.monitors.controllable_keys() == [A, B]


def test_slider_reaches_the_backend(lumina):
    controller, backend = lumina
    controller.window.monitors._cards[B].slider.setValue(25)
    _pump(0.4)
    assert (B, 25) in backend.writes


def test_uncontrollable_monitor_is_not_written(lumina):
    controller, backend = lumina
    controller._apply_values({k: 50 for k in controller._controllable_keys()})
    _pump(0.4)
    assert all(key != "DISPLAY#C#1" for key, _ in backend.writes)


def test_quick_panel_mirrors_main_window(lumina):
    controller, _ = lumina
    controller.window.monitors._cards[A].slider.setValue(33)
    _pump(0.3)
    assert controller.quick.monitors._cards[A].value() == 33


def test_sync_applies_to_every_controllable_monitor(lumina):
    controller, backend = lumina
    controller._set_sync(True)
    _pump(0.3)
    backend.writes.clear()

    controller.window.monitors._cards[A].slider.setValue(15)
    _pump(0.4)

    written = dict(backend.writes)
    assert written.get(A) == 15
    assert written.get(B) == 15, "sync did not carry to the other monitor"
    assert controller.quick.monitors._cards[B].value() == 15


def test_sync_off_leaves_other_monitors_alone(lumina):
    controller, backend = lumina
    controller._set_sync(False)
    _pump(0.2)
    backend.writes.clear()

    controller.window.monitors._cards[A].slider.setValue(77)
    _pump(0.4)

    assert all(key == A for key, _ in backend.writes)


def test_schedule_without_fade_applies_immediately(lumina):
    controller, backend = lumina
    controller.config.fade_enabled = False
    backend.writes.clear()

    controller._apply_schedule(12)
    _pump(0.4)

    assert dict(backend.writes) == {A: 12, B: 12}


def test_schedule_with_fade_ramps_instead_of_jumping(lumina):
    controller, backend = lumina
    controller.config.fade_enabled = True
    controller.config.fade_duration_ms = 400
    controller.window.monitors.set_values({A: 90, B: 90})
    backend.writes.clear()

    controller._apply_schedule(10)
    _pump(1.0)

    values = [v for k, v in backend.writes if k == A]
    assert values, "fade produced no writes"
    assert values[-1] == 10, "fade did not reach the target"
    assert len(values) > 2, f"fade jumped instead of ramping: {values}"
    assert values == sorted(values, reverse=True), f"fade was not monotonic: {values}"


def test_manual_move_cancels_a_running_fade(lumina):
    controller, backend = lumina
    controller.config.fade_enabled = True
    controller.config.fade_duration_ms = 3000
    controller.window.monitors.set_values({A: 90, B: 90})
    controller._apply_schedule(10)
    _pump(0.2)
    assert controller.fade.running

    controller.window.monitors._cards[A].slider.setValue(55)
    _pump(0.2)
    assert not controller.fade.running, "a scheduled ramp kept fighting the user"


def test_scan_result_does_not_yank_a_slider_the_user_just_moved(lumina):
    controller, _ = lumina
    controller.window.monitors._cards[B].slider.setValue(20)
    _pump(0.1)
    controller._on_values({A: 40, B: 60})     # stale scan result
    assert controller.window.monitors._cards[B].value() == 20


def test_config_survives_a_round_trip(lumina, tmp_path):
    controller, _ = lumina
    controller._set_sync(True)
    controller._on_fade_settings(False, 1500)
    controller._save_now()

    reloaded = config_module.load()
    assert reloaded.sync is True
    assert reloaded.fade_enabled is False
    assert reloaded.fade_duration_ms == 1500
    assert [m["key"] for m in reloaded.monitor_cache] == [A, B, "DISPLAY#C#1"]

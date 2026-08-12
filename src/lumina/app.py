"""Wiring: config <-> service <-> views.

The window and the tray popup are dumb views; this is the only place that
knows the current monitor set, so the two can never drift apart.
"""
from __future__ import annotations

import logging
import time

from PySide6.QtCore import QObject, QTimer, Qt
from PySide6.QtGui import QAction, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import __version__, config as config_module
from .config import Config, ScheduleRule
from .core.backend import Monitor
from .core.service import BrightnessService
from .features import autostart
from .features.automation import FadeController, ScheduleController
from .paths import resource_dir
from .ui.main_window import MainWindow
from .ui.quick_panel import QuickPanel

log = logging.getLogger(__name__)

# A scan result must not yank a slider the user is still moving.
WRITE_GRACE_SECONDS = 0.6
SAVE_DEBOUNCE_MS = 500
HOTPLUG_SETTLE_MS = 900


class LuminaApp(QObject):
    def __init__(self, app: QApplication, start_hidden: bool) -> None:
        super().__init__()
        self.app = app
        self.config: Config = config_module.load()
        self._monitors: list[Monitor] = [
            Monitor.from_dict(entry) for entry in self.config.monitor_cache]
        self._recent_writes: dict[str, float] = {}
        self._applying = False

        self.window = MainWindow(self.config)
        self.quick = QuickPanel()
        self.service = BrightnessService(self)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DEBOUNCE_MS)
        self._save_timer.timeout.connect(self._save_now)

        self._hotplug_timer = QTimer(self)
        self._hotplug_timer.setSingleShot(True)
        self._hotplug_timer.setInterval(HOTPLUG_SETTLE_MS)
        self._hotplug_timer.timeout.connect(self.service.request_refresh)

        self.fade = FadeController(self)
        self.schedules = ScheduleController(lambda: self.config.schedules, self)

        self._build_tray()
        self._connect()

        # Paint the last known monitors before the first scan finishes, so the
        # window is usable immediately instead of v1's 10-25 s locked state.
        if self._monitors:
            self._publish_monitors(self._monitors, cache=False)
        self.window.set_autostart(autostart.is_enabled())
        self.window.set_sync(self.config.sync)
        self.quick.sync_button.setChecked(self.config.sync)
        self.window.set_status("MONİTÖRLER TARANIYOR…")

        self.service.start()
        if not start_hidden:
            self.window.present()

    # ---------------- setup ----------------
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self._icon())
        self.tray.setToolTip(f"LUMINA {__version__}")

        menu = QMenu()
        panel_action = QAction("Hızlı panel", menu)
        panel_action.triggered.connect(self.quick.popup_at_cursor)
        window_action = QAction("Pencereyi aç", menu)
        window_action.triggered.connect(self.window.present)
        rescan_action = QAction("Monitörleri tara", menu)
        rescan_action.triggered.connect(self.service.request_refresh)
        quit_action = QAction("Çıkış", menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(panel_action)
        menu.addAction(window_action)
        menu.addSeparator()
        menu.addAction(rescan_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        # Left click only. v1 also handled DoubleClick, which fired Trigger
        # first and opened the popup on the way to opening the window.
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _icon(self) -> QIcon:
        for name in ("lumina.ico", "lumina.png"):
            path = resource_dir() / name
            if path.exists():
                return QIcon(str(path))
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setBrush(Qt.GlobalColor.white)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(10, 10, 44, 44)
        painter.end()
        return QIcon(pixmap)

    def _connect(self) -> None:
        self.service.monitorsChanged.connect(self._on_monitors)
        self.service.valuesChanged.connect(self._on_values)
        self.service.busyChanged.connect(self._on_busy)
        self.service.failed.connect(self._on_failed)

        for view in (self.window.monitors, self.quick.monitors):
            view.changed.connect(self._on_user_change)
        self.window.sync_toggled.connect(self._set_sync)
        self.quick.sync_toggled.connect(self._set_sync)
        self.quick.open_requested.connect(self.window.present)
        self.window.refresh_requested.connect(self.service.request_refresh)
        self.window.schedules_changed.connect(self._on_schedules)
        self.window.autostart_toggled.connect(self._on_autostart)
        self.window.fade_changed.connect(self._on_fade_settings)
        self.window.quit_requested.connect(self.quit)

        self.schedules.triggered.connect(self._apply_schedule)
        self.fade.stepped.connect(self._apply_values)

        screens = QGuiApplication.instance()
        screens.screenAdded.connect(lambda _: self._hotplug_timer.start())
        screens.screenRemoved.connect(lambda _: self._hotplug_timer.start())

        self.app.aboutToQuit.connect(self._teardown)

    # ---------------- service events ----------------
    def _on_monitors(self, monitors: list[Monitor]) -> None:
        self._publish_monitors(monitors, cache=True)

    def _publish_monitors(self, monitors: list[Monitor], cache: bool) -> None:
        self._monitors = monitors
        self.window.monitors.set_monitors(monitors)
        self.quick.monitors.set_monitors(monitors)
        if cache:
            self.config.monitor_cache = [m.as_dict() for m in monitors]
            self._save_soon()

    def _on_values(self, values: dict) -> None:
        now = time.monotonic()
        fresh = {
            key: percent for key, percent in values.items()
            if now - self._recent_writes.get(key, 0.0) > WRITE_GRACE_SECONDS
        }
        if fresh:
            self.window.monitors.set_values(fresh)
            self.quick.monitors.set_values(fresh)

    def _on_busy(self, busy: bool) -> None:
        self.window.set_status("MONİTÖRLER TARANIYOR…" if busy else "")
        self.window.refresh_button.setEnabled(not busy)

    def _on_failed(self, message: str) -> None:
        log.error("Service failure: %s", message)
        self.window.set_status(f"HATA: {message.upper()[:60]}")
        self.tray.showMessage("LUMINA", f"Arka plan hatası: {message}",
                              QSystemTrayIcon.MessageIcon.Warning, 5000)

    # ---------------- user actions ----------------
    def _on_user_change(self, key: str, percent: int) -> None:
        if self._applying:
            return
        if self.fade.running:
            self.fade.cancel()   # a manual move wins over a scheduled ramp
        targets = {key: percent}
        if self.config.sync:
            targets = {k: percent for k in self._controllable_keys()}
        self._apply_values(targets)

    def _apply_values(self, values: dict) -> None:
        """Push to the backend and mirror into both views.

        Every card gets the value, including the one the change came from: the
        same monitor also has a card in the other view, and skipping the source
        key left that twin stale. Re-setting the originating slider is free -
        set_value blocks signals and writing back its own current value is a
        no-op inside QSlider.
        """
        if not values:
            return
        now = time.monotonic()
        for key in values:
            self._recent_writes[key] = now
        self.service.set_many(values)
        self._applying = True
        try:
            self.window.monitors.set_values(values)
            self.quick.monitors.set_values(values)
        finally:
            self._applying = False

    def _controllable_keys(self) -> list[str]:
        return [m.key for m in self._monitors if m.controllable]

    def _set_sync(self, enabled: bool) -> None:
        self.config.sync = enabled
        self.window.set_sync(enabled)
        blocked = self.quick.sync_button.blockSignals(True)
        self.quick.sync_button.setChecked(enabled)
        self.quick.sync_button.blockSignals(blocked)
        self._save_soon()
        if enabled:
            current = self.window.monitors.values() or self.quick.monitors.values()
            if current:
                reference = next(iter(current.values()))
                self._apply_values({k: reference for k in self._controllable_keys()})

    def _on_schedules(self, rules: list[ScheduleRule]) -> None:
        self.config.schedules = rules
        self.schedules.reset()
        self._save_soon()
        self.schedules.check()

    def _on_autostart(self, enabled: bool) -> None:
        if not autostart.set_enabled(enabled):
            self.window.set_autostart(autostart.is_enabled())

    def _on_fade_settings(self, enabled: bool, duration_ms: int) -> None:
        self.config.fade_enabled = enabled
        self.config.fade_duration_ms = duration_ms
        self._save_soon()

    def _apply_schedule(self, percent: int) -> None:
        keys = self._controllable_keys()
        if not keys:
            return
        target = {key: percent for key in keys}
        if not self.config.fade_enabled or self.config.fade_duration_ms <= 0:
            self._apply_values(target)
            return
        current = self.window.monitors.values() or self.quick.monitors.values()
        self.fade.run(current, target, self.config.fade_duration_ms)

    def _on_tray_activated(self, reason) -> None:
        if reason != QSystemTrayIcon.ActivationReason.Trigger:
            return
        if self.quick.isVisible():
            self.quick.hide()
        else:
            self.quick.popup_at_cursor()
            self.service.request_read()

    # ---------------- lifecycle ----------------
    def show_from_second_instance(self) -> None:
        self.window.present()

    def _save_soon(self) -> None:
        self._save_timer.start()

    def _save_now(self) -> None:
        config_module.save(self.config)

    def quit(self) -> None:
        self.app.quit()

    def _teardown(self) -> None:
        self._save_timer.stop()
        self._save_now()
        self.fade.cancel()
        self.service.shutdown()
        self.tray.hide()

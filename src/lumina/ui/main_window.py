"""Main window: monitors, scheduler, settings.

Frameless but not a Qt.Tool window, so it shows up in the taskbar and Alt-Tab
like an application rather than a floating widget.
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSlider,
    QStackedWidget, QVBoxLayout, QWidget,
)

from .. import __version__
from ..config import Config, ScheduleRule
from ..paths import LOG_DIR, resource_dir
from . import icons
from .widgets import MonitorList, RuleCard

WINDOW_SIZE = (580, 610)


class MainWindow(QWidget):
    changed = Signal(str, int)
    sync_toggled = Signal(bool)
    refresh_requested = Signal()
    schedules_changed = Signal(list)
    autostart_toggled = Signal(bool)
    fade_changed = Signal(bool, int)
    quit_requested = Signal()

    def __init__(self, config: Config, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("LUMINA")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(*WINDOW_SIZE)

        icon_path = resource_dir() / "lumina.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        container = QFrame()
        container.setObjectName("container")
        root.addWidget(container)

        body = QHBoxLayout(container)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        body.addWidget(self._build_pages(), 1)

    # ---------------- construction ----------------
    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(164)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 24, 0, 8)
        layout.setSpacing(0)

        logo_path = resource_dir() / "lumina.png"
        if logo_path.exists():
            logo = QLabel()
            logo.setPixmap(QPixmap(str(logo_path)).scaled(
                56, 56, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(logo)
            layout.addSpacing(10)

        wordmark = QLabel("LUMINA")
        wordmark.setObjectName("wordmark")
        wordmark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(wordmark)

        version = QLabel(f"v{__version__}")
        version.setObjectName("versionLabel")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)
        layout.addSpacing(28)

        self._nav_buttons = []
        for index, text in enumerate(("MONİTÖRLER", "ZAMANLAYICI", "AYARLAR")):
            button = QPushButton(text)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.setFixedHeight(38)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, i=index: self.show_page(i))
            layout.addWidget(button)
            self._nav_buttons.append(button)

        layout.addStretch()
        quit_button = QPushButton("SİSTEMDEN ÇIK")
        quit_button.setObjectName("quitButton")
        quit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        quit_button.clicked.connect(self.quit_requested.emit)
        layout.addWidget(quit_button)
        return sidebar

    def _build_pages(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top = QHBoxLayout()
        top.setContentsMargins(0, 14, 14, 0)
        top.addStretch()
        close = QPushButton(icons.CLOSE)
        close.setObjectName("iconButton")
        close.setToolTip("Bildirim alanına gizle")
        close.setFixedSize(28, 28)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.hide)
        top.addWidget(close)
        layout.addLayout(top)

        self._pages = QStackedWidget()
        self._pages.addWidget(self._build_monitor_page())
        self._pages.addWidget(self._build_schedule_page())
        self._pages.addWidget(self._build_settings_page())
        layout.addWidget(self._pages, 1)

        self.status_bar = QFrame()
        self.status_bar.setObjectName("statusBar")
        self.status_bar.setFixedHeight(28)
        status_layout = QHBoxLayout(self.status_bar)
        status_layout.setContentsMargins(16, 0, 16, 0)
        self._status_text = QLabel("")
        self._status_text.setObjectName("statusText")
        status_layout.addWidget(self._status_text)
        status_layout.addStretch()
        self.status_bar.setVisible(False)
        layout.addWidget(self.status_bar)
        return wrapper

    def _build_monitor_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 4, 28, 24)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("MONİTÖRLER")
        title.setObjectName("pageTitle")
        self.refresh_button = QPushButton(icons.REFRESH)
        self.refresh_button.setObjectName("iconButton")
        self.refresh_button.setFixedSize(28, 28)
        self.refresh_button.setToolTip("Monitörleri yeniden tara")
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.refresh_button)
        layout.addLayout(header)

        self.monitors = MonitorList()
        self.monitors.changed.connect(self.changed.emit)
        layout.addWidget(self.monitors)
        layout.addStretch()
        return page

    def _build_schedule_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 4, 28, 24)
        layout.setSpacing(12)

        title = QLabel("ZAMANLAYICI")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        hint = QLabel("Gece aşırı aralıklar desteklenir (örn. 22:00 → 06:00).")
        hint.setObjectName("pageHint")
        layout.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        holder = QWidget()
        self._rules_layout = QVBoxLayout(holder)
        self._rules_layout.setContentsMargins(0, 0, 8, 0)
        self._rules_layout.setSpacing(10)
        self._rules_layout.addStretch()
        scroll.setWidget(holder)
        layout.addWidget(scroll, 1)

        add = QPushButton("+ YENİ KURAL")
        add.setObjectName("ghostButton")
        add.setFixedHeight(34)
        add.setCursor(Qt.CursorShape.PointingHandCursor)
        add.clicked.connect(lambda: self._add_rule(None, emit=True))
        layout.addWidget(add)

        for rule in self._config.schedules:
            self._add_rule(rule, emit=False)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 4, 28, 24)
        layout.setSpacing(16)

        title = QLabel("AYARLAR")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        self.autostart_box = QCheckBox("WINDOWS İLE BAŞLAT")
        self.autostart_box.toggled.connect(self.autostart_toggled.emit)
        layout.addWidget(self.autostart_box)

        self.sync_box = QCheckBox("EŞİTLEME MODU (TÜM MONİTÖRLER BİRLİKTE)")
        self.sync_box.setChecked(self._config.sync)
        self.sync_box.toggled.connect(self.sync_toggled.emit)
        layout.addWidget(self.sync_box)

        self.fade_box = QCheckBox("ZAMANLAYICIDA YUMUŞAK GEÇİŞ")
        self.fade_box.setChecked(self._config.fade_enabled)
        self.fade_box.toggled.connect(self._emit_fade)
        layout.addWidget(self.fade_box)

        fade_row = QHBoxLayout()
        fade_row.setSpacing(10)
        fade_label = QLabel("GEÇİŞ SÜRESİ")
        fade_label.setObjectName("ruleLabel")
        self.fade_slider = QSlider(Qt.Orientation.Horizontal)
        self.fade_slider.setRange(0, 10)
        self.fade_slider.setValue(round(self._config.fade_duration_ms / 1000))
        self.fade_readout = QLabel(f"{self.fade_slider.value()} sn")
        self.fade_readout.setObjectName("cardValue")
        self.fade_readout.setFixedWidth(44)
        self.fade_readout.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.fade_slider.valueChanged.connect(self._emit_fade)
        fade_row.addWidget(fade_label)
        fade_row.addWidget(self.fade_slider)
        fade_row.addWidget(self.fade_readout)
        layout.addLayout(fade_row)
        self.fade_slider.setEnabled(self.fade_box.isChecked())

        layout.addStretch()
        logs = QPushButton("GÜNLÜK KLASÖRÜNÜ AÇ")
        logs.setObjectName("ghostButton")
        logs.setFixedHeight(32)
        logs.setCursor(Qt.CursorShape.PointingHandCursor)
        logs.clicked.connect(self._open_logs)
        layout.addWidget(logs)
        return page

    # ---------------- behaviour ----------------
    def show_page(self, index: int) -> None:
        self._pages.setCurrentIndex(index)
        for position, button in enumerate(self._nav_buttons):
            button.setChecked(position == index)

    def _emit_fade(self) -> None:
        enabled = self.fade_box.isChecked()
        seconds = self.fade_slider.value()
        self.fade_readout.setText(f"{seconds} sn")
        self.fade_slider.setEnabled(enabled)
        self.fade_changed.emit(enabled, seconds * 1000)

    def _add_rule(self, rule: ScheduleRule | None, emit: bool) -> None:
        card = RuleCard(rule)
        card.removed.connect(self._remove_rule)
        card.edited.connect(self._emit_rules)
        self._rules_layout.insertWidget(self._rules_layout.count() - 1, card)
        if emit:
            self._emit_rules()

    def _remove_rule(self, card: RuleCard) -> None:
        self._rules_layout.removeWidget(card)
        card.setParent(None)
        card.deleteLater()
        self._emit_rules()   # v1 kept deleted rules until you pressed Save

    def _emit_rules(self) -> None:
        rules = [
            self._rules_layout.itemAt(i).widget().to_rule()
            for i in range(self._rules_layout.count())
            if isinstance(self._rules_layout.itemAt(i).widget(), RuleCard)
        ]
        self.schedules_changed.emit(rules)

    def _open_logs(self) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(LOG_DIR)  # noqa: S606 - opening our own log folder

    def set_status(self, message: str) -> None:
        self._status_text.setText(message)
        self.status_bar.setVisible(bool(message))

    def set_autostart(self, enabled: bool) -> None:
        blocked = self.autostart_box.blockSignals(True)
        self.autostart_box.setChecked(enabled)
        self.autostart_box.blockSignals(blocked)

    def set_sync(self, enabled: bool) -> None:
        blocked = self.sync_box.blockSignals(True)
        self.sync_box.setChecked(enabled)
        self.sync_box.blockSignals(blocked)

    def present(self) -> None:
        if not self.isVisible():
            screen = QGuiApplication.primaryScreen().availableGeometry()
            self.move(screen.center() - self.rect().center())
        self.show()
        self.raise_()
        self.activateWindow()

    def mousePressEvent(self, event) -> None:
        # Native move: gets Aero Snap and multi-monitor DPI right for free,
        # unlike v1's manual globalPos arithmetic.
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.windowHandle()
            if handle is not None:
                handle.startSystemMove()
        super().mousePressEvent(event)

"""Tray flyout: the fast path. One click from the notification area to a
slider, with no scan in between - values come from the controller's cache."""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import icons
from .widgets import MonitorList

PANEL_WIDTH = 292
SCREEN_MARGIN = 12


class QuickPanel(QWidget):
    changed = Signal(str, int)
    sync_toggled = Signal(bool)
    open_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(PANEL_WIDTH)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        container = QFrame()
        container.setObjectName("popupContainer")
        outer.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(15, 14, 15, 15)
        layout.setSpacing(11)

        header = QHBoxLayout()
        title = QLabel("LUMINA")
        title.setObjectName("panelTitle")
        self.sync_button = QPushButton(icons.SYNC)
        self.sync_button.setObjectName("toggleButton")
        self.sync_button.setCheckable(True)
        self.sync_button.setFixedSize(26, 26)
        self.sync_button.setToolTip("Tüm monitörleri eşitle")
        self.sync_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sync_button.clicked.connect(
            lambda: self.sync_toggled.emit(self.sync_button.isChecked()))
        settings = QPushButton(icons.SETTINGS)
        settings.setObjectName("toggleButton")
        settings.setFixedSize(26, 26)
        settings.setToolTip("Paneli aç")
        settings.setCursor(Qt.CursorShape.PointingHandCursor)
        settings.clicked.connect(self._open_main)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.sync_button)
        header.addWidget(settings)
        layout.addLayout(header)

        self.monitors = MonitorList()
        self.monitors.changed.connect(self.changed.emit)
        layout.addWidget(self.monitors)

    def _open_main(self) -> None:
        self.hide()
        self.open_requested.emit()

    def popup_at_cursor(self) -> None:
        """Anchor above the tray icon and stay inside the screen it is on."""
        self.adjustSize()
        cursor = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()

        x = cursor.x() - self.width() // 2
        x = max(area.left() + SCREEN_MARGIN,
                min(x, area.right() - self.width() - SCREEN_MARGIN))
        y = cursor.y() - self.height() - 16
        if y < area.top() + SCREEN_MARGIN:
            y = cursor.y() + 16   # taskbar on top: drop below instead

        self.move(QPoint(x, y))
        self.show()
        self.raise_()
        self.activateWindow()

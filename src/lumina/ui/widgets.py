"""Reusable widgets. Styling lives in resources/theme.qss - only object names
and layout here."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTime, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSlider, QTimeEdit, QVBoxLayout,
    QWidget,
)

from ..config import ScheduleRule
from ..core.backend import INTERNAL, Monitor


class MonitorCard(QFrame):
    """One monitor: name, live percentage, slider.

    No debounce. v1 waited 150 ms before acting on a drag because each write
    cost a process spawn; the service coalesces now, so every tick can be sent
    and the slider feels attached to the backlight.
    """

    changed = Signal(str, int)   # key, percent

    def __init__(self, monitor: Monitor, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.monitor = monitor

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        self._name = QLabel(monitor.name.upper())
        self._name.setObjectName("cardName")
        badge = QLabel("DAHİLİ" if monitor.kind == INTERNAL else "HARİCİ")
        badge.setObjectName("cardBadge")
        self._value = QLabel("—")
        self._value.setObjectName("cardValue")
        self._value.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._value.setFixedWidth(46)
        header.addWidget(self._name)
        header.addWidget(badge)
        header.addStretch()
        header.addWidget(self._value)
        layout.addLayout(header)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setPageStep(5)
        self.slider.valueChanged.connect(self._on_slider)
        layout.addWidget(self.slider)

        self._warning = QLabel(monitor.reason)
        self._warning.setObjectName("cardWarning")
        self._warning.setVisible(False)
        layout.addWidget(self._warning)

        self.apply_state(monitor)

    @property
    def key(self) -> str:
        return self.monitor.key

    def apply_state(self, monitor: Monitor) -> None:
        self.monitor = monitor
        self._name.setText(monitor.name.upper())
        self.setProperty("disabledCard", not monitor.controllable)
        self.style().unpolish(self)
        self.style().polish(self)
        if monitor.controllable:
            self._warning.setVisible(False)
            self.slider.setEnabled(True)
            self.set_value(monitor.brightness)
        else:
            self._warning.setText(monitor.reason or "Kontrol edilemiyor")
            self._warning.setVisible(True)
            self.slider.setEnabled(False)
            self._value.setText("—")

    def set_value(self, percent: int) -> None:
        """Update without emitting - used for sync, fade and scan results."""
        if percent < 0:
            self._value.setText("—")
            return
        blocked = self.slider.blockSignals(True)
        self.slider.setValue(percent)
        self.slider.blockSignals(blocked)
        self._value.setText(f"{percent}%")

    def value(self) -> int:
        return self.slider.value()

    def _on_slider(self, percent: int) -> None:
        self._value.setText(f"{percent}%")
        self.changed.emit(self.monitor.key, percent)


class MonitorList(QWidget):
    """Dumb view over the monitor set.

    The main window and the tray popup both embed one; neither owns state, so
    keeping them in step is one controller's job instead of v1's
    ``self._cards + self.quick._cards`` scattered through every handler.
    """

    changed = Signal(str, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)
        self._cards: dict[str, MonitorCard] = {}
        self._empty = QLabel("Monitör aranıyor…")
        self._empty.setObjectName("emptyState")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._empty)

    def set_monitors(self, monitors: list[Monitor]) -> None:
        keys = [m.key for m in monitors]
        for key in list(self._cards):
            if key not in keys:
                card = self._cards.pop(key)
                self._layout.removeWidget(card)
                card.deleteLater()
        for index, monitor in enumerate(monitors):
            card = self._cards.get(monitor.key)
            if card is None:
                card = MonitorCard(monitor)
                card.changed.connect(self.changed.emit)
                self._cards[monitor.key] = card
            else:
                card.apply_state(monitor)
            self._layout.insertWidget(index, card)
        self._empty.setVisible(not monitors)

    def set_values(self, values: dict[str, int]) -> None:
        for key, percent in values.items():
            card = self._cards.get(key)
            if card is not None and card.monitor.controllable:
                card.set_value(percent)

    def values(self) -> dict[str, int]:
        return {k: c.value() for k, c in self._cards.items() if c.monitor.controllable}

    def controllable_keys(self) -> list[str]:
        return [k for k, c in self._cards.items() if c.monitor.controllable]

    def set_interactive(self, enabled: bool) -> None:
        for card in self._cards.values():
            if card.monitor.controllable:
                card.slider.setEnabled(enabled)


class RuleCard(QFrame):
    """A single time rule. Emits on edit so the caller can persist eagerly."""

    removed = Signal(object)
    edited = Signal()

    def __init__(self, rule: ScheduleRule | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ruleCard")
        rule = rule or ScheduleRule()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 14, 15, 14)
        layout.setSpacing(11)

        top = QHBoxLayout()
        top.setSpacing(9)
        label = QLabel("ARALIK")
        label.setObjectName("ruleLabel")
        self.start = self._time_edit(rule.start)
        arrow = QLabel("→")
        arrow.setObjectName("ruleLabel")
        self.end = self._time_edit(rule.end)
        delete = QPushButton("SİL")
        delete.setObjectName("deleteButton")
        delete.setFixedSize(40, 24)
        delete.setCursor(Qt.CursorShape.PointingHandCursor)
        delete.clicked.connect(lambda: self.removed.emit(self))
        for widget in (label, self.start, arrow, self.end):
            top.addWidget(widget)
        top.addStretch()
        top.addWidget(delete)
        layout.addLayout(top)

        bottom = QHBoxLayout()
        bottom.setSpacing(9)
        value_label = QLabel("PARLAKLIK")
        value_label.setObjectName("ruleLabel")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(rule.value)
        self.readout = QLabel(f"{rule.value}%")
        self.readout.setObjectName("cardValue")
        self.readout.setFixedWidth(40)
        self.readout.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.slider.valueChanged.connect(self._on_value)
        bottom.addWidget(value_label)
        bottom.addWidget(self.slider)
        bottom.addWidget(self.readout)
        layout.addLayout(bottom)

        self.overnight = QLabel("GECE AŞIRI")
        self.overnight.setObjectName("cardBadge")
        layout.addWidget(self.overnight)
        self._update_overnight()

    def _time_edit(self, value: str) -> QTimeEdit:
        edit = QTimeEdit()
        edit.setDisplayFormat("HH:mm")
        edit.setTime(QTime.fromString(value, "HH:mm"))
        edit.setFixedWidth(62)
        edit.timeChanged.connect(self._on_time)
        return edit

    def _on_time(self) -> None:
        self._update_overnight()
        self.edited.emit()

    def _on_value(self, value: int) -> None:
        self.readout.setText(f"{value}%")
        self.edited.emit()

    def _update_overnight(self) -> None:
        self.overnight.setVisible(self.start.time() > self.end.time())

    def to_rule(self) -> ScheduleRule:
        return ScheduleRule(
            start=self.start.time().toString("HH:mm"),
            end=self.end.time().toString("HH:mm"),
            value=self.slider.value(),
            enabled=True,
        )

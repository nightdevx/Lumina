"""Time-based rules and smooth transitions.

Rule matching is pure so it can be tested without a clock or a monitor; the
controllers on top only add timers.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable

from PySide6.QtCore import QObject, QTime, QTimer, Signal

from ..config import ScheduleRule

log = logging.getLogger(__name__)

FADE_STEP_MS = 80   # ~1.3x the DDC/CI bus write time; finer steps just coalesce away


def parse_hhmm(text: str) -> int:
    """"22:30" -> 1350 minutes past midnight. Invalid input -> 0."""
    try:
        hours, _, minutes = text.partition(":")
        return (int(hours) % 24) * 60 + int(minutes) % 60
    except ValueError:
        return 0


def in_range(now: int, start: int, end: int) -> bool:
    """Half-open [start, end) on a 24 h circle.

    v1 compared "HH:MM" strings, so an overnight rule like 22:00->06:00 was
    never true. Wrapping ranges are the common case for a brightness app.
    start == end wraps the whole way round, i.e. always active.
    """
    if start == end:
        return True
    if start < end:
        return start <= now < end
    return now >= start or now < end


def active_rule(rules: Iterable[ScheduleRule], now_minutes: int) -> ScheduleRule | None:
    """First enabled rule covering `now`. Order in the list is the priority."""
    for rule in rules:
        if not rule.enabled:
            continue
        if in_range(now_minutes, parse_hhmm(rule.start), parse_hhmm(rule.end)):
            return rule
    return None


class ScheduleController(QObject):
    """Fires once when the active rule changes, not once per tick."""

    triggered = Signal(int)   # target percent

    def __init__(self, rules_provider: Callable[[], list[ScheduleRule]], parent=None) -> None:
        super().__init__(parent)
        self._rules = rules_provider
        self._applied: ScheduleRule | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check)
        self._timer.start(20_000)

    def reset(self) -> None:
        """After an edit, let the current rule fire again."""
        self._applied = None

    def check(self) -> None:
        now = QTime.currentTime()
        rule = active_rule(self._rules(), now.hour() * 60 + now.minute())
        if rule is None:
            self._applied = None
            return
        if rule == self._applied:
            return
        self._applied = rule
        log.info("Schedule rule active: %s-%s -> %s%%", rule.start, rule.end, rule.value)
        self.triggered.emit(rule.value)


class FadeController(QObject):
    """Interpolates towards a target instead of jumping.

    Only worth it for scheduled changes; a slider drag is already continuous.
    """

    stepped = Signal(dict)     # {key: percent}
    finished = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(FADE_STEP_MS)
        self._timer.timeout.connect(self._advance)
        self._start: dict[str, int] = {}
        self._target: dict[str, int] = {}
        self._steps = 0
        self._step = 0

    @property
    def running(self) -> bool:
        return self._timer.isActive()

    def cancel(self) -> None:
        self._timer.stop()

    def run(self, start: dict[str, int], target: dict[str, int], duration_ms: int) -> None:
        self.cancel()
        self._start = {k: v for k, v in start.items() if k in target}
        self._target = dict(target)
        self._steps = max(1, duration_ms // FADE_STEP_MS)
        self._step = 0
        if duration_ms < FADE_STEP_MS:
            self.stepped.emit(dict(self._target))
            self.finished.emit()
            return
        self._timer.start()

    def _advance(self) -> None:
        self._step += 1
        progress = min(1.0, self._step / self._steps)
        values = {
            key: round(self._start.get(key, value) +
                       (value - self._start.get(key, value)) * progress)
            for key, value in self._target.items()
        }
        self.stepped.emit(values)
        if progress >= 1.0:
            self._timer.stop()
            self.finished.emit()

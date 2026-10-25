"""One view of every controllable display, over whichever transport fits it.

Owns the DDC/CI handles and the WMI connection, so it is single-threaded by
construction: create it on the backend worker thread and never touch it from
the GUI thread.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from . import ddcci
from .discovery import DisplayInfo, enumerate_displays, topology_signature
from .panel import PanelBackend

log = logging.getLogger(__name__)

INTERNAL = "internal"
EXTERNAL = "external"


@dataclass(frozen=True)
class Monitor:
    key: str                 # normalized identity, stable across reboots
    name: str
    kind: str                # INTERNAL | EXTERNAL
    brightness: int          # 0-100, -1 when unknown
    controllable: bool
    reason: str = ""         # why not controllable, shown in the UI
    primary: bool = False

    def as_dict(self) -> dict:
        return {"key": self.key, "name": self.name, "kind": self.kind,
                "brightness": self.brightness, "controllable": self.controllable,
                "reason": self.reason, "primary": self.primary}

    @staticmethod
    def from_dict(data: dict) -> "Monitor":
        return Monitor(
            key=str(data.get("key", "")),
            name=str(data.get("name", "Monitör")),
            kind=str(data.get("kind", EXTERNAL)),
            brightness=int(data.get("brightness", -1)),
            controllable=bool(data.get("controllable", True)),
            reason=str(data.get("reason", "")),
            primary=bool(data.get("primary", False)),
        )


class MonitorBackend:
    def __init__(self) -> None:
        self._panel = PanelBackend()
        self._handles: dict[str, list[ddcci.PhysicalMonitor]] = {}
        self._panel_instances: dict[str, str] = {}   # key -> WMI InstanceName
        self._monitors: list[Monitor] = []
        self._signature: tuple = ()

    @property
    def monitors(self) -> list[Monitor]:
        return list(self._monitors)

    def topology_changed(self) -> bool:
        """True when the displays no longer match what the last scan saw.

        A scan is only as good as the moment it ran. Windows brings displays up
        in steps (logon, docking, a monitor waking), and a step that adds no Qt
        screen, such as a monitor device attaching to an output that already
        exists, used to leave a monitor missing until a manual rescan."""
        return topology_signature() != self._signature

    def refresh(self) -> list[Monitor]:
        """Re-enumerate from scratch. Must run after any display change —
        HMONITOR values and physical monitor handles both go stale."""
        # Taken before enumerating: a change during the scan then shows up as
        # a mismatch on the next poll instead of being baked into the result.
        self._signature = topology_signature()
        self._release_handles()
        panels = {p.identity: p for p in self._panel.list_panels()}
        self._panel_instances = {p.identity: p.instance_name for p in panels.values()}

        found: list[Monitor] = []
        for display in enumerate_displays():
            if display.identity in panels:
                found.append(self._build_internal(display, panels[display.identity]))
            else:
                found.append(self._build_external(display))

        # A WMI panel that no display enumeration matched still deserves a card;
        # without it a laptop with an unusual identity string loses its slider.
        matched = {m.key for m in found}
        for identity, info in panels.items():
            if identity not in matched:
                found.append(Monitor(key=identity, name="Laptop Ekranı", kind=INTERNAL,
                                     brightness=info.brightness, controllable=True))

        found.sort(key=lambda m: (m.kind != INTERNAL, not m.primary, m.name))
        self._monitors = found
        log.info("Discovered %d monitor(s): %s", len(found),
                 ", ".join(f"{m.name}[{m.kind}{'' if m.controllable else '/no-ddc'}]"
                           for m in found))
        return list(found)

    def _build_internal(self, display: DisplayInfo, panel) -> Monitor:
        return Monitor(key=display.identity, name="Laptop Ekranı", kind=INTERNAL,
                       brightness=panel.brightness, controllable=True,
                       primary=display.is_primary)

    def _build_external(self, display: DisplayInfo) -> Monitor:
        handles = ddcci.open_physical_monitors(display.hmonitor)
        value = None
        for handle in handles:
            value = handle.read_brightness()
            if value is not None:
                break
        if value is None:
            for handle in handles:
                handle.close()
            return Monitor(key=display.identity, name=display.friendly_name,
                           kind=EXTERNAL, brightness=-1, controllable=False,
                           reason="DDC/CI yanıt vermiyor", primary=display.is_primary)
        self._handles[display.identity] = handles
        return Monitor(key=display.identity, name=display.friendly_name,
                       kind=EXTERNAL, brightness=value.to_percent(),
                       controllable=True, primary=display.is_primary)

    def read_all(self) -> list[Monitor]:
        """Cheap refresh of values only, reusing the existing handles."""
        updated: list[Monitor] = []
        for monitor in self._monitors:
            updated.append(replace(monitor, brightness=self._read(monitor)))
        self._monitors = updated
        return list(updated)

    def _read(self, monitor: Monitor) -> int:
        if not monitor.controllable:
            return monitor.brightness
        if monitor.kind == INTERNAL:
            instance = self._panel_instances.get(monitor.key)
            value = self._panel.read(instance) if instance else None
            return monitor.brightness if value is None else value
        for handle in self._handles.get(monitor.key, ()):
            value = handle.read_brightness()
            if value is not None:
                return value.to_percent()
        return monitor.brightness

    def set_percent(self, key: str, percent: int) -> bool:
        percent = max(0, min(100, int(percent)))
        instance = self._panel_instances.get(key)
        if instance is not None:
            return self._panel.set_percent(instance, percent)
        # Mirrored outputs share one HMONITOR; write every handle behind it.
        handles = self._handles.get(key)
        if handles and all(handle.set_percent(percent) for handle in handles):
            return True
        # A display mode change (resolution, HDR, a monitor waking) destroys
        # the handles without adding or removing a screen, and every write then
        # fails with ERROR_GRAPHICS_MONITOR_NO_LONGER_EXISTS. Re-acquire, retry.
        handles = self._reopen(key)
        return bool(handles) and all(handle.set_percent(percent) for handle in handles)

    def _reopen(self, key: str) -> list[ddcci.PhysicalMonitor]:
        for handle in self._handles.pop(key, ()):
            handle.close()
        for display in enumerate_displays():
            if display.identity == key:
                handles = ddcci.open_physical_monitors(display.hmonitor)
                if handles:
                    self._handles[key] = handles
                return handles
        return []

    def _release_handles(self) -> None:
        for handles in self._handles.values():
            for handle in handles:
                handle.close()
        self._handles.clear()

    def close(self) -> None:
        self._release_handles()
        self._panel.close()

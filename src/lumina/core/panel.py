"""Internal (laptop) panel brightness through WMI over COM.

Replaces the ``powershell.exe -Command (Get-WmiObject ...)`` subprocess: a read
went from ~1180 ms to ~6 ms, a write from ~1200 ms to ~8 ms.

COM apartments are per-thread, so one instance belongs to exactly one thread —
the backend worker owns it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from .discovery import normalize_identity

log = logging.getLogger(__name__)

_NAMESPACE = r"winmgmts:\\.\root\WMI"


@dataclass
class PanelInfo:
    identity: str        # DISPLAY#BOE0A41#4&3A9F8B26&3&UID8388688
    instance_name: str   # raw WMI InstanceName, needed to address the panel
    brightness: int      # already a percentage in the WMI class


class PanelBackend:
    """Thin cache over WmiMonitorBrightness / WmiMonitorBrightnessMethods.

    Every method degrades to a no-op result instead of raising: a machine with
    no WMI-controllable panel (most desktops) is normal, not an error.
    """

    def __init__(self) -> None:
        self._service = None
        self._methods: dict[str, object] = {}
        self._com_ready = False

    def _ensure_com(self) -> None:
        if self._com_ready:
            return
        import pythoncom
        pythoncom.CoInitialize()
        self._com_ready = True

    def _connect(self):
        if self._service is None:
            self._ensure_com()
            import win32com.client
            self._service = win32com.client.GetObject(_NAMESPACE)
        return self._service

    def list_panels(self) -> list[PanelInfo]:
        try:
            service = self._connect()
            rows = service.ExecQuery("SELECT * FROM WmiMonitorBrightness")
            panels = [
                PanelInfo(
                    identity=normalize_identity(row.InstanceName),
                    instance_name=row.InstanceName,
                    brightness=int(row.CurrentBrightness),
                )
                for row in rows
            ]
        except Exception as exc:  # COM failures surface as pywintypes.com_error
            log.info("WMI panel query unavailable: %s", exc)
            return []
        if panels:
            self._refresh_method_cache()
        return panels

    def _refresh_method_cache(self) -> None:
        self._methods.clear()
        try:
            service = self._connect()
            for obj in service.ExecQuery("SELECT * FROM WmiMonitorBrightnessMethods"):
                self._methods[obj.InstanceName] = obj
        except Exception as exc:
            log.warning("WmiMonitorBrightnessMethods unavailable: %s", exc)

    def read(self, instance_name: str) -> int | None:
        try:
            service = self._connect()
            for row in service.ExecQuery("SELECT * FROM WmiMonitorBrightness"):
                if row.InstanceName == instance_name:
                    return int(row.CurrentBrightness)
        except Exception as exc:
            log.warning("Panel read failed: %s", exc)
        return None

    def set_percent(self, instance_name: str, percent: int) -> bool:
        percent = max(0, min(100, int(percent)))
        obj = self._methods.get(instance_name)
        if obj is None:
            self._refresh_method_cache()
            obj = self._methods.get(instance_name)
        if obj is None:
            return False
        try:
            params = obj.Methods_("WmiSetBrightness").InParameters.SpawnInstance_()
            params.Timeout = 0        # fire and forget; waiting costs ~1 s
            params.Brightness = percent
            obj.ExecMethod_("WmiSetBrightness", params)
            return True
        except Exception as exc:
            log.warning("WmiSetBrightness(%s) failed: %s", percent, exc)
            self._methods.pop(instance_name, None)
            return False

    def close(self) -> None:
        self._methods.clear()
        self._service = None
        if self._com_ready:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass
            self._com_ready = False

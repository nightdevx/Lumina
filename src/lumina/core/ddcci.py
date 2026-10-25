"""DDC/CI control of external monitors through dxva2.dll.

Replaces the ControlMyMonitor.exe subprocess: a read went from ~7.8 s to ~60 ms.
Handles are expensive relative to a single call, so callers keep them open for
the lifetime of a display configuration and re-acquire when a write fails.
"""
from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes
from dataclasses import dataclass

log = logging.getLogger(__name__)

_dxva2 = ctypes.WinDLL("dxva2", use_last_error=True)
_user32 = ctypes.WinDLL("user32", use_last_error=True)

VCP_BRIGHTNESS = 0x10
VCP_CONTRAST = 0x12

_DESCRIPTION_SIZE = 128


class PHYSICAL_MONITOR(ctypes.Structure):
    _fields_ = [
        ("hPhysicalMonitor", wintypes.HANDLE),
        ("szPhysicalMonitorDescription", wintypes.WCHAR * _DESCRIPTION_SIZE),
    ]


_LPDWORD = ctypes.POINTER(wintypes.DWORD)

# Explicit signatures matter on 64-bit: without argtypes ctypes truncates
# HANDLE values to int and every subsequent call fails with ERROR_INVALID_HANDLE.
_dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [wintypes.HMONITOR, _LPDWORD]
_dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
_dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [
    wintypes.HMONITOR, wintypes.DWORD, ctypes.POINTER(PHYSICAL_MONITOR)]
_dxva2.GetPhysicalMonitorsFromHMONITOR.restype = wintypes.BOOL
_dxva2.DestroyPhysicalMonitor.argtypes = [wintypes.HANDLE]
_dxva2.DestroyPhysicalMonitor.restype = wintypes.BOOL
_dxva2.GetMonitorBrightness.argtypes = [wintypes.HANDLE, _LPDWORD, _LPDWORD, _LPDWORD]
_dxva2.GetMonitorBrightness.restype = wintypes.BOOL
_dxva2.SetMonitorBrightness.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_dxva2.SetMonitorBrightness.restype = wintypes.BOOL
_dxva2.GetVCPFeatureAndVCPFeatureReply.argtypes = [
    wintypes.HANDLE, wintypes.BYTE, _LPDWORD, _LPDWORD, _LPDWORD]
_dxva2.GetVCPFeatureAndVCPFeatureReply.restype = wintypes.BOOL
_dxva2.SetVCPFeature.argtypes = [wintypes.HANDLE, wintypes.BYTE, wintypes.DWORD]
_dxva2.SetVCPFeature.restype = wintypes.BOOL


@dataclass(frozen=True)
class VcpValue:
    """Raw VCP reading. `maximum` is per-monitor — 100 on most panels, but 255
    and other ranges exist, so never assume a 0-100 scale."""
    minimum: int
    current: int
    maximum: int

    def to_percent(self) -> int:
        span = self.maximum - self.minimum
        if span <= 0:
            return 0
        return round((self.current - self.minimum) * 100 / span)

    def percent_to_raw(self, percent: int) -> int:
        percent = max(0, min(100, percent))
        span = self.maximum - self.minimum
        return self.minimum + round(span * percent / 100)


class PhysicalMonitor:
    """One DDC/CI-addressable monitor. Not thread-safe: the DDC/CI bus is
    serial, so all calls belong on the single backend thread."""

    __slots__ = ("_handle", "description", "_closed", "_range")

    def __init__(self, handle: int, description: str) -> None:
        self._handle = handle
        self.description = description
        self._closed = False
        self._range: VcpValue | None = None

    def read_brightness(self) -> VcpValue | None:
        """None means the monitor does not answer DDC/CI (laptop eDP panels,
        monitors with DDC/CI disabled in their OSD, some KVMs and docks)."""
        if self._closed:
            return None
        mn, cur, mx = wintypes.DWORD(), wintypes.DWORD(), wintypes.DWORD()
        ok = _dxva2.GetMonitorBrightness(
            self._handle, ctypes.byref(mn), ctypes.byref(cur), ctypes.byref(mx))
        if not ok:
            log.debug("GetMonitorBrightness failed for %s (err=%s)",
                      self.description, ctypes.get_last_error())
            return None
        value = VcpValue(mn.value, cur.value, mx.value)
        self._range = value
        return value

    def set_percent(self, percent: int) -> bool:
        """Write brightness as a percentage of this monitor's own VCP range."""
        if self._closed:
            return False
        scale = self._range or self.read_brightness()
        if scale is None:
            return False
        raw = scale.percent_to_raw(percent)
        ok = bool(_dxva2.SetMonitorBrightness(self._handle, raw))
        if ok:
            # Track locally so the next set_percent skips a bus round-trip.
            self._range = VcpValue(scale.minimum, raw, scale.maximum)
        else:
            log.warning("SetMonitorBrightness(%s%%->%s) failed for %s (err=%s)",
                        percent, raw, self.description, ctypes.get_last_error())
        return ok

    def read_contrast(self) -> VcpValue | None:
        if self._closed:
            return None
        cur, mx = wintypes.DWORD(), wintypes.DWORD()
        kind = wintypes.DWORD()
        ok = _dxva2.GetVCPFeatureAndVCPFeatureReply(
            self._handle, VCP_CONTRAST, ctypes.byref(kind),
            ctypes.byref(cur), ctypes.byref(mx))
        return VcpValue(0, cur.value, mx.value) if ok else None

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._handle:
            _dxva2.DestroyPhysicalMonitor(self._handle)
        self._handle = 0


def open_physical_monitors(hmonitor: int) -> list[PhysicalMonitor]:
    """Acquire every physical monitor behind one HMONITOR (a mirrored or
    daisy-chained adapter can expose more than one)."""
    count = wintypes.DWORD()
    if not _dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hmonitor, ctypes.byref(count)):
        log.debug("GetNumberOfPhysicalMonitorsFromHMONITOR failed (err=%s)",
                  ctypes.get_last_error())
        return []
    if count.value == 0:
        return []
    array = (PHYSICAL_MONITOR * count.value)()
    if not _dxva2.GetPhysicalMonitorsFromHMONITOR(hmonitor, count.value, array):
        log.debug("GetPhysicalMonitorsFromHMONITOR failed (err=%s)",
                  ctypes.get_last_error())
        return []
    return [PhysicalMonitor(pm.hPhysicalMonitor, pm.szPhysicalMonitorDescription)
            for pm in array]

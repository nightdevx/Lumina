"""Enumerate attached displays and give each one a stable identity.

Identity comes from the device interface path, which contains the EDID
manufacturer/product id plus the hardware instance:

    \\\\?\\DISPLAY#GSM7714#5&9063784&1&UID4352#{guid}
                   ^^^^^^^ ^^^^^^^^^^^^^^^^^^^
                   pnp id  instance id

WMI reports the internal panel with the same two parts (as
``DISPLAY\\BOE0A41\\4&3a9f8b26&3&UID8388688_0``), which is what lets us tell the
laptop panel apart from external monitors without guessing.
"""
from __future__ import annotations

import ctypes
import logging
import winreg
from ctypes import wintypes
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

_user32 = ctypes.WinDLL("user32", use_last_error=True)

EDD_GET_DEVICE_INTERFACE_NAME = 0x00000001
MONITORINFOF_PRIMARY = 0x00000001


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", wintypes.WCHAR * 32),
        ("DeviceString", wintypes.WCHAR * 128),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", wintypes.WCHAR * 128),
        ("DeviceKey", wintypes.WCHAR * 128),
    ]


_MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
    ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

_user32.EnumDisplayMonitors.argtypes = [
    wintypes.HDC, ctypes.POINTER(wintypes.RECT), _MONITORENUMPROC, wintypes.LPARAM]
_user32.EnumDisplayMonitors.restype = wintypes.BOOL
_user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
_user32.GetMonitorInfoW.restype = wintypes.BOOL
_user32.EnumDisplayDevicesW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DISPLAY_DEVICEW), wintypes.DWORD]
_user32.EnumDisplayDevicesW.restype = wintypes.BOOL


@dataclass
class DisplayInfo:
    hmonitor: int
    adapter: str          # \\.\DISPLAY5
    device_name: str      # \\.\DISPLAY5\Monitor0
    device_string: str    # "Generic PnP Monitor"
    identity: str         # DISPLAY#GSM7714#5&9063784&1&UID4352
    pnp_id: str           # GSM7714
    instance_id: str      # 5&9063784&1&UID4352
    is_primary: bool
    edid: bytes | None = field(default=None, repr=False)

    @property
    def friendly_name(self) -> str:
        """Real model name from EDID, falling back to the driver's generic
        string so a card is never nameless."""
        if self.edid:
            name = parse_edid_name(self.edid)
            if name:
                return name
            vendor = parse_edid_vendor(self.edid)
            if vendor:
                return f"{vendor} {self.pnp_id[3:]}".strip()
        return self.device_string or self.pnp_id or "Monitör"


def normalize_identity(raw: str) -> str:
    """Fold the several spellings Windows uses for the same display into one.

    Accepts a device interface path, a WMI InstanceName or an already
    normalized identity, and returns ``DISPLAY#<pnp>#<instance>`` uppercased.
    """
    text = raw.replace("\\", "#").upper()
    text = text.lstrip("#?")
    parts = [p for p in text.split("#") if p]
    try:
        start = parts.index("DISPLAY")
    except ValueError:
        return text
    parts = parts[start:start + 3]
    if len(parts) == 3 and "_" in parts[2]:
        # WMI appends an "_0" ordinal that the interface path does not carry.
        parts[2] = parts[2].rsplit("_", 1)[0]
    return "#".join(parts)


def parse_edid_name(edid: bytes) -> str | None:
    """Descriptor tag 0xFC holds the model name, e.g. "27GL850"."""
    if len(edid) < 128:
        return None
    for offset in (54, 72, 90, 108):
        block = edid[offset:offset + 18]
        if len(block) < 18 or block[0:3] != b"\x00\x00\x00" or block[3] != 0xFC:
            continue
        name = block[5:18].split(b"\x0a")[0].decode("ascii", "ignore").strip()
        if name:
            return name
    return None


def parse_edid_vendor(edid: bytes) -> str | None:
    """Bytes 8-9 pack three 5-bit letters, the PNP manufacturer code."""
    if len(edid) < 10:
        return None
    packed = (edid[8] << 8) | edid[9]
    letters = "".join(chr(((packed >> shift) & 0x1F) + ord("A") - 1)
                      for shift in (10, 5, 0))
    return letters if letters.isalpha() else None


def read_edid(pnp_id: str, instance_id: str) -> bytes | None:
    key = rf"SYSTEM\CurrentControlSet\Enum\DISPLAY\{pnp_id}\{instance_id}\Device Parameters"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as handle:
            value, _ = winreg.QueryValueEx(handle, "EDID")
            return bytes(value)
    except OSError:
        return None


def _monitor_handles() -> list[int]:
    handles: list[int] = []

    def callback(hmonitor, _hdc, _rect, _param):
        handles.append(int(hmonitor))
        return True

    proc = _MONITORENUMPROC(callback)
    if not _user32.EnumDisplayMonitors(None, None, proc, 0):
        log.warning("EnumDisplayMonitors failed (err=%s)", ctypes.get_last_error())
    return handles


def enumerate_displays() -> list[DisplayInfo]:
    displays: list[DisplayInfo] = []
    for hmonitor in _monitor_handles():
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if not _user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            continue

        device = DISPLAY_DEVICEW()
        device.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        if not _user32.EnumDisplayDevicesW(info.szDevice, 0, ctypes.byref(device), 0):
            continue
        device_name, device_string = device.DeviceName, device.DeviceString

        # Second pass with the interface flag: DeviceID then carries the
        # instance id we need for both the EDID lookup and the WMI match.
        iface = DISPLAY_DEVICEW()
        iface.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        _user32.EnumDisplayDevicesW(info.szDevice, 0, ctypes.byref(iface),
                                    EDD_GET_DEVICE_INTERFACE_NAME)

        identity = normalize_identity(iface.DeviceID or device.DeviceID)
        parts = identity.split("#")
        pnp_id = parts[1] if len(parts) > 1 else ""
        instance_id = parts[2] if len(parts) > 2 else ""

        displays.append(DisplayInfo(
            hmonitor=hmonitor,
            adapter=info.szDevice,
            device_name=device_name,
            device_string=device_string,
            identity=identity,
            pnp_id=pnp_id,
            instance_id=instance_id,
            is_primary=bool(info.dwFlags & MONITORINFOF_PRIMARY),
            edid=read_edid(pnp_id, instance_id) if pnp_id and instance_id else None,
        ))
    return displays

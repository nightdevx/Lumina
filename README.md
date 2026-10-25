<div align="center">

<img src="docs/images/logo.png" width="110" alt="LUMINA">

# LUMINA

**Brightness control for every screen on a Windows machine — the laptop panel and DDC/CI monitors, from one slider in the notification area.**

[![Platform](https://img.shields.io/badge/platform-Windows%2010%20%2F%2011-0078D4)](#install)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](#development)
[![Qt](https://img.shields.io/badge/UI-PySide6-41CD52)](#architecture)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[Türkçe README](README.tr.md)

<img src="docs/images/hero.png" width="900" alt="LUMINA main window and quick panel">

</div>

---

External monitors have no brightness key. Windows exposes a slider only for the
built-in panel, so the desk monitor gets adjusted through its own OSD buttons —
or not at all.

LUMINA drives both from the same place. The laptop panel goes through WMI, the
external monitors through DDC/CI over the display cable, and neither path
shells out to another program.

## Features

<table>
<tr>
<td width="58%" valign="top">

**Everything on one slider set.** Internal and external monitors appear side by
side. A monitor that will not answer DDC/CI says so instead of pretending —
no silent fallback to a made-up value.

**Tray flyout.** One left click on the notification area icon puts the sliders
under the cursor, positioned to stay on whichever screen the mouse is on and
flipping below the cursor when the taskbar sits at the top.

**Sync mode.** One slider moves every monitor together.

**Scheduler.** Time ranges with a target brightness, including overnight ranges
like `22:00 → 06:00`.

**Smooth transitions.** A scheduled change ramps over a configurable duration
instead of snapping. Touching a slider cancels a running ramp.

**Hotplug aware.** Plug or unplug a display and the list updates itself.

**Starts with Windows.** Straight to the notification area, no window flash.

</td>
<td width="42%" valign="top">

<img src="docs/images/quick-panel.png" width="100%" alt="Quick panel">

</td>
</tr>
</table>

### Screens

| Monitors | Scheduler | Settings |
|---|---|---|
| <img src="docs/images/monitors.png" alt="Monitors page"> | <img src="docs/images/schedule.png" alt="Scheduler page"> | <img src="docs/images/settings.png" alt="Settings page"> |
| Every display, live percentage, and a clear reason when one cannot be driven. | Overnight ranges are marked. Rules save as you edit them. | Autostart, sync, transition length, and a shortcut to the log folder. |

## Install

Download `LuminaSetup-<version>.exe` from
[Releases](../../releases/latest) and run it.

- No administrator rights. Installs per user under `%LOCALAPPDATA%\Programs\Lumina`.
- Python is not required — the runtime is bundled.
- 19.9 MB installer, ~62 MB installed.

> **SmartScreen.** The installer is unsigned, so Windows shows a warning the
> first time: **More info → Run anyway**. A code signing certificate costs a few
> hundred dollars a year; if that changes, `build.ps1` has a place for the
> `signtool` step.

Uninstall from Settings → Apps as normal. Your `config.json` is left in place;
delete `%APPDATA%\Lumina` to remove it too.

## Why it is fast

The previous version of this app called two external programs for every
operation: `ControlMyMonitor.exe` for the external monitors and `powershell.exe`
for the laptop panel. A process spawn per slider tick is the entire performance
story.

LUMINA calls the Windows APIs those programs wrap. Measured on the same machine
(Intel laptop panel + LG UltraWide over DisplayPort):

| Operation | Via subprocess | Direct API | |
|---|--:|--:|--:|
| Full monitor scan | 8000 ms | **135 ms** | 59× |
| External monitor read | 7840 ms | **62 ms** | 126× |
| External monitor write | 170 ms | **60 ms** | 2.8× |
| Internal panel read | 1183 ms | **4 ms** | 296× |
| Internal panel write | 1200 ms | **7 ms** | 171× |

The 60 ms floor on an external write is the DDC/CI I²C bus itself — no software
gets under it. What software *can* fix is the queue: while a write is in flight,
newer slider values overwrite the pending one instead of lining up behind it, so
a drag applies the value you stopped on and never replays the path you took to
get there.

Reproduce the numbers on your own hardware:

```powershell
.venv\Scripts\python.exe tools\smoke_core.py
```

Runtime cost: **927 ms** cold start, **413 ms** warm, **0.00 %** CPU while idle,
~72 MB working set (~34 MB private).

## Architecture

| Concern | Mechanism |
|---|---|
| External monitors | `dxva2.dll` — `GetMonitorBrightness` / `SetMonitorBrightness`, with `SetVCPFeature` available for other VCP codes |
| Internal panel | `WmiMonitorBrightnessMethods` over COM |
| Display enumeration | `EnumDisplayMonitors` + `EnumDisplayDevices` |
| Monitor names | EDID descriptor `0xFC` from the registry, so a card reads `LG HDR WFHD` rather than `Generic PnP Monitor` |
| Internal vs external | The device interface path and the WMI `InstanceName` both contain the PNP id and hardware instance; normalising them makes the match exact rather than a guess |
| Hotplug | The worker polls a cheap display fingerprint every 2 s while idle and rescans when it changes; a failed DDC/CI write re-acquires that monitor's handles and retries |

Everything below the UI runs on one worker thread, which is also where the COM
apartment and the DDC/CI handles live. The GUI thread never blocks on a bus
round-trip.

```
src/lumina/
  core/
    ddcci.py       dxva2 ctypes wrapper, per-monitor VCP range handling
    panel.py       WMI over COM
    discovery.py   enumeration, identity normalisation, EDID parsing
    backend.py     one Monitor list across both transports
    service.py     worker thread + write coalescing
  features/
    automation.py  schedule matching and fade ramps
    autostart.py   HKCU\...\Run
  ui/
    main_window.py  quick_panel.py  widgets.py  icons.py
  resources/       theme.qss (all styling), lumina.png, lumina.ico
  app.py           the only place that knows the current monitor set
build/             lumina.spec, installer.iss, version_info.txt
tools/             smoke_core.py, preview.py, measure_startup.py
```

User data:

- Settings — `%APPDATA%\Lumina\config.json`, written atomically
- Logs — `%LOCALAPPDATA%\Lumina\logs\lumina.log`, rotating, 512 KB × 3

## Development

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe run_lumina.py --debug
```

```powershell
.venv\Scripts\python.exe -m pytest tests -q      # 39 tests, no hardware needed
.venv\Scripts\python.exe tools\smoke_core.py     # real monitors, latency report
.venv\Scripts\python.exe tools\preview.py        # regenerate docs/images
.venv\Scripts\python.exe tools\measure_startup.py
```

The test suite covers the schedule matcher (including overnight wrap), VCP
percentage scaling on non-0-100 ranges, identity normalisation, EDID parsing,
config round-trips, write coalescing against a simulated slow bus, and the full
UI-to-backend wiring with a fake backend.

### Build

```powershell
.\build.ps1               # tests, then exe, then installer
.\build.ps1 -ExeOnly      # stop after PyInstaller
.\build.ps1 -SkipTests
```

Output lands in `build\output\LuminaSetup-<version>.exe`. If Inno Setup is not
installed, `build.ps1` fetches it with winget.

PyInstaller runs in `onedir` mode. `onefile` unpacked the whole bundle into
`%TEMP%` on every launch, which is most of what made the old build feel slow to
start. The spec also drops Qt libraries the hook pulls in as binary
dependencies — the QML runtime, the software OpenGL rasteriser, the PDF module
and OpenSSL — taking the bundle from 114 MB to 61 MB.

## Troubleshooting

**A monitor shows "DDC/CI yanıt vermiyor".** The display is not answering on the
data channel. Check for a DDC/CI option in its OSD menu — it ships disabled on
some models. USB-C docks, KVM switches and some HDMI adapters also drop the
channel. Laptop panels never answer DDC/CI; they are driven through WMI and are
labelled `DAHİLİ`.

**The laptop panel is missing.** Some desktop GPUs and virtual displays expose
no `WmiMonitorBrightness` instance. Run with `--debug` and check the log.

**Brightness snaps back after a change.** Vendor software (Dell Display Manager,
LG OnScreen Control, some gaming utilities) may be writing to the same VCP code.

Logs: **Settings → GÜNLÜK KLASÖRÜNÜ AÇ**, or `%LOCALAPPDATA%\Lumina\logs`.

## Contributing

Issues and pull requests are welcome. Useful things to know:

- The UI strings are Turkish only right now. Localisation would be a good first
  contribution — the strings are inline in `src/lumina/ui/`.
- Anything touching brightness logic needs a test in `tests/`; the hardware
  layer is covered by `tools/smoke_core.py` instead.
- Run `pytest` before opening a PR; `build.ps1` refuses to build on a red suite.

## License

[MIT](LICENSE) for this project's own code.

Distributed builds bundle third-party components under their own terms — most
importantly Qt via PySide6 under the LGPL v3. See
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

# Third-party notices

LUMINA's own source is MIT ([LICENSE](LICENSE)). A distributed build bundles the
components below, each under its own terms.

## Qt, via PySide6 — LGPL v3

- Project: <https://www.qt.io/qt-for-python>
- Source: <https://code.qt.io/cgit/pyside/pyside-setup.git/>
- Qt source: <https://download.qt.io/official_releases/qt/>
- License: GNU Lesser General Public License v3
  (<https://www.gnu.org/licenses/lgpl-3.0.html>)

The installer ships Qt as separate, dynamically loaded DLLs under the
application directory (`_internal\PySide6\`). They are not statically linked and
are not modified. Anyone may replace them with their own build of the same Qt
version, which is what LGPL v3 §4(d) asks for. The build is produced by
PyInstaller in `onedir` mode specifically so this stays true — the `onefile`
alternative would embed the libraries in a single archive.

## pywin32 — PSF-style license

- Project: <https://github.com/mhammond/pywin32>
- License: <https://github.com/mhammond/pywin32/blob/main/win32/License.txt>

## CPython — PSF License Agreement

- Project: <https://www.python.org/>
- License: <https://docs.python.org/3/license.html>

## Windows APIs

`dxva2.dll`, `user32.dll` and the WMI providers are Microsoft Windows operating
system components. They are called, not redistributed.

## No longer bundled

Version 1 of this app shipped NirSoft's `ControlMyMonitor.exe`. Version 2 calls
the DDC/CI APIs directly and does not include it or any other third-party
executable.

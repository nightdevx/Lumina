# PyInstaller spec - onedir on purpose.
#
# v1 shipped onefile, which meant the 37 MB archive was unpacked into a fresh
# %TEMP%\_MEIxxxxx directory on every single launch (visible in its own logs).
# onedir starts in a fraction of the time and the installer hides the folder
# from the user anyway.
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
RESOURCES = SRC / "lumina" / "resources"

sys.path.insert(0, str(SRC))

block_cipher = None

a = Analysis(
    [str(ROOT / "build" / "entry.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[(str(RESOURCES), "resources")],
    hiddenimports=["win32com.client", "pythoncom", "pywintypes"],
    hookspath=[],
    runtime_hooks=[],
    # Qt ships far more than a tray utility needs; each of these is tens of MB.
    excludes=[
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D",
        "PySide6.QtQuickWidgets", "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel",
        "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
        "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.Qt3DCore",
        "PySide6.Qt3DRender", "PySide6.Qt3DAnimation", "PySide6.QtBluetooth",
        "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
        "PySide6.QtPositioning", "PySide6.QtPrintSupport", "PySide6.QtQuickControls2",
        "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSensors",
        "PySide6.QtSerialPort", "PySide6.QtSpatialAudio", "PySide6.QtSql",
        "PySide6.QtStateMachine", "PySide6.QtTest", "PySide6.QtTextToSpeech",
        "PySide6.QtUiTools", "PySide6.QtWebSockets", "PySide6.QtXml",
        "tkinter", "unittest", "pydoc", "doctest", "pytest", "setuptools",
        "numpy", "PIL",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# The PySide6 hook pulls in Qt libraries our excludes cannot reach, because
# they arrive as binary dependencies rather than as Python imports. Dropping
# them by name takes the bundle from 114 MB to about 65 MB.
#
# Each entry is here for a reason, not because it looked unused:
#   opengl32sw  - 20 MB software GL rasteriser; QtWidgets paints via raster
#                 and the windows platform plugin uses Direct2D/GDI.
#   Qt6Quick/Qml- QML runtime; this UI is pure QtWidgets.
#   Qt6Pdf      - PDF renderer, reachable only through the excluded QtPdf.
#   libcrypto/  - OpenSSL for TLS; the only socket here is a local named pipe.
#     libssl
#   win32ui     - pywin32's MFC wrapper, unused by win32com.
_DROP_BINARIES = (
    "opengl32sw", "qt6quick", "qt6qml", "qt6pdf", "qt6opengl",
    "libcrypto-3", "libssl-3", "win32ui", "qt6designer", "qt6test",
)
_DROP_PLUGIN_DIRS = ("qmltooling", "scenegraph", "assetimporters")
_KEEP_IMAGEFORMATS = ("qico", "qjpeg")


def _drop_binary(dest: str) -> bool:
    lowered = dest.lower().replace("\\", "/")
    if any(name in lowered for name in _DROP_BINARIES):
        return True
    if any(f"/{folder}/" in lowered for folder in _DROP_PLUGIN_DIRS):
        return True
    if "plugins/imageformats/" in lowered:
        return not any(keep in lowered for keep in _KEEP_IMAGEFORMATS)
    return False


def _drop_data(dest: str) -> bool:
    lowered = dest.lower().replace("\\", "/")
    return lowered.startswith(("pyside6/translations/", "pyside6/qml/"))


_before = len(a.binaries) + len(a.datas)
a.binaries = TOC([entry for entry in a.binaries if not _drop_binary(entry[0])])
a.datas = TOC([entry for entry in a.datas if not _drop_data(entry[0])])
print(f"[lumina] trimmed {_before - len(a.binaries) - len(a.datas)} bundled files")

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LUMINA",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,              # no console window on launch
    disable_windowed_traceback=False,
    version=str(ROOT / "build" / "version_info.txt"),
    icon=str(RESOURCES / "lumina.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="LUMINA",
)

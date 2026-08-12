"""Render the real UI to PNG without touching hardware.

    .venv\\Scripts\\python.exe tools\\preview.py [outdir] [--scale N]

Used both as a layout check while developing and to produce the images in
docs/images for the README. The monitor list is seeded rather than scanned so
the output is identical on any machine - including the third monitor that does
not answer DDC/CI, which is the state worth documenting.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

args = [a for a in sys.argv[1:] if not a.startswith("--")]
SCALE = 2
if "--scale" in sys.argv:
    SCALE = int(sys.argv[sys.argv.index("--scale") + 1])
os.environ["QT_SCALE_FACTOR"] = str(SCALE)
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")

from PySide6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap, QRadialGradient  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lumina.config import Config, ScheduleRule  # noqa: E402
from lumina.core.backend import EXTERNAL, INTERNAL, Monitor  # noqa: E402
from lumina.paths import resource_dir  # noqa: E402
from lumina.ui.main_window import MainWindow  # noqa: E402
from lumina.ui.quick_panel import QuickPanel  # noqa: E402

OUT = Path(args[0]) if args else ROOT / "docs" / "images"
OUT.mkdir(parents=True, exist_ok=True)

MONITORS = [
    Monitor("DISPLAY#BOE0A41#1", "Laptop Ekranı", INTERNAL, 42, True),
    Monitor("DISPLAY#GSM7714#1", "LG HDR WFHD", EXTERNAL, 68, True, primary=True),
    Monitor("DISPLAY#DEL4090#1", "DELL U2415", EXTERNAL, -1, False,
            "DDC/CI yanıt vermiyor"),
]

app = QApplication(sys.argv[:1])
app.setStyleSheet((resource_dir() / "theme.qss").read_text(encoding="utf-8"))

config = Config(
    sync=True,
    fade_enabled=True,
    fade_duration_ms=2000,
    schedules=[ScheduleRule("22:00", "06:00", 20), ScheduleRule("09:00", "17:00", 85)],
)

window = MainWindow(config)
window.monitors.set_monitors(MONITORS)
window.show()
app.processEvents()

popup = QuickPanel()
popup.monitors.set_monitors(MONITORS)
popup.sync_button.setChecked(True)
popup.adjustSize()
popup.show()
app.processEvents()


def shot(widget, name):
    pixmap = widget.grab()
    # grab() hands back a pixmap tagged with the 2x device pixel ratio, and
    # drawPixmap then paints it at its logical (half) size. The file on disk is
    # already full resolution, so flatten the ratio for the hero composition.
    pixmap.setDevicePixelRatio(1.0)
    pixmap.save(str(OUT / f"{name}.png"), "PNG")
    print(f"  {name}.png  {pixmap.width()}x{pixmap.height()}")
    return pixmap


print(f"writing to {OUT}")
pages = {0: "monitors", 1: "schedule", 2: "settings"}
shots = {}
for index, name in pages.items():
    window.show_page(index)
    app.processEvents()
    shots[name] = shot(window, name)

window.show_page(0)
window.set_status("MONİTÖRLER TARANIYOR…")
app.processEvents()
shot(window, "scanning")
window.set_status("")

quick = shot(popup, "quick-panel")

# ---- hero: window and popup on one backdrop -------------------------------
main = shots["monitors"]
pad = 60 * SCALE
overlap = 40 * SCALE
width = main.width() + quick.width() + pad * 3 - overlap
height = main.height() + pad * 2

hero = QPixmap(width, height)
hero.fill(QColor("#050505"))
painter = QPainter(hero)
painter.setRenderHint(QPainter.RenderHint.Antialiasing)

glow = QRadialGradient(width * 0.35, height * 0.35, width * 0.7)
glow.setColorAt(0.0, QColor(60, 60, 70, 90))
glow.setColorAt(1.0, QColor(5, 5, 5, 0))
painter.fillRect(QRect(0, 0, width, height), glow)

painter.drawPixmap(QPoint(pad, pad), main)
painter.drawPixmap(
    QPoint(pad + main.width() + pad - overlap, height - pad - quick.height()), quick)
painter.end()
hero.save(str(OUT / "hero.png"), "PNG")
print(f"  hero.png  {hero.width()}x{hero.height()}")

logo = QPixmap(str(resource_dir() / "lumina.png")).scaled(
    160, 160, Qt.AspectRatioMode.KeepAspectRatio,
    Qt.TransformationMode.SmoothTransformation)
logo.save(str(OUT / "logo.png"), "PNG")
print("  logo.png  160x160")
print(f"\n{len(list(OUT.glob('*.png')))} images in {OUT.resolve()}")

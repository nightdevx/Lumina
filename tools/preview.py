"""Render every page and the tray popup to PNG without touching hardware.

    .venv\\Scripts\\python.exe tools\\preview.py [outdir]

Fake monitors on purpose: this checks layout and styling, not DDC/CI.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from lumina.config import Config, ScheduleRule  # noqa: E402
from lumina.core.backend import EXTERNAL, INTERNAL, Monitor  # noqa: E402
from lumina.paths import resource_dir  # noqa: E402
from lumina.ui.main_window import MainWindow  # noqa: E402
from lumina.ui.quick_panel import QuickPanel  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "preview")
OUT.mkdir(parents=True, exist_ok=True)

MONITORS = [
    Monitor("k1", "Laptop Ekranı", INTERNAL, 42, True, primary=False),
    Monitor("k2", "LG HDR WFHD", EXTERNAL, 68, True, primary=True),
    Monitor("k3", "Dell U2415", EXTERNAL, -1, False, "DDC/CI yanıt vermiyor"),
]

app = QApplication(sys.argv[:1])
app.setStyleSheet((resource_dir() / "theme.qss").read_text(encoding="utf-8"))

config = Config(
    sync=True,
    schedules=[ScheduleRule("22:00", "06:00", 20), ScheduleRule("09:00", "17:00", 85)],
)

window = MainWindow(config)
window.monitors.set_monitors(MONITORS)
window.set_status("MONİTÖRLER TARANIYOR…")
window.show()
app.processEvents()

for index, name in enumerate(("monitors", "schedule", "settings")):
    window.show_page(index)
    app.processEvents()
    window.grab().save(str(OUT / f"page-{index}-{name}.png"), "PNG")

popup = QuickPanel()
popup.monitors.set_monitors(MONITORS)
popup.sync_button.setChecked(True)
popup.adjustSize()
popup.show()
app.processEvents()
popup.grab().save(str(OUT / "quick-panel.png"), "PNG")

print("wrote", len(list(OUT.glob("*.png"))), "images to", OUT.resolve())

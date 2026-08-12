"""One QApplication for the whole session.

Qt allows exactly one application object per process, and it must be a
QApplication (not a bare QCoreApplication) before any QWidget exists -
otherwise the widget tests take the process down with them.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()

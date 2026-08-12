"""Entry point. Single instance, styling, then hand off to LuminaApp."""
from __future__ import annotations

import argparse
import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from . import __version__, logging_setup
from .paths import resource_dir

SERVER_NAME = "LuminaSingleInstance.v2"
log = logging.getLogger("lumina")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="lumina", add_help=True)
    parser.add_argument("--tray", action="store_true",
                        help="start minimised to the notification area")
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    parser.add_argument("--version", action="version", version=f"LUMINA {__version__}")
    return parser.parse_args(argv)


def _signal_running_instance() -> bool:
    """True when another instance answered and was asked to show itself."""
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if not socket.waitForConnected(300):
        return False
    socket.write(b"show")
    socket.flush()
    socket.waitForBytesWritten(300)
    socket.disconnectFromServer()
    return True


def _listen(on_show) -> QLocalServer:
    server = QLocalServer()
    # A hard kill leaves the pipe behind; without this the next launch would
    # think it is a duplicate and exit immediately.
    QLocalServer.removeServer(SERVER_NAME)
    server.listen(SERVER_NAME)

    def handle():
        connection = server.nextPendingConnection()
        if connection is not None:
            connection.readyRead.connect(lambda: (connection.readAll(), on_show()))
            connection.disconnected.connect(connection.deleteLater)

    server.newConnection.connect(handle)
    return server


def _load_stylesheet() -> str:
    try:
        return (resource_dir() / "theme.qss").read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("Stylesheet missing (%s); falling back to platform style", exc)
        return ""


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    logging_setup.setup(args.debug)
    logging_setup.install_excepthook()
    log.info("LUMINA %s starting (tray=%s, frozen=%s)",
             __version__, args.tray, getattr(sys, "frozen", False))

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("LUMINA")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Lumina")
    app.setQuitOnLastWindowClosed(False)   # tray app: closing the window stays running

    if _signal_running_instance():
        log.info("Another instance is running; asked it to show and exiting")
        return 0

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "LUMINA",
                             "Bildirim alanı kullanılamıyor, uygulama başlatılamaz.")
        return 1

    app.setStyleSheet(_load_stylesheet())

    from .app import LuminaApp   # imported late so a Qt failure logs first
    controller = LuminaApp(app, start_hidden=args.tray)
    server = _listen(controller.show_from_second_instance)
    app.aboutToQuit.connect(server.close)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

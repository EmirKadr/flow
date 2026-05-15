"""Capture screenshots of Windows-app shell states.

The actual planning UI is the same web app and is covered by visual_smoke.py.
This tool captures desktop-specific wrapper states that are otherwise hard to
see in service tests: loading, connection error, and loaded shell container.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "artifacts" / "desktop-shell"


class FakeSignal:
    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        self._callbacks.append(callback)

    def emit(self, *args):
        for callback in list(self._callbacks):
            callback(*args)


class FakeWorker:
    def __init__(self):
        self.healthy = FakeSignal()
        self.error = FakeSignal()
        self.finished = FakeSignal()
        self._running = False

    def start(self):
        self._running = True

    def isRunning(self):
        return self._running

    def wait(self, *_args):
        self._running = False
        return True

    def deleteLater(self):
        self._running = False


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["BEMANNING_DISABLE_UPDATE_CHECK"] = "1"
    sys.path.insert(0, str(ROOT))

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QLabel

    from desktop.app import MainWindow
    from services.health_service import HealthInfo

    app = QApplication.instance() or QApplication([])

    def browser_factory(parent=None):
        label = QLabel("Webbappen renderas här i Windows-klienten.", parent)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("font-size: 22px; font-weight: 700; color: #0f172a; background: #f5f7fb;")
        return label

    worker = FakeWorker()
    window = MainWindow(
        browser_factory=browser_factory,
        health_worker_factory=lambda: worker,
    )
    window.resize(1400, 900)
    window.show()
    app.processEvents()

    captures = [
        ("desktop-loading.png", lambda: None),
        ("desktop-error.png", lambda: worker.error.emit("Simulerat anslutningsfel till servern")),
        ("desktop-loaded-shell.png", lambda: worker.healthy.emit(HealthInfo(status="ok", environment="visual-test"))),
    ]

    for filename, action in captures:
        action()
        app.processEvents()
        window.grab().save(str(args.output / filename))

    window.close()
    app.processEvents()
    print(f"Desktop shell screenshots written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

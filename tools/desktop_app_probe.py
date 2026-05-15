"""Probe Windows-app behavior.

Default mode is deterministic and safe in headless agent sessions: it exercises
the PyQt shell with a fake embedded browser, captures loading/error/loaded
states, and verifies the shell asks the browser to load the configured server.

Use `--real-webengine` on a machine where Qt WebEngine can render to test the
real embedded browser as well. Some CI/agent sessions cannot run QWebEngine;
the parent process records that diagnostic instead of crashing the whole run.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime

from tools import visual_smoke


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "desktop-app"


@dataclass
class ProbeStep:
    name: str
    screenshot: str | None = None
    detail: str = ""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="Use an already running server.")
    parser.add_argument("--output", type=Path, help="Output directory.")
    parser.add_argument("--real-webengine", action="store_true", help="Also try the real QWebEngine shell.")
    parser.add_argument("--_real-child", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


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
        self.running = False

    def start(self):
        self.running = True

    def isRunning(self):
        return self.running

    def wait(self, *_args):
        self.running = False
        return True

    def deleteLater(self):
        self.running = False


def run_shell_probe(*, output_dir: Path, base_url: str) -> list[ProbeStep]:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["BEMANNING_DISABLE_UPDATE_CHECK"] = "1"
    os.environ["BEMANNING_SERVER_BASE_URL"] = base_url
    sys.path.insert(0, str(ROOT))

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QLabel

    from desktop.app import MainWindow
    from services.health_service import HealthInfo

    app = QApplication.instance() or QApplication([])
    worker = FakeWorker()
    loaded_urls: list[str] = []

    class FakeBrowser(QLabel):
        def __init__(self, parent=None):
            super().__init__("Webbappen renderas här i Windows-klienten.", parent)
            self.loadFinished = FakeSignal()
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setStyleSheet("font-size: 22px; font-weight: 700; color: #0f172a; background: #f5f7fb;")

        def load(self, url):
            loaded_urls.append(url.toString())
            self.loadFinished.emit(True)

    window = MainWindow(
        browser_factory=lambda parent=None: FakeBrowser(parent),
        health_worker_factory=lambda: worker,
    )
    window.resize(1400, 900)
    window.show()
    app.processEvents()

    steps: list[ProbeStep] = []

    def screenshot(name: str) -> str:
        path = output_dir / f"{name}.png"
        window.grab().save(str(path))
        return str(path.relative_to(output_dir))

    try:
        steps.append(ProbeStep("desktop_loading", screenshot("01-desktop-loading")))
        worker.error.emit("Simulerat anslutningsfel till lokal testserver")
        app.processEvents()
        steps.append(ProbeStep("desktop_error", screenshot("02-desktop-error")))
        worker.healthy.emit(HealthInfo(status="ok", environment="desktop-probe"))
        app.processEvents()
        if loaded_urls != [base_url]:
            raise RuntimeError(f"Desktop shell loaded {loaded_urls}, expected {[base_url]}")
        steps.append(ProbeStep("desktop_loaded_shell", screenshot("03-desktop-loaded-shell"), base_url))
    finally:
        window.close()
        app.processEvents()

    return steps


def run_real_webengine_child(*, output_dir: Path, base_url: str) -> int:
    env = os.environ.copy()
    env.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    env["BEMANNING_DISABLE_UPDATE_CHECK"] = "1"
    env["BEMANNING_SERVER_BASE_URL"] = base_url
    command = [
        sys.executable,
        "-m",
        "tools.desktop_app_probe",
        "--_real-child",
        "--base-url",
        base_url,
        "--output",
        str(output_dir),
    ]
    result = subprocess.run(command, cwd=ROOT, env=env)
    return int(result.returncode)


def run_real_webengine_probe(*, output_dir: Path, base_url: str) -> list[ProbeStep]:
    from PyQt6.QtCore import QEventLoop, QTimer
    from desktop.app import MainWindow
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.resize(1400, 900)
    window.show()
    app.processEvents()

    steps: list[ProbeStep] = []

    def screenshot(name: str) -> str:
        app.processEvents()
        path = output_dir / f"{name}.png"
        window.grab().save(str(path))
        return str(path.relative_to(output_dir))

    def run_js(script: str):
        loop = QEventLoop()
        result_box = {"value": None}

        def done(value):
            result_box["value"] = value
            loop.quit()

        window._browser.page().runJavaScript(script, done)
        QTimer.singleShot(10000, loop.quit)
        loop.exec()
        return result_box["value"]

    def wait_js(predicate: str, timeout_ms: int = 20000) -> bool:
        deadline = datetime.now().timestamp() + timeout_ms / 1000
        while datetime.now().timestamp() < deadline:
            app.processEvents()
            if run_js(f"Boolean({predicate})"):
                return True
            loop = QEventLoop()
            QTimer.singleShot(250, loop.quit)
            loop.exec()
        return False

    try:
        if not wait_js("document.querySelector('#login-form')"):
            raise RuntimeError("Real QWebEngine did not load login form")
        steps.append(ProbeStep("real_loaded_login", screenshot("real-01-login")))
        run_js(
            """
            document.querySelector('#username').value = 'admin';
            document.querySelector('#password').value = 'admin123';
            document.querySelector('#login-form').dispatchEvent(new Event('submit', {bubbles:true, cancelable:true}));
            """
        )
        if not wait_js("document.querySelector('#scheduleTable')"):
            raise RuntimeError("Real QWebEngine did not reach schedule")
        steps.append(ProbeStep("real_login_admin", screenshot("real-02-schedule")))
    finally:
        window.close()
        app.processEvents()

    return steps


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output or (DEFAULT_OUTPUT_ROOT / datetime.now().strftime("%Y%m%d-%H%M%S"))
    output_dir.mkdir(parents=True, exist_ok=True)

    if args._real_child:
        results = run_real_webengine_probe(output_dir=output_dir, base_url=args.base_url or "")
        (output_dir / "real-webengine-report.json").write_text(
            json.dumps([step.__dict__ for step in results], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return 0

    server = None
    base_url = args.base_url
    if not base_url:
        base_url, server = visual_smoke.start_local_server(output_dir)

    try:
        results = run_shell_probe(output_dir=output_dir, base_url=base_url)
        real_returncode: int | None = None
        if args.real_webengine:
            real_returncode = run_real_webengine_child(output_dir=output_dir, base_url=base_url)
            detail = "ok" if real_returncode == 0 else f"failed with exit code {real_returncode}"
            results.append(ProbeStep("real_webengine_probe", detail=detail))
    finally:
        if server:
            server.close()

    report = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "base_url": base_url,
        "real_webengine_requested": bool(args.real_webengine),
        "results": [step.__dict__ for step in results],
    }
    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Desktop app probe completed: {len(results)} steps")
    print(f"Output written to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

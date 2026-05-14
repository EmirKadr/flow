"""Qt desktop shell for the central Bemanning web app."""
from __future__ import annotations

import ctypes
import os
import sys
import tempfile
import webbrowser
from pathlib import Path
from typing import Callable, Optional


# Windows 11 DWM-attribut för att färga title-baren så den smälter in med appen.
# Stöds från Windows 11 22H2 (build 22621+). Misslyckas tyst på äldre versioner.
_DWMWA_BORDER_COLOR = 34
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36


def _hex_to_colorref(hex_color: str) -> int:
    """#RRGGBB → Windows COLORREF (0x00BBGGRR)."""
    h = hex_color.lstrip("#")
    return int(h[4:6] + h[2:4] + h[0:2], 16)


def apply_windows_titlebar_blend(hwnd: int) -> None:
    """Färga title-baren så den matchar appens ljusa tema (Teams/Word-lookalike)."""
    if sys.platform != "win32":
        return
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
    except OSError:
        return
    set_attr = dwmapi.DwmSetWindowAttribute

    def _set(attr: int, hex_color: str) -> None:
        value = ctypes.c_int(_hex_to_colorref(hex_color))
        try:
            set_attr(
                ctypes.wintypes.HWND(hwnd) if hasattr(ctypes, "wintypes") else hwnd,
                attr,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
        except Exception:
            pass

    # Matcha CSS-temat (var(--bg) = #f5f7fb, --border = #e4e8ef, --text = #0f172a)
    _set(_DWMWA_CAPTION_COLOR, "#f5f7fb")
    _set(_DWMWA_BORDER_COLOR, "#e4e8ef")
    _set(_DWMWA_TEXT_COLOR, "#0f172a")

from PyQt6.QtCore import QProcess, Qt, QTimer, QUrl
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.app_info import (
    APP_NAME,
    APP_TITLE,
    APP_VERSION,
    GITHUB_RELEASES_URL,
    SERVER_BASE_URL,
    UPDATE_DISABLED_ENV,
)
from desktop.web_view import create_web_view
from desktop.widgets.error_view import ErrorView
from desktop.workers.health_worker import HealthCheckWorker
from desktop.workers.update_worker import UpdateCheckWorker, UpdateDownloadWorker


SILENT_UPDATE_ARGS = [
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART",
    "/CLOSEAPPLICATIONS",
    "/FORCECLOSEAPPLICATIONS",
]


class MainWindow(QMainWindow):
    def __init__(
        self,
        browser_factory: Optional[Callable[..., QWidget]] = None,
        health_worker_factory: Optional[Callable[[], object]] = None,
        update_check_worker_factory: Optional[Callable[[], object]] = None,
        update_download_worker_factory: Optional[
            Callable[[object, Path], object]
        ] = None,
    ):
        super().__init__()
        self._browser_factory = browser_factory or create_web_view
        self._health_worker_factory = health_worker_factory or (
            lambda: HealthCheckWorker(SERVER_BASE_URL)
        )
        self._update_check_worker_factory = update_check_worker_factory or (
            lambda: UpdateCheckWorker(APP_VERSION)
        )
        self._update_download_worker_factory = update_download_worker_factory or (
            lambda info, target_dir: UpdateDownloadWorker(info, target_dir)
        )

        self._health_worker = None
        self._update_check_worker = None
        self._update_download_worker = None
        self._update_progress: Optional[QProgressDialog] = None

        self.setWindowTitle(APP_TITLE)
        self.resize(1400, 900)
        self.setMinimumSize(980, 720)
        self._setup_menu()
        self.menuBar().hide()
        self.statusBar().hide()

        # Färga title-baren så den smälter in med appen på Windows 11
        QTimer.singleShot(0, lambda: apply_windows_titlebar_blend(int(self.winId())))

        self._stack = QStackedWidget(self)
        self.setCentralWidget(self._stack)

        self._loading_view = self._make_loading_view()
        self._error_view = ErrorView(self)
        self._error_view.retry_requested.connect(self._start_health_check)
        self._error_view.open_browser_requested.connect(self._open_in_browser)
        self._browser = self._browser_factory(self)

        if hasattr(self._browser, "loadFinished"):
            self._browser.loadFinished.connect(self._on_browser_load_finished)

        self._stack.addWidget(self._loading_view)
        self._stack.addWidget(self._error_view)
        self._stack.addWidget(self._browser)
        self._stack.setCurrentWidget(self._loading_view)

        QTimer.singleShot(0, self._start_health_check)
        self._schedule_update_check()

    def _setup_menu(self) -> None:
        help_menu = self.menuBar().addMenu("&Hjälp")

        update_action = QAction("Sök efter uppdateringar", self)
        update_action.triggered.connect(lambda: self._check_for_updates(manual=True))
        help_menu.addAction(update_action)

        open_browser_action = QAction("Öppna i webbläsare", self)
        open_browser_action.triggered.connect(self._open_in_browser)
        help_menu.addAction(open_browser_action)

        release_action = QAction("Öppna releasesida", self)
        release_action.triggered.connect(lambda: webbrowser.open(GITHUB_RELEASES_URL))
        help_menu.addAction(release_action)

        help_menu.addSeparator()
        about_action = QAction(f"Om {APP_NAME}", self)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)

    def _make_loading_view(self) -> QWidget:
        container = QWidget(self)
        container.setObjectName("loadingView")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Startar Bemanning")
        title.setStyleSheet("font-size: 24px; font-weight: 700;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._loading_label = QLabel("Kontrollerar anslutning till den centrala servern…")
        self._loading_label.setWordWrap(True)
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loading_label.setStyleSheet("font-size: 15px; color: #4b5563;")

        layout.addWidget(title)
        layout.addWidget(self._loading_label)
        return container

    def _show_about_dialog(self) -> None:
        QMessageBox.about(
            self,
            f"Om {APP_NAME}",
            f"{APP_NAME}\nVersion {APP_VERSION}\nServer: {SERVER_BASE_URL}",
        )

    def _set_loading_message(self, message: str) -> None:
        self._loading_label.setText(message)
        self._stack.setCurrentWidget(self._loading_view)
        self.statusBar().showMessage(message)

    def _start_health_check(self) -> None:
        if self._health_worker and self._health_worker.isRunning():
            return

        self._set_loading_message("Kontrollerar anslutning till den centrala servern…")
        worker = self._health_worker_factory()
        worker.healthy.connect(self._on_health_ok)
        worker.error.connect(self._on_health_error)
        worker.finished.connect(lambda: self._on_health_check_finished(worker))
        self._health_worker = worker
        worker.start()

    def _on_health_ok(self, info) -> None:
        if hasattr(self._browser, "load"):
            self._browser.load(QUrl(SERVER_BASE_URL))
        self._stack.setCurrentWidget(self._browser)
        environment = getattr(info, "environment", "")
        if environment:
            self.statusBar().showMessage(f"Ansluten till servern ({environment}).", 5000)
        else:
            self.statusBar().showMessage("Ansluten till servern.", 5000)

    def _on_health_error(self, message: str) -> None:
        self._error_view.set_message(
            "Klienten kunde inte nå den centrala Bemanning-servern.\n\n"
            f"Fel: {message}"
        )
        self._stack.setCurrentWidget(self._error_view)
        self.statusBar().showMessage("Servern kunde inte nås.")

    def _on_health_check_finished(self, worker) -> None:
        if self._health_worker is worker:
            self._health_worker = None
        worker.deleteLater()

    def _on_browser_load_finished(self, ok: bool) -> None:
        if ok:
            self.statusBar().showMessage("Bemanning är redo.", 3000)
            return
        self._error_view.set_message(
            "Render svarade på health check, men själva appen kunde inte laddas.\n\n"
            "Försök igen eller öppna sidan i webbläsaren."
        )
        self._stack.setCurrentWidget(self._error_view)
        self.statusBar().showMessage("Kunde inte ladda appen.")

    def _open_in_browser(self) -> None:
        webbrowser.open(SERVER_BASE_URL)

    def _schedule_update_check(self) -> None:
        if not self._automatic_update_checks_enabled():
            return
        QTimer.singleShot(2500, lambda: self._check_for_updates(manual=False))

    def _automatic_update_checks_enabled(self) -> bool:
        if os.environ.get(UPDATE_DISABLED_ENV) == "1":
            return False
        return "pytest" not in sys.modules

    def _check_for_updates(self, manual: bool = False) -> None:
        if self._update_check_worker and self._update_check_worker.isRunning():
            if manual:
                QMessageBox.information(
                    self,
                    "Uppdatering",
                    "Söker redan efter uppdateringar.",
                )
            return

        worker = self._update_check_worker_factory()
        worker.update_available.connect(
            lambda info: self._on_update_available(info, manual)
        )
        worker.no_update.connect(lambda: self._on_no_update(manual))
        worker.error.connect(lambda msg: self._on_update_error(msg, manual))
        worker.finished.connect(lambda: self._on_update_check_finished(worker))
        self._update_check_worker = worker
        worker.start()

    def _on_update_check_finished(self, worker) -> None:
        if self._update_check_worker is worker:
            self._update_check_worker = None
        worker.deleteLater()

    def _on_no_update(self, manual: bool) -> None:
        if manual:
            QMessageBox.information(
                self,
                "Ingen uppdatering",
                f"Du kör senaste versionen av {APP_NAME}.",
            )

    def _on_update_error(self, message: str, manual: bool) -> None:
        if manual:
            QMessageBox.warning(
                self,
                "Kunde inte söka efter uppdatering",
                f"Försök igen senare.\n\n{message}",
            )

    def _on_update_available(self, info, manual: bool) -> None:
        if not info.installer_url:
            reply = QMessageBox.question(
                self,
                "Uppdatering finns",
                (
                    f"Version {info.version} finns tillgänglig, men releasen "
                    "saknar Setup.exe. Vill du öppna releasesidan?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                webbrowser.open(info.release_url)
            return

        reply = QMessageBox.question(
            self,
            "Uppdatering finns",
            (
                f"Version {info.version} finns tillgänglig.\n\n"
                "Vill du ladda ner och installera uppdateringen nu? "
                "Appen stängs automatiskt medan uppdateringen installeras."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes if manual else QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._download_update(info)

    def _download_update(self, info) -> None:
        if self._update_download_worker and self._update_download_worker.isRunning():
            QMessageBox.information(
                self,
                "Uppdatering",
                "Uppdateringen laddas redan ner.",
            )
            return

        target_dir = Path(tempfile.gettempdir()) / APP_NAME / "updates"
        progress = QProgressDialog("Laddar ner uppdatering…", "Avbryt", 0, 100, self)
        progress.setWindowTitle("Uppdatering")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        worker = self._update_download_worker_factory(info, target_dir)
        progress.canceled.connect(worker.stop)
        worker.progress.connect(progress.setValue)
        worker.downloaded.connect(self._on_update_downloaded)
        worker.error.connect(self._on_update_download_error)
        worker.finished.connect(lambda: self._on_update_download_finished(worker))
        self._update_progress = progress
        self._update_download_worker = worker
        worker.start()

    def _on_update_downloaded(self, installer_path: str) -> None:
        if self._update_progress:
            self._update_progress.setValue(100)
            self._update_progress.close()

        started = QProcess.startDetached(installer_path, SILENT_UPDATE_ARGS)
        ok = bool(started[0]) if isinstance(started, tuple) else bool(started)
        if ok:
            QApplication.quit()
            return

        QMessageBox.critical(
            self,
            "Kunde inte starta uppdatering",
            f"Installeraren kunde inte startas:\n{installer_path}",
        )

    def _on_update_download_error(self, message: str) -> None:
        if self._update_progress:
            self._update_progress.close()
        QMessageBox.warning(
            self,
            "Kunde inte ladda ner uppdatering",
            f"Försök igen senare.\n\n{message}",
        )

    def _on_update_download_finished(self, worker) -> None:
        if self._update_download_worker is worker:
            self._update_download_worker = None
        self._update_progress = None
        worker.deleteLater()

    def _cleanup_workers(self) -> None:
        if self._health_worker and self._health_worker.isRunning():
            self._health_worker.wait(3000)
        if self._update_check_worker and self._update_check_worker.isRunning():
            self._update_check_worker.wait(3000)
        if self._update_download_worker and self._update_download_worker.isRunning():
            self._update_download_worker.stop()
            self._update_download_worker.wait(3000)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._cleanup_workers()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()

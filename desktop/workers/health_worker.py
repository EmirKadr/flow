"""Background worker for backend health checks."""
from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from core.app_info import SERVER_BASE_URL
from services.health_service import check_server_health


class HealthCheckWorker(QThread):
    healthy = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, base_url: str = SERVER_BASE_URL, parent=None):
        super().__init__(parent)
        self.base_url = base_url

    def run(self) -> None:
        try:
            info = check_server_health(base_url=self.base_url, attempts=8, retry_delay=1.5)
        except Exception as exc:
            self.error.emit(str(exc))
            return
        self.healthy.emit(info)

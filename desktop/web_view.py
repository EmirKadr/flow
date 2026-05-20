"""QWebEngine setup for the desktop shell."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QStandardPaths
from PyQt6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

from core.app_info import APP_NAME


def default_download_dir() -> Path:
    location = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DownloadLocation
    )
    root = Path(location) if location else Path.home() / "Downloads"
    root.mkdir(parents=True, exist_ok=True)
    return root


def configure_downloads(profile: QWebEngineProfile) -> None:
    def accept_download(download) -> None:
        filename = download.suggestedFileName() or download.downloadFileName() or "download"
        download.setDownloadDirectory(str(default_download_dir()))
        download.setDownloadFileName(filename)
        download.accept()

    profile.downloadRequested.connect(accept_download)
    profile._bemanning_download_handler = accept_download


def create_web_view(parent=None) -> QWebEngineView:
    view = QWebEngineView(parent)

    app_data_dir = Path(
        QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )
    )
    app_data_dir.mkdir(parents=True, exist_ok=True)

    profile = QWebEngineProfile(f"{APP_NAME.lower()}-profile", view)
    profile.setPersistentStoragePath(str(app_data_dir / "browser-profile"))
    profile.setCachePath(str(app_data_dir / "browser-cache"))
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
    )
    configure_downloads(profile)

    page = QWebEnginePage(profile, view)
    view.setPage(page)

    settings = view.settings()
    settings.setAttribute(
        QWebEngineSettings.WebAttribute.JavascriptEnabled,
        True,
    )
    settings.setAttribute(
        QWebEngineSettings.WebAttribute.LocalStorageEnabled,
        True,
    )
    settings.setAttribute(
        QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
        True,
    )
    return view

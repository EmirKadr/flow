"""QWebChannel bridge for desktop-local files."""
from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QObject, pyqtSlot
from PyQt6.QtWidgets import QFileDialog

from desktop.local_runtime import DesktopLocalRuntime


class DesktopFileBridge(QObject):
    def __init__(self, runtime: DesktopLocalRuntime, parent=None) -> None:
        super().__init__(parent)
        self._runtime = runtime

    @pyqtSlot(str, bool, result="QVariant")
    def chooseFiles(self, accept: str = "", multiple: bool = True) -> list[dict[str, Any]]:  # noqa: N802
        filters = _file_filters(accept)
        if multiple:
            paths, _selected = QFileDialog.getOpenFileNames(
                None,
                "Välj filer",
                "",
                filters,
            )
        else:
            path, _selected = QFileDialog.getOpenFileName(
                None,
                "Välj fil",
                "",
                filters,
            )
            paths = [path] if path else []
        entries: list[dict[str, Any]] = []
        for path in paths or []:
            try:
                entries.append(self._runtime.register_path(path))
            except Exception:
                continue
        return entries


def _file_filters(accept: str) -> str:
    text = str(accept or "").strip()
    if not text:
        return "CSV och Excel (*.csv *.txt *.xlsx *.xlsm *.xls);;Alla filer (*.*)"
    suffixes = []
    for item in text.split(","):
        item = item.strip()
        if item.startswith("."):
            suffixes.append(f"*{item}")
    if suffixes:
        return f"Valda filtyper ({' '.join(suffixes)});;Alla filer (*.*)"
    return "Alla filer (*.*)"

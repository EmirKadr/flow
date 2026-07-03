"""Katalogladdning och katalogkontext för Hämta data."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import settings
from . import core
from .core import (
    ALLOWED_OPERATORS,
    DEFAULT_CATALOG_PATH,
    ROOT_DIR,
    DataCatalog,
    DataColumn,
    DataFetchConfigError,
    DataView,
    _preferred_date_column,
    infer_prompt_period,
)


_CATALOG_CACHE: tuple[str, DataCatalog] | None = None


def clear_catalog_cache() -> None:
    global _CATALOG_CACHE
    _CATALOG_CACHE = None

def _catalog_source() -> tuple[str, str]:
    raw_json = settings.DATA_SOURCE_CATALOG_JSON.strip()
    if raw_json:
        return "env:DATA_SOURCE_CATALOG_JSON", raw_json

    configured_path = settings.DATA_SOURCE_CATALOG_PATH.strip()
    path = Path(configured_path) if configured_path else DEFAULT_CATALOG_PATH
    if not path.is_absolute():
        path = ROOT_DIR / path
    if not path.is_file():
        raise DataFetchConfigError("Extern datakatalog saknas i servermiljön.")
    try:
        return str(path), path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DataFetchConfigError(f"Kunde inte läsa extern datakatalog: {exc}") from exc


def load_catalog() -> DataCatalog:
    global _CATALOG_CACHE
    source, raw = _catalog_source()
    signature = f"{source}:{hash(raw)}"
    if _CATALOG_CACHE and _CATALOG_CACHE[0] == signature:
        return _CATALOG_CACHE[1]
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DataFetchConfigError("Extern datakatalog är inte giltig JSON.") from exc
    catalog = catalog_from_payload(payload)
    _CATALOG_CACHE = (signature, catalog)
    return catalog


def catalog_from_payload(payload: dict[str, Any]) -> DataCatalog:
    views_payload = payload.get("views") if isinstance(payload, dict) else None
    if not isinstance(views_payload, list):
        raise DataFetchConfigError("Extern datakatalog måste innehålla listan 'views'.")

    views: dict[str, DataView] = {}
    for view_payload in views_payload:
        if not isinstance(view_payload, dict):
            continue
        view_id = str(view_payload.get("id") or "").strip()
        if not view_id:
            continue
        columns: list[DataColumn] = []
        for column_payload in view_payload.get("columns") or []:
            if not isinstance(column_payload, dict):
                continue
            column_id = str(column_payload.get("id") or "").strip()
            if not column_id:
                continue
            columns.append(
                DataColumn(
                    id=column_id,
                    label_en=str(column_payload.get("label_en") or "").strip(),
                    label_sv=str(column_payload.get("label_sv") or "").strip(),
                    order=int(column_payload.get("order") or len(columns) + 1),
                )
            )
        columns.sort(key=lambda item: item.order)
        views[view_id] = DataView(
            id=view_id,
            label_en=str(view_payload.get("label_en") or "").strip(),
            label_sv=str(view_payload.get("label_sv") or "").strip(),
            columns=tuple(columns),
        )
    if not views:
        raise DataFetchConfigError("Extern datakatalog innehåller inga vyer.")
    return DataCatalog(views=views)


def catalog_summary(catalog: DataCatalog) -> dict[str, int]:
    return {
        "views": len(catalog.views),
        "columns": sum(len(view.columns) for view in catalog.views.values()),
    }


def build_catalog_context(prompt: str, catalog: DataCatalog, limit: int = 12) -> dict[str, Any]:
    views = []
    candidate_views = catalog.candidate_views(prompt, limit=limit)
    app_now = core._app_now()
    for view in candidate_views:
        views.append(
            {
                "view_id": view.id,
                "name_sv": view.label_sv,
                "name_en": view.label_en,
                "columns": [
                    {
                        "column_id": column.id,
                        "name_sv": column.label_sv,
                        "name_en": column.label_en,
                    }
                    for column in view.columns
                ],
            }
        )
    context: dict[str, Any] = {
        "operators": list(ALLOWED_OPERATORS),
        "current_date": app_now.date().isoformat(),
        "current_datetime": app_now.isoformat(timespec="seconds"),
        "candidate_views": views,
    }
    period = infer_prompt_period(prompt, app_now.date())
    if period:
        period_hint = dict(period)
        period_hint["preferred_date_columns"] = {
            view.id: column.id
            for view in candidate_views
            if (column := _preferred_date_column(view)) is not None
        }
        context["detected_period"] = period_hint
    return context

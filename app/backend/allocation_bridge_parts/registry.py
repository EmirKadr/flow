from __future__ import annotations

import csv
import hashlib
import importlib
import json
import logging
import math
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
from pathlib import Path
from types import ModuleType

from fastapi import HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.datastructures import UploadFile as StarletteUploadFile

from .compiled_data_paths import (
    article_max_path,
    ensure_article_max_file,
    ensure_bufferpall_observations_file,
    seed_article_max_file,
)


logger = logging.getLogger(__name__)


class AllocationBridgeUnavailable(RuntimeError):
    pass


class OpenAllocationExcelRequest(BaseModel):
    session_id: str
    key: str


_MODULE_LOCK = threading.Lock()
_ENGINE_MODULE: ModuleType | None = None
_FLOWS_MODULE: ModuleType | None = None
_CATALOG_MODULE: ModuleType | None = None
_DETECT_MODULE: ModuleType | None = None
_NATIVE_FLOWS_MODULE: ModuleType | None = None
_NATIVE_TABLES_MODULE: ModuleType | None = None
_YTGENERERING_MAP_MODULE: ModuleType | None = None
_LOAD_ERROR: str | None = None
SESSIONS: dict[str, dict] = {}
UPLOAD_CACHE_DIR = Path(tempfile.gettempdir()) / "flow_allocation_upload_cache"
UPLOAD_CACHE_TTL_SECONDS = 6 * 60 * 60
UPLOAD_CACHE_MAX_FILES = 64
UPLOAD_CACHE_MAX_BYTES = 512 * 1024 * 1024
UPLOAD_READ_CHUNK_SIZE = 1024 * 1024
SESSION_CACHE_DIR = Path(tempfile.gettempdir()) / "flow_allocation_result_cache"
SESSION_TTL_SECONDS = 2 * 60 * 60
SESSION_MAX_COUNT = 12
SESSION_MAX_BYTES = 512 * 1024 * 1024
SESSION_ARTIFACT_INLINE_MAX_BYTES = 512 * 1024


def _active_upload_cache_dir() -> Path:
    """Returnera demo-sessionens cache-mapp om aktiv, annars den globala."""
    try:
        from .demo_session import demo_data_root_var
    except Exception:
        return UPLOAD_CACHE_DIR
    override = demo_data_root_var.get()
    if override is not None:
        return override / "allocation_upload_cache"
    return UPLOAD_CACHE_DIR


def _active_session_cache_dir() -> Path:
    try:
        from .demo_session import demo_data_root_var
    except Exception:
        return SESSION_CACHE_DIR
    override = demo_data_root_var.get()
    if override is not None:
        return override / "allocation_result_cache"
    return SESSION_CACHE_DIR
DEFAULT_MAX_CSV_PARAM = "__default_max_csv_path"
PROCESS_AREA_FOCUS_PARAM = "__process_area_focus"
YTGENERERING_UTL_MIN_PARAM = "__ytgenerering_utl_min"
YTGENERERING_UTL_MAX_PARAM = "__ytgenerering_utl_max"
YTGENERERING_UTL_DEFAULT_MIN = 1
YTGENERERING_UTL_DEFAULT_MAX = 652
PROCESS_MATRIX_ALL_CODE = "ALLT"
PROCESS_MATRIX_ALL_AREA_OPTION: dict[str, str] = {"code": PROCESS_MATRIX_ALL_CODE, "label": "Alla"}
PROCESS_AREA_RULES: dict[str, dict] = {}
PROCESS_DEFAULT_AREA_RULE: dict[str, object] = {
    "visible_flow_ids": None,
}
YTGENERERING_DEFAULT_AREA_RULES: dict[str, dict[str, int]] = {
    "DEFAULT": {"utlMin": YTGENERERING_UTL_DEFAULT_MIN, "utlMax": YTGENERERING_UTL_DEFAULT_MAX},
}
USER_FILTERS_PARAM = "__allocation_user_filters_json"
USER_FILTER_PROFILE_VERSION = 1
USER_FILTER_OPERATORS = {
    "=": "EQ",
    "==": "EQ",
    "eq": "EQ",
    "EQ": "EQ",
    "!=": "NE",
    "<>": "NE",
    "ne": "NE",
    "NE": "NE",
    ">": "GT",
    "gt": "GT",
    "GT": "GT",
    ">=": "GTE",
    "gte": "GTE",
    "GTE": "GTE",
    "<": "LT",
    "lt": "LT",
    "LT": "LT",
    "<=": "LTE",
    "lte": "LTE",
    "LTE": "LTE",
    "between": "Between",
    "Between": "Between",
    "in": "In",
    "In": "In",
    "terms": "In",
    "Terms": "In",
    "not in": "NotIn",
    "not_in": "NotIn",
    "notin": "NotIn",
    "Not In": "NotIn",
    "NotIn": "NotIn",
}
def _default_warehouse_tools_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "warehouse_tools"


def warehouse_tools_dir() -> Path:
    return _default_warehouse_tools_dir()


def _ensure_tools_importable() -> None:
    tools_dir = warehouse_tools_dir()
    if not tools_dir.exists():
        raise AllocationBridgeUnavailable(f"Lagerverktygens backend hittades inte: {tools_dir}")
    tools_parent = str(tools_dir.parent)
    if tools_parent not in sys.path:
        sys.path.insert(0, tools_parent)


def _load_light_module(module_name: str, cache_name: str) -> ModuleType:
    global _CATALOG_MODULE, _DETECT_MODULE, _NATIVE_FLOWS_MODULE, _NATIVE_TABLES_MODULE
    with _MODULE_LOCK:
        cached = globals()[cache_name]
        if cached is not None:
            return cached
        _ensure_tools_importable()
        module = importlib.import_module(module_name)
        globals()[cache_name] = module
        return module


def _catalog() -> ModuleType:
    return _load_light_module("warehouse_tools.catalog", "_CATALOG_MODULE")


def _detect() -> ModuleType:
    return _load_light_module("warehouse_tools.detect", "_DETECT_MODULE")


def _native_flows() -> ModuleType:
    return _load_light_module("warehouse_tools.native_flows", "_NATIVE_FLOWS_MODULE")


def _native_tables() -> ModuleType:
    return _load_light_module("warehouse_tools.native_tables", "_NATIVE_TABLES_MODULE")


def _ytgenerering_map() -> ModuleType:
    return _load_light_module("warehouse_tools.ytgenerering_map", "_YTGENERERING_MAP_MODULE")


def ytgenerering_map_layout_payload(locations: object | None = None) -> dict[str, object]:
    return _ytgenerering_map().map_layout_payload(locations)


def normalize_ytgenerering_map_location_rows(value: object) -> list[dict[str, object]]:
    return _ytgenerering_map().normalize_map_location_rows(value)


def ytgenerering_location_option_rows(location_path: str | Path) -> list[dict[str, object]]:
    flows_module = _flows()
    locations = flows_module._read_prepared_locations(Path(location_path))
    rows: list[dict[str, object]] = []
    for row in locations.to_dict("records"):
        location = str(row.get("Lagerplats") or "").strip().upper()
        if not location:
            continue
        try:
            max_pall = float(row.get("Max pall") or 0)
        except (TypeError, ValueError):
            max_pall = 0.0
        rows.append({"location": location, "maxPall": round(max_pall, 2)})
    return rows


def _load_modules() -> tuple[ModuleType, ModuleType]:
    global _ENGINE_MODULE, _FLOWS_MODULE, _LOAD_ERROR
    with _MODULE_LOCK:
        if _ENGINE_MODULE is not None and _FLOWS_MODULE is not None:
            return _ENGINE_MODULE, _FLOWS_MODULE

        try:
            _ensure_tools_importable()
        except AllocationBridgeUnavailable as exc:
            _LOAD_ERROR = str(exc)
            raise

        try:
            _ENGINE_MODULE = importlib.import_module("warehouse_tools.engine")
            _FLOWS_MODULE = importlib.import_module("warehouse_tools.flows")
            _LOAD_ERROR = None
        except Exception as exc:  # noqa: BLE001
            _ENGINE_MODULE = None
            _FLOWS_MODULE = None
            _LOAD_ERROR = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            raise AllocationBridgeUnavailable(_LOAD_ERROR) from exc

        return _ENGINE_MODULE, _FLOWS_MODULE


def _engine() -> ModuleType:
    return _load_modules()[0]


def _flows() -> ModuleType:
    return _load_modules()[1]


def unavailable_detail() -> dict:
    try:
        _load_modules()
    except AllocationBridgeUnavailable:
        pass
    return {
        "available": False,
        "message": _LOAD_ERROR or "Lagerverktygen är inte tillgängliga.",
        "backend_dir": str(warehouse_tools_dir()),
    }


def public_registry() -> list[dict]:
    return _catalog().public_registry()


def public_pool() -> list[dict]:
    return _catalog().public_pool()


def detect_file_type(path: str | Path) -> str | None:
    return _detect().detect_file_type(path)


def require_available() -> tuple[ModuleType, ModuleType]:
    try:
        return _load_modules()
    except AllocationBridgeUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=unavailable_detail()) from exc


def business_allocation_data_paths(business_code: str | None) -> dict[str, str]:
    require_available()
    seed_article_max_file(business_code)
    return {
        "observations_path": str(ensure_bufferpall_observations_file(business_code)),
        "article_max_path": str(article_max_path(business_code)),
    }


def business_article_max_path_for_flow(business_code: str | None) -> str:
    require_available()
    return str(ensure_article_max_file(business_code))



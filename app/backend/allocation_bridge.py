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
PROCESS_MATRIX_AREA_OPTIONS: tuple[dict[str, str], ...] = (
    {"code": "GG", "label": "GG"},
    {"code": "MG", "label": "MG"},
    {"code": "AS", "label": "AS"},
    {"code": "EH", "label": "EH"},
    {"code": "R3", "label": "R3"},
    {"code": "ALLT", "label": "Alla"},
)
PROCESS_AREA_RULES: dict[str, dict] = {
    "GG": {
        "visible_flow_ids": None,
    },
    "MG": {
        "visible_flow_ids": None,
    },
}
PROCESS_DEFAULT_AREA_RULE: dict[str, object] = {
    "visible_flow_ids": None,
}
YTGENERERING_DEFAULT_AREA_RULES: dict[str, dict[str, int]] = {
    "DEFAULT": {"utlMin": YTGENERERING_UTL_DEFAULT_MIN, "utlMax": YTGENERERING_UTL_DEFAULT_MAX},
    "MG": {"utlMin": 205, "utlMax": YTGENERERING_UTL_DEFAULT_MAX},
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


def normalize_process_area_focus(value: object) -> str:
    return str(value or "").strip().upper()


def _process_matrix_flow_ids(flows: list[dict] | None) -> set[str] | None:
    if flows is None:
        return None
    ids: set[str] = set()
    for flow in flows:
        flow_id = str(flow.get("id") or "").strip()
        if flow_id:
            ids.add(flow_id)
    return ids


def _process_rule_values(raw: dict | None, *keys: str):
    if not isinstance(raw, dict):
        return None
    for key in keys:
        if key in raw:
            return raw.get(key)
    return None


def _process_visible_flow_ids(value: object, allowed_flow_ids: set[str] | None = None) -> set[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        raw_values = re.split(r"[,;\s]+", value)
    elif isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        raw_values = [value]
    ids = {str(item or "").strip() for item in raw_values if str(item or "").strip()}
    if allowed_flow_ids is not None:
        ids &= allowed_flow_ids
    return ids


def _process_utl_number(value: object, fallback: int) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        number = fallback
    return max(YTGENERERING_UTL_DEFAULT_MIN, min(YTGENERERING_UTL_DEFAULT_MAX, number))


def _process_utl_range(raw: dict, defaults: dict | None = None) -> tuple[int, int]:
    defaults = defaults or YTGENERERING_DEFAULT_AREA_RULES["DEFAULT"]
    default_min = _process_utl_number(defaults.get("utlMin") or defaults.get("ytgenerering_utl_min"), YTGENERERING_UTL_DEFAULT_MIN)
    default_max = _process_utl_number(defaults.get("utlMax") or defaults.get("ytgenerering_utl_max"), YTGENERERING_UTL_DEFAULT_MAX)
    raw_min = _process_rule_values(
        raw,
        "ytgenerering_utl_min",
        "ytgenereringUtlMin",
        "ytgenereringUtlFrom",
        "utl_min",
        "utlMin",
        "utlFrom",
    )
    raw_max = _process_rule_values(
        raw,
        "ytgenerering_utl_max",
        "ytgenereringUtlMax",
        "ytgenereringUtlTo",
        "utl_max",
        "utlMax",
        "utlTo",
    )
    min_number = _process_utl_number(raw_min, default_min)
    max_number = _process_utl_number(raw_max, default_max)
    if min_number > max_number:
        min_number, max_number = max_number, min_number
    return min_number, max_number


def _normalize_process_area_rule(
    raw: dict | None,
    allowed_flow_ids: set[str] | None = None,
    defaults: dict | None = None,
) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    visible_flow_ids = _process_visible_flow_ids(
        _process_rule_values(raw, "visible_flow_ids", "visibleFlowIds", "flow_ids", "flowIds"),
        allowed_flow_ids=allowed_flow_ids,
    )
    return {
        "visible_flow_ids": visible_flow_ids,
    }


def default_process_matrix(flows: list[dict] | None = None) -> dict[str, dict]:
    allowed_flow_ids = _process_matrix_flow_ids(flows)
    matrix: dict[str, dict] = {
        "DEFAULT": _normalize_process_area_rule(PROCESS_DEFAULT_AREA_RULE, allowed_flow_ids=allowed_flow_ids)
    }
    for area in PROCESS_MATRIX_AREA_OPTIONS:
        code = normalize_process_area_focus(area.get("code"))
        matrix[code] = _normalize_process_area_rule(PROCESS_AREA_RULES.get(code), allowed_flow_ids=allowed_flow_ids)
    return matrix


def normalize_process_matrix(value: object = None, *, flows: list[dict] | None = None) -> dict[str, dict]:
    allowed_flow_ids = _process_matrix_flow_ids(flows)
    matrix = default_process_matrix(flows=flows)
    raw_matrix = value.get("matrix") if isinstance(value, dict) and isinstance(value.get("matrix"), dict) else value
    if not isinstance(raw_matrix, dict):
        return matrix

    known_area_codes = {normalize_process_area_focus(area.get("code")) for area in PROCESS_MATRIX_AREA_OPTIONS}
    known_area_codes.add("DEFAULT")
    for raw_code, raw_rule in raw_matrix.items():
        code = normalize_process_area_focus(raw_code)
        if not code or not re.fullmatch(r"[A-Z0-9_:-]{1,40}", code):
            continue
        if code not in known_area_codes and not isinstance(raw_rule, dict):
            continue
        matrix[code] = _normalize_process_area_rule(
            raw_rule,
            allowed_flow_ids=allowed_flow_ids,
            defaults=matrix.get(code) or matrix.get("DEFAULT"),
        )
    return matrix


def process_area_rule(area_focus: object, matrix: dict[str, dict] | None = None) -> dict | None:
    code = normalize_process_area_focus(area_focus)
    if not code:
        return None
    rules = normalize_process_matrix(matrix) if matrix is not None else default_process_matrix()
    return rules.get(code) or rules.get("DEFAULT")


def process_flow_visible(flow_id: str, area_focus: object, matrix: dict[str, dict] | None = None) -> bool:
    rule = process_area_rule(area_focus, matrix=matrix)
    visible_flow_ids = rule.get("visible_flow_ids") if rule else None
    return visible_flow_ids is None or flow_id in visible_flow_ids


def process_rule_has_filters(rule: dict | None) -> bool:
    return False


def process_matrix_storage_payload(matrix: dict[str, dict] | None = None) -> dict[str, dict]:
    rules = normalize_process_matrix(matrix)
    payload: dict[str, dict] = {}
    for code, rule in rules.items():
        if code == "DEFAULT":
            continue
        visible_flow_ids = rule.get("visible_flow_ids")
        payload[code] = {
            "visibleFlowIds": None if visible_flow_ids is None else sorted(str(value) for value in visible_flow_ids),
        }
    return payload


def process_matrix_public_payload(
    matrix: dict[str, dict] | None = None,
    *,
    flows: list[dict] | None = None,
    area_codes: set[str] | None = None,
) -> dict:
    rules = normalize_process_matrix(matrix, flows=flows)
    active_codes = None if area_codes is None else {normalize_process_area_focus(code) for code in area_codes}
    areas = [
        area
        for area in PROCESS_MATRIX_AREA_OPTIONS
        if active_codes is None
        or normalize_process_area_focus(area.get("code")) == "ALLT"
        or normalize_process_area_focus(area.get("code")) in active_codes
    ]
    known_codes = {normalize_process_area_focus(area.get("code")) for area in areas}
    for code in sorted(rules):
        if code != "DEFAULT" and code not in known_codes and (active_codes is None or code in active_codes):
            areas.append({"code": code, "label": code})
            known_codes.add(code)

    public_rules: dict[str, dict] = {}
    for code, rule in rules.items():
        visible_flow_ids = rule.get("visible_flow_ids")
        public_rules[code] = {
            "visibleFlowIds": None if visible_flow_ids is None else sorted(str(value) for value in visible_flow_ids),
        }
    return {
        "areas": areas,
        "flows": flows or [],
        "matrix": public_rules,
    }


def _process_column_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _process_filter_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "nat", "none"}:
        return ""
    return text


def _read_process_filter_table(path: Path):
    import pandas as pd  # type: ignore

    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"}:
        return pd.read_excel(path, dtype=str)

    try:
        df = pd.read_csv(path, dtype=str, sep=None, engine="python", encoding="utf-8-sig")
        if df.shape[1] == 1 and len(df):
            first = str(df.iloc[0, 0])
            if "\t" in first:
                df = pd.read_csv(path, dtype=str, sep="\t", engine="python", encoding="utf-8-sig")
    except Exception:
        df = pd.read_csv(path, dtype=str, sep="\t", engine="python", encoding="utf-8-sig")
    return df


def _write_process_filter_table(
    df,
    *,
    source_key: str,
    area_focus: str,
    target_path: Path | None = None,
) -> Path:
    if target_path is None:
        target = tempfile.NamedTemporaryFile(
            delete=False,
            prefix=f"flow_{area_focus.lower()}_{_safe_upload_stem(source_key)}_",
            suffix=".csv",
        )
        path = Path(target.name)
        target.close()
    else:
        path = target_path
        path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(delete=False, dir=path.parent, prefix="pending_filter_", suffix=".csv")
    try:
        tmp.close()
        df.to_csv(tmp.name, index=False, encoding="utf-8-sig", sep="\t")
        Path(tmp.name).replace(path)
    except Exception:
        Path(tmp.name).unlink(missing_ok=True)
        raise
    return path


def apply_process_area_filters(
    files: dict[str, Path],
    area_focus: object,
    matrix: dict[str, dict] | None = None,
) -> tuple[dict[str, Path], list[Path], list[str]]:
    # Bearbeta-matrisen styr numera bara flodessynlighet. Fil-/radfilter och
    # Ytgenereringens egna installningar ar anvandarspecifika.
    return files, [], []


def _normalize_user_filter_operator(value: object) -> str:
    key = str(value or "").strip()
    return USER_FILTER_OPERATORS.get(key) or USER_FILTER_OPERATORS.get(key.lower()) or "EQ"


def _split_user_filter_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        raw_values = re.split(r"[\n,;]+", str(value))
    result: list[str] = []
    for item in raw_values:
        text = _process_filter_text(item)
        if text:
            result.append(text)
    return result


def _normalize_user_filter_condition(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    column = str(raw.get("column") or raw.get("id") or raw.get("field") or "").strip()
    column_label = str(raw.get("columnLabel") or raw.get("label") or "").strip()
    if not column and not column_label:
        return None
    operator = _normalize_user_filter_operator(raw.get("operator"))
    value = raw.get("value")
    if operator in {"In", "NotIn"}:
        normalized_value = _split_user_filter_values(value)
        if not normalized_value:
            return None
    elif operator == "Between":
        normalized_value = _split_user_filter_values(value)
        if len(normalized_value) < 2:
            return None
        normalized_value = normalized_value[:2]
    else:
        normalized_value = _process_filter_text(value)
        if not normalized_value:
            return None
    return {
        "column": column[:160],
        "columnLabel": column_label[:160],
        "operator": operator,
        "value": normalized_value,
    }


def _normalize_user_source_mode(value: object) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"api", "external", "hamta", "hämta"}:
        return "api"
    if text in {"upload", "uploaded", "file", "local", "uppladdning", "fil"}:
        return "upload"
    return None


def _normalize_user_source_modes(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    modes: dict[str, str] = {}
    for raw_file_key, raw_mode in value.items():
        file_key = str(raw_file_key or "").strip()
        if not file_key or not re.fullmatch(r"[A-Za-z0-9_:-]{1,80}", file_key):
            continue
        mode = _normalize_user_source_mode(raw_mode)
        if mode:
            modes[file_key] = mode
    return modes


def _ytgenerering_default_area_rule(code: object) -> dict[str, int]:
    area_code = normalize_process_area_focus(code) or "DEFAULT"
    defaults = YTGENERERING_DEFAULT_AREA_RULES.get(area_code) or YTGENERERING_DEFAULT_AREA_RULES["DEFAULT"]
    return {
        "utlMin": _process_utl_number(defaults.get("utlMin"), YTGENERERING_UTL_DEFAULT_MIN),
        "utlMax": _process_utl_number(defaults.get("utlMax"), YTGENERERING_UTL_DEFAULT_MAX),
    }


def default_ytgenerering_area_settings() -> dict[str, dict[str, int]]:
    areas = {"DEFAULT": _ytgenerering_default_area_rule("DEFAULT")}
    for area in PROCESS_MATRIX_AREA_OPTIONS:
        code = normalize_process_area_focus(area.get("code"))
        if code:
            areas[code] = _ytgenerering_default_area_rule(code)
    return areas


def _normalize_ytgenerering_area_settings(value: object) -> dict[str, dict[str, int]]:
    areas = default_ytgenerering_area_settings()
    raw_areas = value.get("areas") if isinstance(value, dict) and isinstance(value.get("areas"), dict) else value
    if not isinstance(raw_areas, dict):
        return areas

    known_area_codes = set(areas)
    for raw_code, raw_rule in raw_areas.items():
        code = normalize_process_area_focus(raw_code)
        if not code or not re.fullmatch(r"[A-Z0-9_:-]{1,40}", code):
            continue
        if code not in known_area_codes:
            continue
        base = areas.get(code) or areas["DEFAULT"]
        if isinstance(raw_rule, dict):
            utl_min, utl_max = _process_utl_range(raw_rule, base)
        else:
            utl_min, utl_max = base["utlMin"], base["utlMax"]
        areas[code] = {"utlMin": utl_min, "utlMax": utl_max}
    return areas


def _carrier_cluster_text(value: object, *, max_length: int = 160) -> str:
    text = _process_filter_text(value)
    return text[:max_length]


def _carrier_cluster_sequence(value: object) -> str:
    text = _carrier_cluster_text(value, max_length=20).replace(",", ".")
    if not text:
        return ""
    try:
        number = int(float(text))
    except (TypeError, ValueError):
        return ""
    return str(max(YTGENERERING_UTL_DEFAULT_MIN, min(YTGENERERING_UTL_DEFAULT_MAX, number)))


def _carrier_cluster_order(value: object, fallback: int) -> str:
    text = _carrier_cluster_text(value, max_length=20).replace(",", ".")
    if not text:
        return str(fallback)
    try:
        number = int(float(text))
    except (TypeError, ValueError):
        number = fallback
    return str(max(0, min(10000, number)))


def _normalize_user_carrier_cluster_row(raw: object, index: int) -> dict | None:
    if not isinstance(raw, dict):
        return None
    carrier_num = _carrier_cluster_text(
        raw.get("carrierNum")
        or raw.get("carrier_num")
        or raw.get("agencyNum")
        or raw.get("agency_num")
        or raw.get("AGENCY_NUM"),
        max_length=80,
    )
    if carrier_num.endswith(".0"):
        carrier_num = carrier_num[:-2]
    description = _carrier_cluster_text(
        raw.get("description")
        or raw.get("agencyDesc")
        or raw.get("agency_desc")
        or raw.get("AGENCY_DESC")
        or raw.get("carrier")
        or raw.get("transportor")
    )
    alias = _carrier_cluster_text(raw.get("alias") or raw.get("agencyAlias") or raw.get("agency_alias") or raw.get("AGENCY_ALIAS"))
    if not (carrier_num or description or alias):
        return None
    row = {
        "id": _carrier_cluster_text(raw.get("id"), max_length=100) or carrier_num or f"row-{index + 1}",
        "carrierNum": carrier_num,
        "description": description,
        "alias": alias,
        "clusterGroup": _carrier_cluster_text(raw.get("clusterGroup") or raw.get("cluster_group") or raw.get("CLUSTER_GROUP") or raw.get("cluster")),
        "assignmentOrder": _carrier_cluster_order(raw.get("assignmentOrder") or raw.get("assignment_order") or raw.get("ASSIGNMENT_ORDER"), index + 1),
        "startSeq": _carrier_cluster_sequence(raw.get("startSeq") or raw.get("start_seq") or raw.get("START_SEQ") or raw.get("from") or raw.get("utlFrom")),
        "endSeq": _carrier_cluster_sequence(raw.get("endSeq") or raw.get("end_seq") or raw.get("END_SEQ") or raw.get("to") or raw.get("utlTo")),
        "asn": _carrier_cluster_text(raw.get("asn") or raw.get("agency_asn") or raw.get("agencyAsn") or raw.get("ASN"), max_length=40),
        "arrive": _carrier_cluster_text(raw.get("arrive") or raw.get("agency_arrive") or raw.get("agencyArrive") or raw.get("ARRIVE"), max_length=40),
        "depart": _carrier_cluster_text(raw.get("depart") or raw.get("agency_depart") or raw.get("agencyDepart") or raw.get("DEPART"), max_length=40),
        "color": _carrier_cluster_text(raw.get("color") or raw.get("colour"), max_length=24),
    }
    return row


def _normalize_user_carrier_clusters(value: object) -> dict | None:
    if value is None:
        return None
    rows = value if isinstance(value, list) else value.get("rows") if isinstance(value, dict) else None
    if not isinstance(rows, list):
        return None
    normalized_rows = [
        row
        for row in (_normalize_user_carrier_cluster_row(item, index) for index, item in enumerate(rows[:200]))
        if row is not None
    ]
    if not normalized_rows:
        return None
    source = value.get("source") if isinstance(value, dict) and isinstance(value.get("source"), dict) else {}
    return {
        "version": 1,
        "source": {
            "name": _carrier_cluster_text(source.get("name"), max_length=120) or "Transportorer",
            "rowCount": len(normalized_rows),
        },
        "rows": normalized_rows,
    }


def _normalize_user_ytgenerering_settings(value: object) -> dict | None:
    raw = value if isinstance(value, dict) else {}
    if not raw:
        return None
    areas = _normalize_ytgenerering_area_settings(raw.get("areas") if isinstance(raw.get("areas"), dict) else raw)
    carrier_clusters = _normalize_user_carrier_clusters(raw.get("carrierClusters") or raw.get("carrier_clusters"))
    settings: dict[str, object] = {"areas": areas}
    if carrier_clusters:
        settings["carrierClusters"] = carrier_clusters
    return settings


def normalize_user_filter_profile(value: object, *, flows: list[dict] | None = None) -> dict:
    allowed_flow_ids = _process_matrix_flow_ids(flows)
    raw_profile = value if isinstance(value, dict) else {}
    raw_flows = raw_profile.get("flows")
    if not isinstance(raw_flows, dict):
        raw_flows = {}
    profile_flows: dict[str, dict] = {}
    for raw_flow_id, raw_flow in raw_flows.items():
        flow_id = str(raw_flow_id or "").strip()
        if not flow_id or not re.fullmatch(r"[A-Za-z0-9_:-]{1,80}", flow_id):
            continue
        if allowed_flow_ids is not None and flow_id not in allowed_flow_ids:
            continue
        if not isinstance(raw_flow, dict):
            continue
        raw_files = raw_flow.get("files") if isinstance(raw_flow, dict) else None
        files_payload: dict[str, list[dict]] = {}
        if isinstance(raw_files, dict):
            for raw_file_key, raw_conditions in raw_files.items():
                file_key = str(raw_file_key or "").strip()
                if not file_key or not re.fullmatch(r"[A-Za-z0-9_:-]{1,80}", file_key):
                    continue
                conditions = [
                    condition
                    for condition in (_normalize_user_filter_condition(item) for item in (raw_conditions or []))
                    if condition is not None
                ]
                if conditions:
                    files_payload[file_key] = conditions[:20]
        flow_payload: dict[str, object] = {}
        source_modes = _normalize_user_source_modes(raw_flow.get("sources") or raw_flow.get("sourceModes"))
        if source_modes:
            flow_payload["sources"] = source_modes
        if files_payload:
            flow_payload["files"] = files_payload
        raw_settings = raw_flow.get("settings") if isinstance(raw_flow.get("settings"), dict) else {}
        raw_ytgenerering_settings = raw_settings.get("ytgenerering") if isinstance(raw_settings, dict) else None
        if raw_ytgenerering_settings is None:
            raw_ytgenerering_settings = raw_flow.get("ytgenerering")
        if flow_id == "ytgenerering":
            ytgenerering_settings = _normalize_user_ytgenerering_settings(raw_ytgenerering_settings)
            if ytgenerering_settings:
                flow_payload["settings"] = {"ytgenerering": ytgenerering_settings}
        if flow_payload:
            profile_flows[flow_id] = flow_payload
    return {"version": USER_FILTER_PROFILE_VERSION, "flows": profile_flows}


def user_filter_profile_count(profile: object) -> int:
    normalized = normalize_user_filter_profile(profile)
    file_count = sum(
        len(conditions)
        for flow in normalized.get("flows", {}).values()
        for conditions in flow.get("files", {}).values()
    )
    source_count = sum(
        len(flow.get("sources", {}))
        for flow in normalized.get("flows", {}).values()
        if isinstance(flow, dict)
    )
    settings_count = 0
    for flow in normalized.get("flows", {}).values():
        ytgenerering = ((flow.get("settings") or {}).get("ytgenerering") or {}) if isinstance(flow, dict) else {}
        if not isinstance(ytgenerering, dict):
            continue
        if ytgenerering.get("areas"):
            settings_count += 1
        carrier_clusters = ytgenerering.get("carrierClusters") if isinstance(ytgenerering.get("carrierClusters"), dict) else None
        settings_count += len(carrier_clusters.get("rows") or []) if carrier_clusters else 0
    return file_count + source_count + settings_count


def user_source_modes(profile: object, flow_id: str) -> dict[str, str]:
    normalized = normalize_user_filter_profile(profile)
    flow = normalized.get("flows", {}).get(str(flow_id or ""), {})
    sources = flow.get("sources") if isinstance(flow, dict) else None
    return dict(sources) if isinstance(sources, dict) else {}


def api_source_map_for_user_profile(source_map: dict[str, str], flow_id: str, profile: object) -> dict[str, str]:
    modes = user_source_modes(profile, flow_id)
    if not modes:
        return dict(source_map)
    return {
        file_key: source_key
        for file_key, source_key in source_map.items()
        if modes.get(str(file_key)) != "upload"
    }


def ytgenerering_user_settings(profile: object, *, area_focus: object = None) -> dict[str, object]:
    normalized = normalize_user_filter_profile(profile)
    settings = (
        normalized.get("flows", {})
        .get("ytgenerering", {})
        .get("settings", {})
        .get("ytgenerering")
    )
    settings = settings if isinstance(settings, dict) else {}
    areas = _normalize_ytgenerering_area_settings(settings.get("areas") if isinstance(settings.get("areas"), dict) else {})
    focus_code = normalize_process_area_focus(area_focus) or "ALLT"
    rule = areas.get(focus_code) or areas.get("DEFAULT") or _ytgenerering_default_area_rule("DEFAULT")
    carrier_clusters = settings.get("carrierClusters") if isinstance(settings.get("carrierClusters"), dict) else None
    rows = carrier_clusters.get("rows") if isinstance(carrier_clusters, dict) else None
    return {
        "areas": areas,
        "utlRange": (int(rule["utlMin"]), int(rule["utlMax"])),
        "carrierClusters": carrier_clusters if rows else None,
    }


def apply_ytgenerering_user_settings(
    params: dict[str, str],
    profile: object,
    *,
    area_focus: object = None,
) -> dict[str, object]:
    settings = ytgenerering_user_settings(profile, area_focus=area_focus)
    utl_min, utl_max = settings["utlRange"]
    params[YTGENERERING_UTL_MIN_PARAM] = str(utl_min)
    params[YTGENERERING_UTL_MAX_PARAM] = str(utl_max)
    carrier_clusters = settings.get("carrierClusters")
    if isinstance(carrier_clusters, dict) and carrier_clusters.get("rows"):
        params["__carrier_clusters_json"] = json.dumps(carrier_clusters, ensure_ascii=False)
    return settings


def _user_filter_column(df, condition: dict) -> str | None:
    candidates = {
        _process_column_key(value)
        for value in (condition.get("column"), condition.get("columnLabel"))
        if _process_column_key(value)
    }
    if not candidates:
        return None
    for column in df.columns:
        if _process_column_key(column) in candidates:
            return column
    return None


def _user_filter_text_series(series):
    return series.map(_process_filter_text)


def _user_filter_casefold(value: object) -> str:
    return _process_filter_text(value).casefold()


def _user_filter_number(value: object) -> float | None:
    text = _process_filter_text(value).replace(",", ".")
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _user_filter_numeric_mask(series, operator: str, values: list[str] | str):
    import pandas as pd  # type: ignore

    if isinstance(values, str):
        compare_values = [values]
    else:
        compare_values = list(values)
    numbers = [_user_filter_number(value) for value in compare_values]
    if any(number is None for number in numbers):
        return None
    numeric_series = pd.to_numeric(
        _user_filter_text_series(series).map(lambda value: str(value).replace(",", ".")),
        errors="coerce",
    )
    first = numbers[0]
    if first is None:
        return None
    if operator == "GT":
        return numeric_series > first
    if operator == "GTE":
        return numeric_series >= first
    if operator == "LT":
        return numeric_series < first
    if operator == "LTE":
        return numeric_series <= first
    if operator == "Between" and len(numbers) >= 2 and numbers[1] is not None:
        low, high = sorted((first, numbers[1]))
        return numeric_series.between(low, high, inclusive="both")
    return None


def _user_filter_condition_mask(series, condition: dict):
    operator = str(condition.get("operator") or "EQ")
    value = condition.get("value")
    text_series = _user_filter_text_series(series).map(lambda item: str(item).casefold())
    if operator == "EQ":
        return text_series.eq(_user_filter_casefold(value))
    if operator == "NE":
        return ~text_series.eq(_user_filter_casefold(value))
    if operator in {"GT", "GTE", "LT", "LTE"}:
        numeric = _user_filter_numeric_mask(series, operator, _process_filter_text(value))
        if numeric is not None:
            return numeric.fillna(False)
        compare = _user_filter_casefold(value)
        if operator == "GT":
            return text_series.gt(compare)
        if operator == "GTE":
            return text_series.ge(compare)
        if operator == "LT":
            return text_series.lt(compare)
        return text_series.le(compare)
    if operator == "Between":
        values = value if isinstance(value, list) else _split_user_filter_values(value)
        numeric = _user_filter_numeric_mask(series, operator, values[:2])
        if numeric is not None:
            return numeric.fillna(False)
        if len(values) < 2:
            return text_series.eq("")
        low, high = sorted((_user_filter_casefold(values[0]), _user_filter_casefold(values[1])))
        return text_series.between(low, high, inclusive="both")
    if operator in {"In", "NotIn"}:
        values = {_user_filter_casefold(item) for item in _split_user_filter_values(value)}
        mask = text_series.isin(values)
        return ~mask if operator == "NotIn" else mask
    return text_series.eq(_user_filter_casefold(value))


def apply_user_flow_filters(
    files: dict[str, Path],
    flow_id: str,
    profile: object,
) -> tuple[dict[str, Path], list[Path], list[str]]:
    normalized = normalize_user_filter_profile(profile)
    flow_filters = (normalized.get("flows") or {}).get(str(flow_id or ""), {}).get("files") or {}
    if not flow_filters:
        return files, [], []

    filtered_files = dict(files)
    temp_paths: list[Path] = []
    log_lines: list[str] = []
    for file_key, conditions in flow_filters.items():
        if file_key not in files or not conditions:
            continue
        path = Path(files[file_key])
        try:
            df = _read_process_filter_table(path)
        except Exception as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Filtret for {file_key} kunde inte lasa tabellen.",
            ) from exc
        mask = None
        missing_columns: list[str] = []
        for condition in conditions:
            column = _user_filter_column(df, condition)
            if column is None:
                missing_columns.append(str(condition.get("columnLabel") or condition.get("column") or "kolumn"))
                continue
            condition_mask = _user_filter_condition_mask(df[column], condition)
            mask = condition_mask if mask is None else (mask & condition_mask)
        if missing_columns:
            missing = ", ".join(sorted(set(missing_columns))[:5])
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Filtret for {file_key} saknar kolumn: {missing}.",
            )
        if mask is None:
            continue
        before = int(len(df))
        filtered_df = df.loc[mask].copy()
        filtered_path = _write_process_filter_table(filtered_df, source_key=file_key, area_focus="userfilter")
        filtered_files[file_key] = filtered_path
        temp_paths.append(filtered_path)
        log_lines.append(f"Anvandarfilter {file_key}: {before} -> {int(len(filtered_df))} rader ({len(conditions)} villkor).")
    return filtered_files, temp_paths, log_lines


def _cell(value: object) -> str:
    try:
        import pandas as pd  # type: ignore
    except Exception:  # noqa: BLE001
        pd = None

    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        return str(int(value)) if value.is_integer() else f"{value:g}"
    if pd is not None and isinstance(value, pd.Timestamp):
        return "" if pd.isna(value) else value.isoformat(sep=" ")
    text = str(value)
    return "" if text.lower() in ("nan", "nat", "none") else text


def _is_simple_table(value: object) -> bool:
    try:
        return bool(_native_tables().is_simple_table(value))
    except Exception:
        return False


def df_to_table(df, preview_limit: int = 1000) -> dict:
    if _is_simple_table(df):
        columns = [str(column) for column in df.columns]
        rows = [[_cell(value) for value in row] for row in df.preview_rows(preview_limit)]
        return {
            "columns": columns,
            "rows": rows,
            "row_count": int(len(df)),
            "truncated": len(df) > preview_limit,
        }

    try:
        import pandas as pd  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise AllocationBridgeUnavailable("Pandas saknas för lagerverktygsresultat.") from exc

    if not isinstance(df, pd.DataFrame) or df.empty:
        cols = [str(c) for c in df.columns] if isinstance(df, pd.DataFrame) else []
        return {"columns": cols, "rows": [], "row_count": 0, "truncated": False}
    columns = [str(c) for c in df.columns]
    preview = df.head(preview_limit)
    rows = [[_cell(v) for v in rec] for rec in preview.itertuples(index=False, name=None)]
    return {
        "columns": columns,
        "rows": rows,
        "row_count": int(len(df)),
        "truncated": len(df) > preview_limit,
    }


def _safe_session_key(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "table")).strip("._-")
    return (safe or "table")[:80]


def _session_file_path(session_id: str, key: str, suffix: str) -> Path:
    return _active_session_cache_dir() / f"{session_id}_{_safe_session_key(key)}{suffix}"


def _table_to_dataframe(table):
    try:
        import pandas as pd  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise AllocationBridgeUnavailable("Pandas saknas for lagerverktygsresultat.") from exc

    if isinstance(table, pd.DataFrame):
        return table
    if _is_simple_table(table):
        return pd.DataFrame(list(table.rows), columns=[str(column) for column in table.columns])
    return pd.DataFrame(table)


def _write_session_table(session_id: str, key: str, table) -> dict:
    cache_dir = _active_session_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _session_file_path(session_id, key, ".pkl")
    df = _table_to_dataframe(table)
    df.to_pickle(path)
    return {
        "__allocation_table_file__": True,
        "format": "pickle",
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "columns": [str(column) for column in df.columns],
        "row_count": int(len(df)),
    }


def _read_session_table(value):
    if isinstance(value, dict) and value.get("__allocation_table_file__"):
        path = Path(str(value.get("path") or ""))
        if not path.is_file():
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resultatet hittades inte (kör flödet igen).")
        try:
            import pandas as pd  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise AllocationBridgeUnavailable("Pandas saknas for lagerverktygsresultat.") from exc
        return pd.read_pickle(path)
    return value


def session_table(session: dict | None, key: str):
    if not session:
        return None
    tables = session.get("tables") or {}
    if key not in tables:
        return None
    return _read_session_table(tables[key])


def _json_payload_size(value: object) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))
    except (TypeError, ValueError):
        return 0


def _write_session_json(session_id: str, key: str, payload: object) -> dict:
    cache_dir = _active_session_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _session_file_path(session_id, key, ".json")
    tmp = tempfile.NamedTemporaryFile(delete=False, dir=cache_dir, prefix="pending_", suffix=".json", mode="w", encoding="utf-8")
    try:
        json.dump(payload, tmp, ensure_ascii=False, default=str)
        tmp.close()
        Path(tmp.name).replace(path)
    except Exception:
        Path(tmp.name).unlink(missing_ok=True)
        raise
    return {
        "__allocation_json_file__": True,
        "path": str(path),
        "size_bytes": path.stat().st_size,
    }


def _read_session_json(value: object) -> object:
    if isinstance(value, dict) and value.get("__allocation_json_file__"):
        path = Path(str(value.get("path") or ""))
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    return value


def _store_session_artifacts(session_id: str, artifacts: dict) -> dict:
    stored: dict[str, object] = {}
    for key, value in (artifacts or {}).items():
        if _json_payload_size(value) > SESSION_ARTIFACT_INLINE_MAX_BYTES:
            stored[key] = _write_session_json(session_id, f"artifact_{key}", value)
        else:
            stored[key] = value
    return stored


def session_artifacts(session: dict | None) -> dict:
    artifacts = (session or {}).get("artifacts") or {}
    return {key: _read_session_json(value) for key, value in artifacts.items()}


def _store_session_download_files(session_id: str, download_files: dict) -> dict:
    _active_session_cache_dir().mkdir(parents=True, exist_ok=True)
    stored: dict[str, dict] = {}
    for key, payload in (download_files or {}).items():
        item = dict(payload or {})
        content = item.pop("content", "")
        filename = str(item.get("filename") or f"{key}.csv")
        suffix = Path(filename).suffix or ".csv"
        path = _session_file_path(session_id, f"download_{key}", suffix)
        encoding = str(item.get("encoding") or "utf-8-sig")
        with open(path, "wb") as handle:
            if isinstance(content, bytes):
                handle.write(content)
            else:
                handle.write(str(content).encode(encoding))
        item["path"] = str(path)
        item["size_bytes"] = path.stat().st_size
        stored[key] = item
    return stored


def _session_file_paths(session: dict | None) -> list[Path]:
    paths: list[Path] = []
    for value in ((session or {}).get("tables") or {}).values():
        if isinstance(value, dict) and value.get("path"):
            paths.append(Path(str(value["path"])))
    for value in ((session or {}).get("artifacts") or {}).values():
        if isinstance(value, dict) and value.get("path"):
            paths.append(Path(str(value["path"])))
    for value in ((session or {}).get("download_files") or {}).values():
        if isinstance(value, dict) and value.get("path"):
            paths.append(Path(str(value["path"])))
    return paths


def _remove_session(session: dict | None) -> None:
    for path in _session_file_paths(session):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            continue


def _session_size_bytes(session: dict | None) -> int:
    total = 0
    for path in _session_file_paths(session):
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total


def _safe_upload_stem(filename: str | None) -> str:
    stem = Path(filename or "upload").stem or "upload"
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._-")
    return (safe or "upload")[:80]


def _upload_cache_index_dir() -> Path:
    return _active_upload_cache_dir() / ".index"


def _upload_cache_reference_path(cache_key: str) -> Path:
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    return _upload_cache_index_dir() / f"{digest}.txt"


def _upload_cache_referenced_names() -> set[str]:
    index_dir = _upload_cache_index_dir()
    if not index_dir.exists():
        return set()
    names: set[str] = set()
    for path in index_dir.iterdir():
        try:
            if path.is_file():
                value = path.read_text(encoding="utf-8").strip()
                if value:
                    names.add(value)
        except OSError:
            continue
    return names


def _remember_upload_cache(cache_key: str | None, target: Path) -> None:
    if not cache_key:
        return
    index_dir = _upload_cache_index_dir()
    index_dir.mkdir(parents=True, exist_ok=True)
    index_path = _upload_cache_reference_path(cache_key)
    previous = ""
    try:
        previous = index_path.read_text(encoding="utf-8").strip() if index_path.exists() else ""
    except OSError:
        previous = ""
    if previous == target.name:
        return

    tmp = tempfile.NamedTemporaryFile(
        delete=False,
        dir=index_dir,
        prefix="pending_",
        suffix=".txt",
        mode="w",
        encoding="utf-8",
    )
    try:
        tmp.write(target.name)
        tmp.close()
        Path(tmp.name).replace(index_path)
    except Exception:
        Path(tmp.name).unlink(missing_ok=True)
        raise

    if previous and previous not in _upload_cache_referenced_names():
        try:
            (_active_upload_cache_dir() / previous).unlink(missing_ok=True)
        except OSError:
            pass


def _cleanup_upload_cache(now: float | None = None) -> None:
    cache_dir = _active_upload_cache_dir()
    try:
        if not cache_dir.exists():
            return
        now_ts = time.time() if now is None else now
        retained: list[tuple[float, int, Path]] = []
        for path in cache_dir.iterdir():
            try:
                if not path.is_file():
                    continue
                stat = path.stat()
                if now_ts - stat.st_mtime > UPLOAD_CACHE_TTL_SECONDS:
                    path.unlink(missing_ok=True)
                    continue
                retained.append((stat.st_mtime, stat.st_size, path))
            except OSError:
                continue

        overflow = len(retained) - UPLOAD_CACHE_MAX_FILES
        if overflow > 0:
            for _mtime, _size, path in sorted(retained)[:overflow]:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    continue
            retained = sorted(retained)[overflow:]

        total_bytes = sum(size for _mtime, size, _path in retained)
        if total_bytes > UPLOAD_CACHE_MAX_BYTES:
            for _mtime, size, path in sorted(retained):
                try:
                    path.unlink(missing_ok=True)
                    total_bytes -= size
                except OSError:
                    continue
                if total_bytes <= UPLOAD_CACHE_MAX_BYTES:
                    break
        index_dir = _upload_cache_index_dir()
        if index_dir.exists():
            existing = {path.name for path in cache_dir.iterdir() if path.is_file()}
            for path in index_dir.iterdir():
                try:
                    if path.is_file() and path.read_text(encoding="utf-8").strip() not in existing:
                        path.unlink(missing_ok=True)
                except OSError:
                    continue
    except OSError:
        return


async def _write_upload_to_temp(
    upload: UploadFile,
    *,
    directory: Path | None = None,
    prefix: str,
    suffix: str,
) -> tuple[Path, str]:
    digest = hashlib.sha256()
    tmp = tempfile.NamedTemporaryFile(delete=False, dir=directory, prefix=prefix, suffix=suffix)
    path = Path(tmp.name)
    try:
        while True:
            chunk = await upload.read(UPLOAD_READ_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            tmp.write(chunk)
        tmp.close()
        return path, digest.hexdigest()
    except Exception:
        tmp.close()
        path.unlink(missing_ok=True)
        raise


async def save_upload(upload: UploadFile, *, cache: bool = False, cache_key: str | None = None) -> Path:
    suffix = Path(upload.filename or "").suffix or ".csv"
    if cache:
        cache_dir = _active_upload_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        _cleanup_upload_cache()
        temp_path, digest = await _write_upload_to_temp(
            upload,
            directory=cache_dir,
            prefix="pending_",
            suffix=suffix,
        )
        target = cache_dir / f"{digest}{suffix}"
        if target.exists():
            temp_path.unlink(missing_ok=True)
        else:
            temp_path.replace(target)
        _remember_upload_cache(cache_key, target)
        _cleanup_upload_cache()
        return target

    prefix = f"bem_allok_upload_{_safe_upload_stem(upload.filename)}_"
    path, _digest = await _write_upload_to_temp(upload, prefix=prefix, suffix=suffix)
    return path


def _cleanup_sessions(now: float | None = None) -> None:
    cache_dir = _active_session_cache_dir()
    now_ts = time.time() if now is None else now
    for session_id, session in list(SESSIONS.items()):
        try:
            created_at = float(session.get("created_at") or now_ts)
        except (TypeError, ValueError):
            created_at = now_ts
        if now_ts - created_at > SESSION_TTL_SECONDS:
            removed = SESSIONS.pop(session_id, None)
            _remove_session(removed)

    overflow = len(SESSIONS) - SESSION_MAX_COUNT
    ordered = sorted(
        SESSIONS.items(),
        key=lambda item: float(item[1].get("created_at") or now_ts),
    )
    if overflow > 0:
        for session_id, _session in ordered[:overflow]:
            removed = SESSIONS.pop(session_id, None)
            _remove_session(removed)
        ordered = ordered[overflow:]

    total_bytes = sum(_session_size_bytes(session) for _session_id, session in ordered)
    if total_bytes > SESSION_MAX_BYTES:
        for session_id, session in ordered:
            if len(SESSIONS) <= 1:
                break
            removed = SESSIONS.pop(session_id, None)
            total_bytes -= _session_size_bytes(session)
            _remove_session(removed)
            if total_bytes <= SESSION_MAX_BYTES:
                break

    try:
        if cache_dir.exists():
            active_paths = {path.resolve() for session in SESSIONS.values() for path in _session_file_paths(session)}
            for path in cache_dir.iterdir():
                try:
                    if not path.is_file():
                        continue
                    stat = path.stat()
                    if path.resolve() not in active_paths and now_ts - stat.st_mtime > SESSION_TTL_SECONDS:
                        path.unlink(missing_ok=True)
                except OSError:
                    continue
    except OSError:
        return


def open_path(path: str) -> None:
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Kunde inte öppna filen automatiskt: {exc}") from exc


def excel_writer_engine() -> str:
    if importlib.util.find_spec("openpyxl"):
        return "openpyxl"
    if importlib.util.find_spec("xlsxwriter"):
        return "xlsxwriter"
    raise RuntimeError("Saknar Excel-skrivare (installera openpyxl eller xlsxwriter).")


def _safe_excel_sheet_name(label: str) -> str:
    cleaned = re.sub(r"[\[\]:*?/\\]+", " ", str(label or "Sheet1"))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:31] or "Sheet1"


def _safe_excel_file_label(label: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(label or "excel"))
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._")
    return (cleaned or "excel")[:80]


def write_table_to_excel(table, label: str, *, include_header: bool = True) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{_safe_excel_file_label(label)}.xlsx")
    path = tmp.name
    tmp.close()
    sheet_name = _safe_excel_sheet_name(label)

    if _is_simple_table(table):
        try:
            from openpyxl import Workbook
        except Exception as exc:  # noqa: BLE001
            raise AllocationBridgeUnavailable("Openpyxl saknas for Excel-export.") from exc

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = sheet_name
        if include_header:
            sheet.append([_cell(column) for column in table.columns])
        for row in table.rows:
            sheet.append([_cell(value) for value in row])
        workbook.save(path)
        return path

    import pandas as pd  # type: ignore

    df = table if isinstance(table, pd.DataFrame) else pd.DataFrame(table)
    with pd.ExcelWriter(path, engine=excel_writer_engine()) as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False, header=include_header)
    return path


def open_df_in_excel_without_header(df, label: str) -> str:
    path = write_table_to_excel(df, label, include_header=False)
    open_path(path)
    return path


def open_simple_table_in_excel_without_header(table, label: str) -> str:
    path = write_table_to_excel(table, label, include_header=False)
    open_path(path)
    return path


async def form_to_flow_payload(form, *, cache_scope: str | None = None) -> tuple[dict[str, Path], dict[str, str], list[Path]]:
    files: dict[str, Path] = {}
    params: dict[str, str] = {}
    temp_paths: list[Path] = []
    for key, value in form.multi_items():
        if isinstance(value, StarletteUploadFile):
            if value.filename:
                upload_cache_key = f"{cache_scope or 'global'}:{key}:{value.filename}"
                path = await save_upload(value, cache=True, cache_key=upload_cache_key)
                files[key] = path
        elif isinstance(value, str) and value.strip() != "":
            params[key] = value
    return files, params, temp_paths


def _friendly_flow_error_message(exc: Exception) -> str:
    raw = str(exc).strip()
    if raw == "No objects to concatenate":
        return (
            "Flödet fick inga rader att sammanställa. Kontrollera att rätt filer är inlagda "
            "och att vald toggle/filter inte filtrerar bort allt."
        )
    return raw or "Flödet kunde inte köras."


def run_flow_handler(
    flow_id: str,
    files: dict,
    params: dict,
    *,
    default_max_csv_path: str | Path | None = None,
) -> dict:
    flow = _native_flows().FLOW_BY_ID.get(flow_id)
    if flow is None:
        if flow_id not in _catalog().FLOW_BY_ID:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Okänt flöde: {flow_id}")
        _engine_module, flows_module = require_available()
        flow = flows_module.FLOW_BY_ID.get(flow_id)
    if flow is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Okänt flöde: {flow_id}")
    handler_params = dict(params or {})
    if default_max_csv_path and "max_csv" not in files:
        handler_params[DEFAULT_MAX_CSV_PARAM] = str(default_max_csv_path)
    try:
        result = flow["handler"](files, handler_params)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Allocation flow failed flow_id=%s", flow_id)
        message = _friendly_flow_error_message(exc)
        raw_message = str(exc).strip()
        detail = {
            "message": message,
            "error_code": "allocation_flow_failed",
            "error_type": type(exc).__name__,
        }
        if raw_message and raw_message != message:
            detail["technical_message"] = raw_message
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=detail,
        ) from exc

    tables = result.get("tables", [])
    artifacts = result.get("artifacts", {}) or {}
    download_files = result.get("download_files", {}) or {}
    _cleanup_sessions()
    session_id = uuid.uuid4().hex
    table_files = {key: _write_session_table(session_id, key, df) for key, _label, df in tables}
    SESSIONS[session_id] = {
        "flow_id": flow_id,
        "created_at": time.time(),
        "tables": table_files,
        "labels": {key: label for key, label, _df in tables},
        "artifacts": _store_session_artifacts(session_id, artifacts),
        "download_files": _store_session_download_files(session_id, download_files),
        "size_bytes": sum(int(ref.get("size_bytes") or 0) for ref in table_files.values()),
    }
    _cleanup_sessions()
    return {
        "flow_id": flow_id,
        "session_id": session_id,
        "summary": result.get("summary", {}),
        "display_summary": result.get("display_summary"),
        "tables": [
            {"key": key, "label": label, "table": df_to_table(df)}
            for key, label, df in tables
        ],
        "text": result.get("text"),
        "maps": result.get("maps") or [],
        "carrier_clusters": result.get("carrier_clusters"),
        "log": result.get("log", []),
        "artifact_keys": sorted(artifacts),
        "auto_downloads": result.get("auto_downloads") or [],
    }


def open_excel_result(req: OpenAllocationExcelRequest) -> dict:
    session = SESSIONS.get(req.session_id)
    table = session_table(session, req.key)
    if session is None or table is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resultatet hittades inte (kör flödet igen).")
    label = session["labels"].get(req.key, req.key)
    include_header = session.get("flow_id") != "split-values"
    try:
        path = write_table_to_excel(table, label, include_header=include_header)
        open_path(path)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte öppna Excel-filen automatiskt. {exc}",
        ) from exc
    return {"opened": True, "path": path}


def table_column_text(session_id: str, key: str, column_index: int) -> dict:
    session = SESSIONS.get(session_id)
    table = session_table(session, key)
    if session is None or table is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resultatet hittades inte.")
    if column_index < 0 or column_index >= len(table.columns):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kolumnen hittades inte.")
    if _is_simple_table(table):
        values = [_cell(value) for value in table.column_values(column_index)]
    else:
        values = [_cell(value) for value in table.iloc[:, column_index].tolist()]
    while values and values[-1] == "":
        values.pop()
    return {"text": "\n".join(values)}


def _download_file_response(payload: dict) -> FileResponse:
    filename = str(payload.get("filename") or "download.csv")
    suffix = Path(filename).suffix or ".csv"
    media_type = str(payload.get("media_type") or "text/csv")
    path = payload.get("path")
    if path:
        return FileResponse(str(path), filename=filename, media_type=media_type)
    encoding = str(payload.get("encoding") or "utf-8-sig")
    content = payload.get("content", "")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        if isinstance(content, bytes):
            tmp.write(content)
        else:
            tmp.write(str(content).encode(encoding))
    finally:
        tmp.close()
    return FileResponse(tmp.name, filename=filename, media_type=media_type)


def download_result(session_id: str, key: str):
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resultatet hittades inte.")
    download_file = (session.get("download_files") or {}).get(key)
    if download_file is not None:
        return _download_file_response(download_file)
    table = session_table(session, key)
    if table is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resultatet hittades inte.")
    label = session["labels"].get(key, key)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    if _is_simple_table(table):
        table.write_csv(tmp.name)
    else:
        with open(tmp.name, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow([str(column) for column in table.columns])
            for row in table.itertuples(index=False, name=None):
                writer.writerow([_cell(value) for value in row])
    tmp.close()
    return FileResponse(tmp.name, filename=f"{label}.csv", media_type="text/csv")

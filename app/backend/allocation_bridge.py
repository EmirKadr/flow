from __future__ import annotations

import csv
import hashlib
import importlib
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
_LOAD_ERROR: str | None = None
SESSIONS: dict[str, dict] = {}
UPLOAD_CACHE_DIR = Path(tempfile.gettempdir()) / "flow_allocation_upload_cache"
UPLOAD_CACHE_TTL_SECONDS = 6 * 60 * 60
UPLOAD_CACHE_MAX_FILES = 64


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
DEFAULT_MAX_CSV_PARAM = "__default_max_csv_path"
PROCESS_AREA_FOCUS_PARAM = "__process_area_focus"
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
        "company": "GG",
        "exclude_customers": {"6005"},
        "label": "Bolag=GG, Kundnr!=6005",
        "visible_flow_ids": None,
    },
    "MG": {
        "company": "MG",
        "exclude_customers": {"40002", "90002"},
        "label": "Bolag=MG, Kundnr!=40002/90002",
        "visible_flow_ids": None,
    },
}
PROCESS_DEFAULT_AREA_RULE: dict[str, object] = {
    "company": "",
    "exclude_customers": set(),
    "label": "",
    "visible_flow_ids": None,
}
PROCESS_COMPANY_COLUMN_KEYS = {
    "bolag",
    "bolagnr",
    "bolagskod",
    "bol",
    "company",
    "companyid",
    "companynum",
}
PROCESS_CUSTOMER_COLUMN_KEYS = {
    "kund",
    "kundnr",
    "kundnummer",
    "kundnum",
    "custom",
    "customnum",
    "customernr",
    "customernumber",
    "customer",
    "customerid",
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
    engine_module, _flows_module = require_available()
    return {
        "observations_path": str(engine_module.business_observations_path(business_code)),
        "article_max_path": str(engine_module.business_artikel_max_path(business_code)),
    }


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


def _process_customer_values(value: object) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        raw_values = re.split(r"[,;\s]+", value)
    elif isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        raw_values = [value]
    return {
        _process_customer_value(item)
        for item in raw_values
        if _process_customer_value(item)
    }


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


def _process_rule_label(rule: dict) -> str:
    company = str(rule.get("company") or "").strip().upper()
    excluded = sorted(str(value) for value in (rule.get("exclude_customers") or set()) if str(value))
    parts: list[str] = []
    if company:
        parts.append(f"Bolag={company}")
    if excluded:
        parts.append(f"Kundnr!={'/'.join(excluded)}")
    return ", ".join(parts)


def _process_rule_filter_notice(rule: dict) -> str:
    company = str(rule.get("company") or "").strip().upper()
    excluded = sorted(str(value) for value in (rule.get("exclude_customers") or set()) if str(value))
    parts: list[str] = []
    if company:
        parts.append(f"Bolag {company}")
    if excluded:
        parts.append(f"exkl. kundnr {' och '.join(excluded)}")
    return f"Filter: {', '.join(parts)}" if parts else ""


def _normalize_process_area_rule(raw: dict | None, allowed_flow_ids: set[str] | None = None) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    company = str(_process_rule_values(raw, "company", "bolag") or "").strip().upper()
    excluded = _process_customer_values(
        _process_rule_values(raw, "exclude_customers", "excludeCustomers", "excluded_customers", "excludedCustomers")
    )
    visible_flow_ids = _process_visible_flow_ids(
        _process_rule_values(raw, "visible_flow_ids", "visibleFlowIds", "flow_ids", "flowIds"),
        allowed_flow_ids=allowed_flow_ids,
    )
    rule = {
        "company": company,
        "exclude_customers": excluded,
        "visible_flow_ids": visible_flow_ids,
    }
    rule["label"] = _process_rule_label(rule)
    return rule


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
        matrix[code] = _normalize_process_area_rule(raw_rule, allowed_flow_ids=allowed_flow_ids)
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
    return bool(rule and (rule.get("company") or rule.get("exclude_customers")))


def process_matrix_storage_payload(matrix: dict[str, dict] | None = None) -> dict[str, dict]:
    rules = normalize_process_matrix(matrix)
    payload: dict[str, dict] = {}
    for code, rule in rules.items():
        if code == "DEFAULT":
            continue
        visible_flow_ids = rule.get("visible_flow_ids")
        payload[code] = {
            "company": str(rule.get("company") or ""),
            "excludeCustomers": sorted(str(value) for value in (rule.get("exclude_customers") or set()) if str(value)),
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
            "company": str(rule.get("company") or ""),
            "excludeCustomers": sorted(str(value) for value in (rule.get("exclude_customers") or set()) if str(value)),
            "visibleFlowIds": None if visible_flow_ids is None else sorted(str(value) for value in visible_flow_ids),
            "label": str(rule.get("label") or ""),
            "filterLabel": _process_rule_filter_notice(rule),
        }
    return {
        "areas": areas,
        "flows": flows or [],
        "matrix": public_rules,
    }


def _process_column_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _process_filter_column(columns, aliases: set[str]) -> str | None:
    for column in columns:
        if _process_column_key(column) in aliases:
            return column
    return None


def _process_filter_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "nat", "none"}:
        return ""
    return text


def _process_company_value(value: object) -> str:
    return _process_filter_text(value).upper()


def _process_customer_value(value: object) -> str:
    text = re.sub(r"\s+", "", _process_filter_text(value))
    if re.fullmatch(r"\d+([,.]0+)?", text):
        return re.split(r"[,.]", text, maxsplit=1)[0]
    return text.upper()


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


def _write_process_filter_table(df, *, source_key: str, area_focus: str) -> Path:
    target = tempfile.NamedTemporaryFile(
        delete=False,
        prefix=f"flow_{area_focus.lower()}_{_safe_upload_stem(source_key)}_",
        suffix=".csv",
    )
    path = Path(target.name)
    target.close()
    df.to_csv(path, index=False, encoding="utf-8-sig", sep="\t")
    return path


def _apply_process_area_rule_to_table(df, rule: dict) -> tuple[object | None, dict | None]:
    company_column = _process_filter_column(df.columns, PROCESS_COMPANY_COLUMN_KEYS)
    customer_column = _process_filter_column(df.columns, PROCESS_CUSTOMER_COLUMN_KEYS)
    company = str(rule.get("company") or "").upper()
    excluded = {str(value).upper() for value in (rule.get("exclude_customers") or set())}
    if not company and not excluded:
        return None, None
    can_apply_company = bool(company and company_column is not None)
    can_apply_customer = bool(excluded and customer_column is not None)
    if not can_apply_company and not can_apply_customer:
        return None, None

    before = int(len(df))
    mask = None
    if can_apply_company:
        mask = df[company_column].map(_process_company_value).eq(company)
    if can_apply_customer:
        customer_mask = ~df[customer_column].map(_process_customer_value).isin(excluded)
        mask = customer_mask if mask is None else (mask & customer_mask)

    filtered = df.loc[mask].copy() if mask is not None else df.copy()
    return filtered, {
        "before": before,
        "after": int(len(filtered)),
        "company_column": str(company_column or ""),
        "customer_column": str(customer_column or ""),
    }


def apply_process_area_filters(
    files: dict[str, Path],
    area_focus: object,
    matrix: dict[str, dict] | None = None,
) -> tuple[dict[str, Path], list[Path], list[str]]:
    rule = process_area_rule(area_focus, matrix=matrix)
    if not process_rule_has_filters(rule):
        return files, [], []

    code = normalize_process_area_focus(area_focus)
    filtered_files = dict(files)
    temp_paths: list[Path] = []
    stats: list[dict] = []

    for key, raw_path in files.items():
        path = Path(raw_path)
        try:
            df = _read_process_filter_table(path)
            filtered_df, stat = _apply_process_area_rule_to_table(df, rule)
        except Exception:
            continue
        if filtered_df is None or stat is None:
            continue
        filtered_path = _write_process_filter_table(filtered_df, source_key=key, area_focus=code)
        filtered_files[key] = filtered_path
        temp_paths.append(filtered_path)
        stats.append({"key": key, **stat})

    if not stats:
        return filtered_files, temp_paths, []

    lines = [f"Omradesfilter {code}: {rule['label']}."]
    for stat in stats:
        columns = ", ".join(
            value for value in (stat.get("company_column"), stat.get("customer_column")) if value
        )
        suffix = f" ({columns})" if columns else ""
        lines.append(f"{stat['key']}: {stat['before']} -> {stat['after']} rader{suffix}.")
    return filtered_files, temp_paths, lines


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
        retained: list[tuple[float, Path]] = []
        for path in cache_dir.iterdir():
            try:
                if not path.is_file():
                    continue
                stat = path.stat()
                if now_ts - stat.st_mtime > UPLOAD_CACHE_TTL_SECONDS:
                    path.unlink(missing_ok=True)
                    continue
                retained.append((stat.st_mtime, path))
            except OSError:
                continue

        overflow = len(retained) - UPLOAD_CACHE_MAX_FILES
        if overflow > 0:
            for _mtime, path in sorted(retained)[:overflow]:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    continue
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


async def save_upload(upload: UploadFile, *, cache: bool = False, cache_key: str | None = None) -> Path:
    suffix = Path(upload.filename or "").suffix or ".csv"
    content = await upload.read()
    if cache:
        digest = hashlib.sha256(content).hexdigest()
        cache_dir = _active_upload_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        _cleanup_upload_cache()
        target = cache_dir / f"{digest}{suffix}"
        if not target.exists():
            tmp = tempfile.NamedTemporaryFile(delete=False, dir=cache_dir, prefix="pending_", suffix=suffix)
            try:
                tmp.write(content)
                tmp.close()
                Path(tmp.name).replace(target)
            except Exception:
                Path(tmp.name).unlink(missing_ok=True)
                raise
        _remember_upload_cache(cache_key, target)
        _cleanup_upload_cache()
        return target

    prefix = f"bem_allok_upload_{_safe_upload_stem(upload.filename)}_"
    tmp = tempfile.NamedTemporaryFile(delete=False, prefix=prefix, suffix=suffix)
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


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
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"message": str(exc), "trace": traceback.format_exc()},
        ) from exc

    tables = result.get("tables", [])
    artifacts = result.get("artifacts", {}) or {}
    session_id = uuid.uuid4().hex
    SESSIONS[session_id] = {
        "flow_id": flow_id,
        "tables": {key: df for key, _label, df in tables},
        "labels": {key: label for key, label, _df in tables},
        "artifacts": artifacts,
    }
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
        "log": result.get("log", []),
        "artifact_keys": sorted(artifacts),
    }


def open_excel_result(req: OpenAllocationExcelRequest) -> dict:
    session = SESSIONS.get(req.session_id)
    if session is None or req.key not in session["tables"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resultatet hittades inte (kör flödet igen).")
    label = session["labels"].get(req.key, req.key)
    table = session["tables"][req.key]
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
    if session is None or key not in session["tables"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resultatet hittades inte.")
    table = session["tables"][key]
    if column_index < 0 or column_index >= len(table.columns):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kolumnen hittades inte.")
    if _is_simple_table(table):
        values = [_cell(value) for value in table.column_values(column_index)]
    else:
        values = [_cell(value) for value in table.iloc[:, column_index].tolist()]
    while values and values[-1] == "":
        values.pop()
    return {"text": "\n".join(values)}


def download_result(session_id: str, key: str):
    session = SESSIONS.get(session_id)
    if session is None or key not in session["tables"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resultatet hittades inte.")
    label = session["labels"].get(key, key)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    table = session["tables"][key]
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

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
DEFAULT_MAX_CSV_PARAM = "__default_max_csv_path"


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
    return UPLOAD_CACHE_DIR / ".index"


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
            (UPLOAD_CACHE_DIR / previous).unlink(missing_ok=True)
        except OSError:
            pass


def _cleanup_upload_cache(now: float | None = None) -> None:
    try:
        if not UPLOAD_CACHE_DIR.exists():
            return
        now_ts = time.time() if now is None else now
        retained: list[tuple[float, Path]] = []
        for path in UPLOAD_CACHE_DIR.iterdir():
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
            existing = {path.name for path in UPLOAD_CACHE_DIR.iterdir() if path.is_file()}
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
        UPLOAD_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cleanup_upload_cache()
        target = UPLOAD_CACHE_DIR / f"{digest}{suffix}"
        if not target.exists():
            tmp = tempfile.NamedTemporaryFile(delete=False, dir=UPLOAD_CACHE_DIR, prefix="pending_", suffix=suffix)
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
    session_id = uuid.uuid4().hex
    SESSIONS[session_id] = {
        "flow_id": flow_id,
        "tables": {key: df for key, _label, df in tables},
        "labels": {key: label for key, label, _df in tables},
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

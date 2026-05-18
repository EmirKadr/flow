from __future__ import annotations

import importlib
import math
import os
import re
import subprocess
import sys
import tempfile
import threading
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
_LOAD_ERROR: str | None = None
SESSIONS: dict[str, dict] = {}


def _default_allokering_backend_dir() -> Path:
    projects_root = Path(__file__).resolve().parents[3]
    return projects_root / "allokering" / "web" / "backend"


def allokering_backend_dir() -> Path:
    configured = os.environ.get("BEMANNING_ALLOKERING_WEB_BACKEND")
    return Path(configured).expanduser().resolve() if configured else _default_allokering_backend_dir()


def _load_modules() -> tuple[ModuleType, ModuleType]:
    global _ENGINE_MODULE, _FLOWS_MODULE, _LOAD_ERROR
    with _MODULE_LOCK:
        if _ENGINE_MODULE is not None and _FLOWS_MODULE is not None:
            return _ENGINE_MODULE, _FLOWS_MODULE

        backend_dir = allokering_backend_dir()
        if not backend_dir.exists():
            _LOAD_ERROR = f"Allokering-webbens backend hittades inte: {backend_dir}"
            raise AllocationBridgeUnavailable(_LOAD_ERROR)

        allokering_root = backend_dir.parents[1]
        for path in (str(backend_dir), str(allokering_root)):
            if path not in sys.path:
                sys.path.insert(0, path)

        try:
            _ENGINE_MODULE = importlib.import_module("engine")
            _FLOWS_MODULE = importlib.import_module("flows")
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
        "message": _LOAD_ERROR or "Allokering är inte tillgängligt.",
        "backend_dir": str(allokering_backend_dir()),
    }


def require_available() -> tuple[ModuleType, ModuleType]:
    try:
        return _load_modules()
    except AllocationBridgeUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=unavailable_detail()) from exc


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


def df_to_table(df, preview_limit: int = 1000) -> dict:
    try:
        import pandas as pd  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise AllocationBridgeUnavailable("Pandas saknas för Allokering-resultat.") from exc

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


async def save_upload(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "").suffix or ".csv"
    prefix = f"bem_allok_upload_{_safe_upload_stem(upload.filename)}_"
    tmp = tempfile.NamedTemporaryFile(delete=False, prefix=prefix, suffix=suffix)
    tmp.write(await upload.read())
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
    except Exception:
        pass


def excel_writer_engine() -> str:
    if importlib.util.find_spec("openpyxl"):
        return "openpyxl"
    if importlib.util.find_spec("xlsxwriter"):
        return "xlsxwriter"
    raise RuntimeError("Saknar Excel-skrivare (installera openpyxl eller xlsxwriter).")


def open_df_in_excel_without_header(df, label: str) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{label}.xlsx")
    path = tmp.name
    tmp.close()
    import pandas as pd  # type: ignore

    with pd.ExcelWriter(path, engine=excel_writer_engine()) as writer:
        df.to_excel(writer, sheet_name=str(label)[:31] or "Sheet1", index=False, header=False)
    open_path(path)
    return path


async def form_to_flow_payload(form) -> tuple[dict[str, Path], dict[str, str], list[Path]]:
    files: dict[str, Path] = {}
    params: dict[str, str] = {}
    temp_paths: list[Path] = []
    for key, value in form.multi_items():
        if isinstance(value, StarletteUploadFile):
            if value.filename:
                path = await save_upload(value)
                files[key] = path
                temp_paths.append(path)
        elif isinstance(value, str) and value.strip() != "":
            params[key] = value
    return files, params, temp_paths


def run_flow_handler(flow_id: str, files: dict, params: dict) -> dict:
    _engine_module, flows_module = require_available()
    flow = flows_module.FLOW_BY_ID.get(flow_id)
    if flow is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Okänt flöde: {flow_id}")
    try:
        result = flow["handler"](files, params)
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
        "tables": [
            {"key": key, "label": label, "table": df_to_table(df)}
            for key, label, df in tables
        ],
        "text": result.get("text"),
        "log": result.get("log", []),
    }


def open_excel_result(req: OpenAllocationExcelRequest) -> dict:
    engine_module, _flows_module = require_available()
    session = SESSIONS.get(req.session_id)
    if session is None or req.key not in session["tables"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resultatet hittades inte (kör flödet igen).")
    label = session["labels"].get(req.key, req.key)
    if session.get("flow_id") == "split-values":
        path = open_df_in_excel_without_header(session["tables"][req.key], label=label)
    else:
        path = engine_module.open_df_in_excel({label: session["tables"][req.key]}, label=label)
    return {"opened": True, "path": path}


def table_column_text(session_id: str, key: str, column_index: int) -> dict:
    require_available()
    session = SESSIONS.get(session_id)
    if session is None or key not in session["tables"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resultatet hittades inte.")
    df = session["tables"][key]
    if column_index < 0 or column_index >= len(df.columns):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kolumnen hittades inte.")
    values = [_cell(value) for value in df.iloc[:, column_index].tolist()]
    while values and values[-1] == "":
        values.pop()
    return {"text": "\n".join(values)}


def download_result(session_id: str, key: str):
    require_available()
    session = SESSIONS.get(session_id)
    if session is None or key not in session["tables"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resultatet hittades inte.")
    label = session["labels"].get(key, key)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    session["tables"][key].to_csv(tmp.name, index=False, encoding="utf-8-sig")
    tmp.close()
    return FileResponse(tmp.name, filename=f"{label}.csv", media_type="text/csv")

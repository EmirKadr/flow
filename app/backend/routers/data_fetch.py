from __future__ import annotations

from datetime import datetime
import json
import logging
from pathlib import Path
import tempfile
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from openpyxl import Workbook
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..audit import log as audit_log
from ..config import settings
from ..data_fetch_service import (
    DataFetchConfigError,
    DataFetchPlanError,
    apply_prompt_period_hint,
    build_catalog_context,
    build_data_fetch_minimax_payload,
    catalog_summary,
    clear_catalog_cache,
    columns_for_response,
    load_catalog,
    parse_minimax_plan,
    project_rows,
    validate_plan_payload,
)
from ..deps import get_db, require_view_access
from ..models import User
from ..external_data_client import ExternalDataClient, ExternalDataClientError
from ..observability import add_span_attributes, start_span
from .assistant import _call_minimax


router = APIRouter(prefix="/api/query-data", tags=["query-data"])
logger = logging.getLogger(__name__)


class DataFetchPromptRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=4000)


class DataFetchRunRequest(BaseModel):
    plan: dict | None = None
    prompt: str | None = Field(default=None, max_length=4000)
    max_rows: int | None = Field(default=None, ge=1, le=5000)


DATA_FETCH_SESSIONS: dict[str, dict] = {}
DATA_FETCH_SESSION_DIR = Path(tempfile.gettempdir()) / "flow_data_fetch_sessions"
DATA_FETCH_SESSION_TTL_SECONDS = 2 * 60 * 60
DATA_FETCH_SESSION_MAX_COUNT = 12
DATA_FETCH_SESSION_MAX_BYTES = 128 * 1024 * 1024


def _user_session_key(user: User) -> str:
    return str(getattr(user, "id", "") or getattr(user, "username", ""))


def _data_fetch_session_path(session_id: str) -> Path:
    return DATA_FETCH_SESSION_DIR / f"{session_id}.json"


def _write_data_fetch_rows(session_id: str, rows: list[dict]) -> dict:
    DATA_FETCH_SESSION_DIR.mkdir(parents=True, exist_ok=True)
    path = _data_fetch_session_path(session_id)
    tmp = tempfile.NamedTemporaryFile(
        delete=False,
        dir=DATA_FETCH_SESSION_DIR,
        prefix="pending_",
        suffix=".json",
        mode="w",
        encoding="utf-8",
    )
    try:
        json.dump(rows, tmp, ensure_ascii=False, default=str)
        tmp.close()
        Path(tmp.name).replace(path)
    except Exception:
        Path(tmp.name).unlink(missing_ok=True)
        raise
    return {"rows_path": str(path), "rows_size_bytes": path.stat().st_size}


def _read_data_fetch_rows(session: dict) -> list[dict]:
    if "rows" in session:
        return list(session.get("rows") or [])
    path = Path(str(session.get("rows_path") or ""))
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resultatet hittades inte. Kör hämtningen igen.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resultatet hittades inte. Kör hämtningen igen.") from exc
    return payload if isinstance(payload, list) else []


def _remove_data_fetch_session(session: dict | None) -> None:
    if not session:
        return
    path = session.get("rows_path")
    if path:
        try:
            Path(str(path)).unlink(missing_ok=True)
        except OSError:
            pass


def _cleanup_data_fetch_sessions(now: float | None = None) -> None:
    now_ts = time.time() if now is None else now
    for session_id, session in list(DATA_FETCH_SESSIONS.items()):
        try:
            created_at = float(session.get("created_at") or now_ts)
        except (TypeError, ValueError):
            created_at = now_ts
        if now_ts - created_at > DATA_FETCH_SESSION_TTL_SECONDS:
            _remove_data_fetch_session(DATA_FETCH_SESSIONS.pop(session_id, None))

    ordered = sorted(
        DATA_FETCH_SESSIONS.items(),
        key=lambda item: float(item[1].get("created_at") or now_ts),
    )
    overflow = len(ordered) - DATA_FETCH_SESSION_MAX_COUNT
    if overflow > 0:
        for session_id, _session in ordered[:overflow]:
            _remove_data_fetch_session(DATA_FETCH_SESSIONS.pop(session_id, None))
        ordered = ordered[overflow:]

    total_bytes = sum(int(session.get("rows_size_bytes") or 0) for _session_id, session in ordered)
    if total_bytes > DATA_FETCH_SESSION_MAX_BYTES:
        for session_id, session in ordered:
            if len(DATA_FETCH_SESSIONS) <= 1:
                break
            _remove_data_fetch_session(DATA_FETCH_SESSIONS.pop(session_id, None))
            total_bytes -= int(session.get("rows_size_bytes") or 0)
            if total_bytes <= DATA_FETCH_SESSION_MAX_BYTES:
                break

    try:
        if DATA_FETCH_SESSION_DIR.exists():
            active = {
                Path(str(session.get("rows_path"))).resolve()
                for session in DATA_FETCH_SESSIONS.values()
                if session.get("rows_path")
            }
            for path in DATA_FETCH_SESSION_DIR.iterdir():
                try:
                    if path.is_file() and path.resolve() not in active and now_ts - path.stat().st_mtime > DATA_FETCH_SESSION_TTL_SECONDS:
                        path.unlink(missing_ok=True)
                except OSError:
                    continue
    except OSError:
        return


def _catalog_or_503():
    try:
        return load_catalog()
    except DataFetchConfigError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


def _max_rows(value: int | None) -> int | None:
    if value is None:
        return None
    configured = max(1, int(settings.DATA_SOURCE_MAX_ROWS or 1000))
    return min(max(1, value), configured)


REQUIRED_API_SETTINGS = (
    "DATA_SOURCE_API_BASE_URL",
    "DATA_SOURCE_API_KEY",
    "DATA_SOURCE_API_CLIENT",
    "DATA_SOURCE_API_KEY_HEADER",
    "DATA_SOURCE_API_CLIENT_HEADER",
    "DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE",
)


def _missing_api_settings() -> list[str]:
    return [
        setting_name
        for setting_name in REQUIRED_API_SETTINGS
        if not str(getattr(settings, setting_name, "")).strip()
    ]


def _api_client_or_503() -> ExternalDataClient:
    missing_settings = _missing_api_settings()
    if missing_settings:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Saknar {', '.join(missing_settings)} i servermiljön.",
        )
    return ExternalDataClient(
        base_url=settings.DATA_SOURCE_API_BASE_URL.strip(),
        api_key=settings.DATA_SOURCE_API_KEY.strip() or None,
        api_client=settings.DATA_SOURCE_API_CLIENT.strip() or None,
        api_key_header=settings.DATA_SOURCE_API_KEY_HEADER.strip() or None,
        api_client_header=settings.DATA_SOURCE_API_CLIENT_HEADER.strip() or None,
        view_data_path_template=settings.DATA_SOURCE_VIEW_DATA_PATH_TEMPLATE.strip(),
        timeout=settings.DATA_SOURCE_TIMEOUT_SECONDS,
        verify_ssl=settings.DATA_SOURCE_VERIFY_SSL,
        ca_bundle=settings.DATA_SOURCE_CA_BUNDLE.strip() or None,
    )


def _filter_summary(filters: list[dict] | None) -> list[dict]:
    return [
        {"id": item.get("id") or item.get("field"), "operator": item.get("operator")}
        for item in (filters or [])
        if isinstance(item, dict)
    ]


def _data_fetch_error_detail(message: str, error_id: str, plan: dict) -> dict:
    return {
        "message": message,
        "error_id": error_id,
        "view": plan.get("view"),
        "view_label": plan.get("view_label"),
    }


def _audit_data_fetch(
    db: Session,
    user: User,
    action: str,
    plan: dict,
    payload: dict,
) -> None:
    try:
        audit_log(
            db,
            "data_fetch",
            0,
            action,
            None,
            {
                "view": plan.get("view"),
                "view_label": plan.get("view_label"),
                "filters": _filter_summary(plan.get("filters")),
                **payload,
            },
            getattr(user, "id", None),
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not write data fetch audit event action=%s", action)


async def _plan_from_prompt(prompt: str) -> dict:
    if not settings.MINIMAX_API_KEY.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Datahämtning saknar MINIMAX_API_KEY i servermiljön.",
        )
    catalog = _catalog_or_503()
    catalog_context = build_catalog_context(prompt, catalog)
    minimax_payload = build_data_fetch_minimax_payload(prompt, catalog_context)
    raw_answer = await run_in_threadpool(_call_minimax, minimax_payload)
    try:
        plan = validate_plan_payload(parse_minimax_plan(raw_answer), catalog)
        return apply_prompt_period_hint(plan, prompt, catalog)
    except DataFetchPlanError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _validate_submitted_plan(plan: dict) -> dict:
    catalog = _catalog_or_503()
    try:
        return validate_plan_payload(plan, catalog)
    except DataFetchPlanError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _fetch_rows(plan: dict, error_id: str) -> list[dict]:
    client = _api_client_or_503()
    try:
        return client.fetch_data(
            plan["view"],
            filters=plan.get("filters") or None,
            identifiers=plan.get("identifiers") or None,
        )
    except ExternalDataClientError as exc:
        logger.warning(
            "Data fetch external request failed error_id=%s view=%s filters=%s reason=%s",
            error_id,
            plan.get("view"),
            _filter_summary(plan.get("filters")),
            exc,
        )
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=_data_fetch_error_detail(str(exc), error_id, plan),
        ) from exc


def _safe_cell(value) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _write_excel(session: dict) -> str:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Data"
    columns = session["columns"]
    rows = _read_data_fetch_rows(session)
    sheet.append([column["label"] for column in columns])
    for row in rows:
        sheet.append([_safe_cell(row.get(column["id"])) for column in columns])
    meta = workbook.create_sheet("Fråga")
    meta.append(["Fält", "Värde"])
    meta.append(["Vy", session["plan"].get("view")])
    meta.append(["Visningsnamn", session["plan"].get("view_label")])
    meta.append(["Antal rader i API-svar", session["total_rows"]])
    meta.append(["Exporterade rader", len(rows)])
    meta.append(["Skapad", datetime.now().isoformat(timespec="seconds")])

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    tmp.close()
    workbook.save(tmp.name)
    return tmp.name


@router.get("/health")
def data_fetch_health(
    _: User = Depends(require_view_access("dataFetch", "view")),
) -> dict:
    try:
        catalog = load_catalog()
        catalog_ready = True
        catalog_info = catalog_summary(catalog)
        message = ""
    except DataFetchConfigError as exc:
        catalog_ready = False
        catalog_info = {"views": 0, "columns": 0}
        message = str(exc)

    api_missing = _missing_api_settings()
    api_configured = not api_missing
    minimax_configured = bool(settings.MINIMAX_API_KEY.strip())
    return {
        "ok": catalog_ready and api_configured and minimax_configured,
        "catalog": catalog_info,
        "catalog_configured": catalog_ready,
        "api_configured": api_configured,
        "api_missing": api_missing,
        "minimax_configured": minimax_configured,
        "message": message,
    }


@router.post("/catalog/reload")
def reload_data_fetch_catalog(
    _: User = Depends(require_view_access("dataFetch", "edit")),
) -> dict:
    with start_span("data_fetch.catalog_reload"):
        clear_catalog_cache()
        catalog = _catalog_or_503()
        summary = catalog_summary(catalog)
        add_span_attributes({
            "data_fetch.views": summary.get("views", 0),
            "data_fetch.columns": summary.get("columns", 0),
        })
        return {"ok": True, "catalog": summary}


@router.post("/plan")
async def plan_data_fetch(
    payload: DataFetchPromptRequest,
    _: User = Depends(require_view_access("dataFetch", "view")),
) -> dict:
    with start_span("data_fetch.plan", {"data_fetch.input_chars": len(payload.prompt or "")}):
        plan = await _plan_from_prompt(payload.prompt)
        add_span_attributes({
            "data_fetch.view": plan.get("view", ""),
            "data_fetch.status": plan.get("status", "ok"),
        })
        return {"plan": plan}


@router.post("/run")
async def run_data_fetch(
    payload: DataFetchRunRequest,
    current_user: User = Depends(require_view_access("dataFetch", "view")),
    db: Session = Depends(get_db),
) -> dict:
    add_span_attributes({
        "data_fetch.has_plan": bool(payload.plan),
        "data_fetch.has_input": bool(payload.prompt and payload.prompt.strip()),
    })
    if payload.plan:
        plan = _validate_submitted_plan(payload.plan)
    elif payload.prompt and payload.prompt.strip():
        plan = await _plan_from_prompt(payload.prompt.strip())
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Skicka antingen prompt eller plan.")

    add_span_attributes({
        "data_fetch.view": plan.get("view", ""),
        "data_fetch.status": plan.get("status", "ok"),
    })
    if plan.get("status") == "needs_clarification":
        add_span_attributes({"data_fetch.result": "needs_clarification"})
        return {"plan": plan, "columns": [], "rows": [], "total_rows": 0, "session_id": None}

    error_id = uuid4().hex[:10]
    try:
        with start_span("data_fetch.external_fetch", {"data_fetch.view": plan.get("view", "")}):
            rows = await run_in_threadpool(_fetch_rows, plan, error_id)
    except HTTPException as exc:
        add_span_attributes({"data_fetch.result": "error", "data_fetch.status_code": exc.status_code})
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        _audit_data_fetch(
            db,
            current_user,
            "fetch_failed",
            plan,
            {
                "error_id": detail.get("error_id") or error_id,
                "status_code": exc.status_code,
                "message": detail.get("message") or str(exc.detail),
            },
        )
        raise
    except Exception as exc:
        add_span_attributes({"data_fetch.result": "error", "data_fetch.status_code": status.HTTP_500_INTERNAL_SERVER_ERROR})
        logger.exception("Data fetch failed unexpectedly error_id=%s view=%s", error_id, plan.get("view"))
        _audit_data_fetch(
            db,
            current_user,
            "fetch_failed",
            plan,
            {
                "error_id": error_id,
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "Oväntat serverfel i datahämtning.",
            },
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_data_fetch_error_detail(
                "Datahämtningen stoppades av ett oväntat serverfel. Använd fel-id:t för att hitta loggen.",
                error_id,
                plan,
            ),
        ) from exc
    max_rows = _max_rows(payload.max_rows)
    projected_rows = project_rows(rows, plan["output_columns"], max_rows)
    columns = columns_for_response(plan)
    _cleanup_data_fetch_sessions()
    session_id = uuid4().hex
    row_storage = _write_data_fetch_rows(session_id, projected_rows)
    DATA_FETCH_SESSIONS[session_id] = {
        "user_key": _user_session_key(current_user),
        "created_at": time.time(),
        "plan": plan,
        "columns": columns,
        **row_storage,
        "total_rows": len(rows),
        "shown_rows": len(projected_rows),
    }
    _cleanup_data_fetch_sessions()
    _audit_data_fetch(
        db,
        current_user,
        "fetch_success",
        plan,
        {
            "total_rows": len(rows),
            "shown_rows": len(projected_rows),
            "truncated": len(rows) > len(projected_rows),
        },
    )
    add_span_attributes({
        "data_fetch.result": "ok",
        "data_fetch.total_rows": len(rows),
        "data_fetch.shown_rows": len(projected_rows),
        "data_fetch.truncated": len(rows) > len(projected_rows),
    })
    return {
        "plan": plan,
        "columns": columns,
        "rows": projected_rows,
        "total_rows": len(rows),
        "shown_rows": len(projected_rows),
        "truncated": len(rows) > len(projected_rows),
        "session_id": session_id,
    }


@router.get("/export/{session_id}")
def export_data_fetch_excel(
    session_id: str,
    current_user: User = Depends(require_view_access("dataFetch", "view")),
):
    session = DATA_FETCH_SESSIONS.get(session_id)
    if not session or session.get("user_key") != _user_session_key(current_user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resultatet hittades inte. Kör hämtningen igen.")
    with start_span(
        "data_fetch.export",
        {
            "data_fetch.view": session["plan"].get("view", ""),
            "data_fetch.total_rows": session.get("total_rows", 0),
            "data_fetch.shown_rows": session.get("shown_rows", 0),
        },
    ):
        path = _write_excel(session)
    return FileResponse(
        path,
        filename=f"hamta-data-{session['plan'].get('view', 'export')}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

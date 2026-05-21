from __future__ import annotations

from datetime import datetime
import tempfile
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from openpyxl import Workbook
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ..config import settings
from ..data_fetch_service import (
    DataFetchConfigError,
    DataFetchPlanError,
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
from ..deps import require_view_access
from ..models import User
from ..external_data_client import ExternalDataClient, ExternalDataClientError
from .assistant import _call_minimax


router = APIRouter(prefix="/api/query-data", tags=["query-data"])


class DataFetchPromptRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=4000)


class DataFetchRunRequest(BaseModel):
    plan: dict | None = None
    prompt: str | None = Field(default=None, max_length=4000)
    max_rows: int = Field(default=500, ge=1, le=5000)


DATA_FETCH_SESSIONS: dict[str, dict] = {}


def _user_session_key(user: User) -> str:
    return str(getattr(user, "id", "") or getattr(user, "username", ""))


def _catalog_or_503():
    try:
        return load_catalog()
    except DataFetchConfigError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


def _max_rows(value: int) -> int:
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
    )


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
        return validate_plan_payload(parse_minimax_plan(raw_answer), catalog)
    except DataFetchPlanError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _validate_submitted_plan(plan: dict) -> dict:
    catalog = _catalog_or_503()
    try:
        return validate_plan_payload(plan, catalog)
    except DataFetchPlanError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _fetch_rows(plan: dict) -> list[dict]:
    client = _api_client_or_503()
    try:
        return client.fetch_data(
            plan["view"],
            filters=plan.get("filters") or None,
            identifiers=plan.get("identifiers") or None,
        )
    except ExternalDataClientError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


def _safe_cell(value) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _write_excel(session: dict) -> str:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Data"
    columns = session["columns"]
    rows = session["rows"]
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
    clear_catalog_cache()
    catalog = _catalog_or_503()
    return {"ok": True, "catalog": catalog_summary(catalog)}


@router.post("/plan")
async def plan_data_fetch(
    payload: DataFetchPromptRequest,
    _: User = Depends(require_view_access("dataFetch", "view")),
) -> dict:
    plan = await _plan_from_prompt(payload.prompt)
    return {"plan": plan}


@router.post("/run")
async def run_data_fetch(
    payload: DataFetchRunRequest,
    current_user: User = Depends(require_view_access("dataFetch", "view")),
) -> dict:
    if payload.plan:
        plan = _validate_submitted_plan(payload.plan)
    elif payload.prompt and payload.prompt.strip():
        plan = await _plan_from_prompt(payload.prompt.strip())
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Skicka antingen prompt eller plan.")

    if plan.get("status") == "needs_clarification":
        return {"plan": plan, "columns": [], "rows": [], "total_rows": 0, "session_id": None}

    rows = await run_in_threadpool(_fetch_rows, plan)
    max_rows = _max_rows(payload.max_rows)
    projected_rows = project_rows(rows, plan["output_columns"], max_rows)
    columns = columns_for_response(plan)
    session_id = uuid4().hex
    DATA_FETCH_SESSIONS[session_id] = {
        "user_key": _user_session_key(current_user),
        "plan": plan,
        "columns": columns,
        "rows": projected_rows,
        "total_rows": len(rows),
    }
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
    path = _write_excel(session)
    return FileResponse(
        path,
        filename=f"hamta-data-{session['plan'].get('view', 'export')}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

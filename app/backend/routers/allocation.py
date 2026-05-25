from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from .. import audit
from .. import allocation_bridge as bridge
from ..business_scope import DEFAULT_BUSINESS_CODE, normalize_business_code, user_business_id
from ..deps import get_db, require_allocation_tools_user
from ..models import Business, User
from ..settings_service import get_role_view_access
from ..user_access import can_use_allocation_process


router = APIRouter(
    prefix="/api/allokering",
    tags=["allokering"],
    dependencies=[Depends(require_allocation_tools_user)],
)

SELF_SERVICE_FLOW_IDS = {"split-values"}
BUSINESS_ARTICLE_MAX_FLOW_IDS = {"ordersaldo", "lyx", "pafyllnadsprio"}
logger = logging.getLogger(__name__)


def _role_access_for_user(db: Session | object, user: User) -> dict | None:
    try:
        return get_role_view_access(db, business_id=getattr(user, "business_id", None))  # type: ignore[arg-type]
    except Exception:
        return None


def _flow_allowed_for_user(flow_id: str, user: User, access: dict | None = None) -> bool:
    return can_use_allocation_process(user, access) or flow_id in SELF_SERVICE_FLOW_IDS


def _assert_flow_allowed(flow_id: str, user: User, access: dict | None = None) -> None:
    if not _flow_allowed_for_user(flow_id, user, access):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Bearbeta kräver behörighet")


def _flow_audit_payload(
    flow_id: str,
    files: dict | None,
    params: dict | None,
    *,
    result: dict | None = None,
    error_type: str | None = None,
) -> dict:
    payload = {
        "flow_id": flow_id,
        "file_keys": sorted(str(key) for key in (files or {}).keys()),
        "param_keys": sorted(str(key) for key in (params or {}).keys()),
    }
    if result is not None:
        payload["table_count"] = len(result.get("tables") or [])
        payload["has_session"] = bool(result.get("session_id"))
    if error_type:
        payload["error_type"] = error_type
    return payload


def _upload_failure_payload(
    *,
    flow_id: str | None = None,
    stage: str,
    error_type: str,
    status_code: int | None = None,
) -> dict:
    payload = {
        "stage": stage,
        "error_type": error_type,
    }
    if flow_id:
        payload["flow_id"] = flow_id
    if status_code is not None:
        payload["status_code"] = status_code
    return payload


def _audit_allocation_event(
    db: Session,
    user: User,
    *,
    action: str,
    payload: dict,
) -> None:
    audit.log_and_commit(
        db,
        entity_type="allocation_flow",
        entity_id=0,
        action=action,
        old_value=None,
        new_value=payload,
        user_id=getattr(user, "id", None),
        logger=logger,
        context=f"allocation audit event action={action}",
    )


def _session_owner_payload(user: User) -> dict:
    return {
        "user_id": getattr(user, "id", None),
        "business_id": getattr(user, "business_id", None),
    }


def _upload_cache_scope(user: User) -> str:
    user_id = getattr(user, "id", None)
    if user_id is not None:
        return f"user:{user_id}"
    return f"business:{getattr(user, 'business_id', None)}"


def _allocation_business_code(db: Session, user: User) -> str:
    business_id = user_business_id(db, user)
    business = db.get(Business, business_id) if business_id is not None else None
    return normalize_business_code(getattr(business, "code", None)) or DEFAULT_BUSINESS_CODE


def _assert_session_allowed(session_id: str, user: User) -> None:
    session = bridge.SESSIONS.get(session_id)
    owner = session.get("owner") if session is not None else None
    if not owner:
        return

    user_id = getattr(user, "id", None)
    owner_user_id = owner.get("user_id")
    if owner_user_id is not None:
        if user_id == owner_user_id:
            return
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resultatet hittades inte.")

    owner_business_id = owner.get("business_id")
    if owner_business_id is None or owner_business_id == getattr(user, "business_id", None):
        return
    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resultatet hittades inte.")


@router.get("/health")
def health(_user: User = Depends(require_allocation_tools_user)) -> dict:
    try:
        bridge.public_registry()
    except Exception:
        return bridge.unavailable_detail()
    return {
        "available": True,
        "status": "ok",
        "version": "inhouse",
        "title": "Lagerverktyg",
        "backend_dir": str(bridge.warehouse_tools_dir()),
    }


@router.get("/flows")
def list_flows(
    user: User = Depends(require_allocation_tools_user),
    db: Session = Depends(get_db),
) -> dict:
    flows = bridge.public_registry()
    if not can_use_allocation_process(user, _role_access_for_user(db, user)):
        flows = [flow for flow in flows if flow.get("id") in SELF_SERVICE_FLOW_IDS]
    return {"flows": flows}


@router.get("/pool")
def list_pool(
    user: User = Depends(require_allocation_tools_user),
    db: Session = Depends(get_db),
) -> dict:
    if not can_use_allocation_process(user, _role_access_for_user(db, user)):
        return {"pool": []}
    return {"pool": bridge.public_pool()}


@router.post("/detect")
async def detect(
    file: UploadFile = File(...),
    user: User = Depends(require_allocation_tools_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        path = await bridge.save_upload(file)
    except Exception as exc:
        _audit_allocation_event(
            db,
            user,
            action="upload_failed",
            payload=_upload_failure_payload(
                stage="save_upload",
                error_type=type(exc).__name__,
                status_code=getattr(exc, "status_code", None),
            ),
        )
        raise
    try:
        file_type = bridge.detect_file_type(path)
    except Exception as exc:
        _audit_allocation_event(
            db,
            user,
            action="detect_failed",
            payload=_upload_failure_payload(stage="detect", error_type=type(exc).__name__),
        )
        file_type = None
    finally:
        path.unlink(missing_ok=True)
    return {"file_type": file_type}


@router.post("/observations/update")
async def update_observations(
    file: UploadFile = File(...),
    user: User = Depends(require_allocation_tools_user),
    db: Session = Depends(get_db),
) -> dict:
    _assert_flow_allowed("observations-update", user, _role_access_for_user(db, user))
    engine_module, _flows_module = bridge.require_available()
    business_code = _allocation_business_code(db, user)
    data_paths = bridge.business_allocation_data_paths(business_code)
    try:
        path = await bridge.save_upload(file)
    except Exception as exc:
        _audit_allocation_event(
            db,
            user,
            action="upload_failed",
            payload=_upload_failure_payload(
                flow_id="observations-update",
                stage="save_upload",
                error_type=type(exc).__name__,
                status_code=getattr(exc, "status_code", None),
            ),
        )
        raise
    try:
        buffer_df = engine_module.read_table(str(path))
        result = engine_module.build_observations_update_result(
            buffer_df,
            observations_path=data_paths["observations_path"],
            artikel_max_out=data_paths["article_max_path"],
            push_to_github=True,
            business_code=business_code,
        )
    except Exception as exc:
        _audit_allocation_event(
            db,
            user,
            action="upload_failed",
            payload=_upload_failure_payload(
                flow_id="observations-update",
                stage="process_upload",
                error_type=type(exc).__name__,
                status_code=getattr(exc, "status_code", None),
            ),
        )
        raise
    finally:
        path.unlink(missing_ok=True)
    _audit_allocation_event(
        db,
        user,
        action="observations_update",
        payload={
            "flow_id": "observations-update",
            "business_code": business_code,
            "new_rows": int(result.new_row_count),
            "github_sent_rows": int(result.github_sent_rows),
            "article_max_rows": int(result.article_max_rows),
            "article_max_changed_rows": int(result.article_max_changed_rows),
            "pushed_to_github": bool(result.pushed_to_github),
        },
    )
    return {
        "new_rows": int(result.new_row_count),
        "github_sent_rows": int(result.github_sent_rows),
        "article_max_rows": int(result.article_max_rows),
        "article_max_changed_rows": int(result.article_max_changed_rows),
        "article_max_increased_rows": int(result.article_max_increased_rows),
        "article_max_decreased_rows": int(result.article_max_decreased_rows),
        "article_max_new_rows": int(result.article_max_new_rows),
        "article_max_removed_rows": int(result.article_max_removed_rows),
        "article_max_changed_examples": list(result.article_max_changed_examples),
        "pushed_to_github": bool(result.pushed_to_github),
        "business_code": business_code,
        "observations_path": result.observations_path,
        "article_max_path": result.article_max_path,
    }


@router.post("/flow/{flow_id}")
async def run_flow(
    flow_id: str,
    request: Request,
    user: User = Depends(require_allocation_tools_user),
    db: Session = Depends(get_db),
) -> dict:
    _assert_flow_allowed(flow_id, user, _role_access_for_user(db, user))
    try:
        form = await request.form()
        files, params, temp_paths = await bridge.form_to_flow_payload(form, cache_scope=_upload_cache_scope(user))
    except Exception as exc:
        _audit_allocation_event(
            db,
            user,
            action="upload_failed",
            payload=_upload_failure_payload(
                flow_id=flow_id,
                stage="parse_upload",
                error_type=type(exc).__name__,
                status_code=getattr(exc, "status_code", None),
            ),
        )
        raise
    try:
        default_max_csv_path = None
        if flow_id in BUSINESS_ARTICLE_MAX_FLOW_IDS and "max_csv" not in files:
            business_code = _allocation_business_code(db, user)
            default_max_csv_path = bridge.business_allocation_data_paths(business_code)["article_max_path"]
        if default_max_csv_path is not None:
            result = bridge.run_flow_handler(flow_id, files, params, default_max_csv_path=default_max_csv_path)
        else:
            result = bridge.run_flow_handler(flow_id, files, params)
        session_id = result.get("session_id")
        if session_id in bridge.SESSIONS:
            bridge.SESSIONS[session_id]["owner"] = _session_owner_payload(user)
        _audit_allocation_event(
            db,
            user,
            action="flow_run",
            payload=_flow_audit_payload(flow_id, files, params, result=result),
        )
        return result
    except Exception as exc:
        _audit_allocation_event(
            db,
            user,
            action="flow_failed",
            payload=_flow_audit_payload(flow_id, files, params, error_type=type(exc).__name__),
        )
        raise
    finally:
        for path in temp_paths:
            path.unlink(missing_ok=True)


@router.post("/open-excel")
def open_excel(
    req: bridge.OpenAllocationExcelRequest,
    user: User = Depends(require_allocation_tools_user),
) -> dict:
    _assert_session_allowed(req.session_id, user)
    return bridge.open_excel_result(req)


@router.get("/table-column/{session_id}/{key}/{column_index}")
def table_column(
    session_id: str,
    key: str,
    column_index: int,
    user: User = Depends(require_allocation_tools_user),
) -> dict:
    _assert_session_allowed(session_id, user)
    return bridge.table_column_text(session_id, key, column_index)


@router.get("/download/{session_id}/{key}")
def download(
    session_id: str,
    key: str,
    user: User = Depends(require_allocation_tools_user),
):
    _assert_session_allowed(session_id, user)
    return bridge.download_result(session_id, key)

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import audit
from .. import allocation_bridge as bridge
from ..business_scope import DEFAULT_BUSINESS_CODE, assert_user_can_access_business, get_business_by_code, normalize_business_code, user_business_id
from ..coredata_service import CoreDataError, find_coredata_file
from ..deps import get_db, require_allocation_tools_user, require_view_access
from ..models import Area, Business, User
from ..settings_service import ALLOCATION_PROCESS_MATRIX_KEY, get_json_setting, get_role_view_access, set_json_setting
from ..user_access import can_use_allocation_process, is_super_user


router = APIRouter(
    prefix="/api/allokering",
    tags=["allokering"],
    dependencies=[Depends(require_allocation_tools_user)],
)

SELF_SERVICE_FLOW_IDS = {"split-values"}
BUSINESS_ARTICLE_MAX_FLOW_IDS = {"ordersaldo", "lyx", "pafyllnadsprio"}
BUSINESS_COREDATA_FLOW_DEFAULTS = {
    "allocate": {"items": "item_option"},
    "forecast": {
        "custom": "custom",
        "item": "item",
        "item_alias": "item_alias",
        "dimension": "dimension",
        "pallet_type": "pallet_type",
        "item_option": "item_option",
    },
    "ytgenerering": {"location": "location"},
}
PROCESS_MATRIX_HIDDEN_FLOW_IDS = {"observations-update", "observations-sync", "update-check", "split-values"}
logger = logging.getLogger(__name__)


class AllocationProcessMatrixUpdate(BaseModel):
    matrix: dict[str, dict] = Field(default_factory=dict)


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
    area_focus: str | None = None,
) -> dict:
    payload = {
        "flow_id": flow_id,
        "file_keys": sorted(str(key) for key in (files or {}).keys()),
        "param_keys": sorted(str(key) for key in (params or {}).keys() if not str(key).startswith("__")),
    }
    if area_focus:
        payload["area_focus"] = area_focus
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


def _allocation_process_matrix_flows() -> list[dict]:
    flows: list[dict] = []
    for flow in bridge.public_registry():
        flow_id = str(flow.get("id") or "")
        if not flow_id or flow_id in PROCESS_MATRIX_HIDDEN_FLOW_IDS:
            continue
        if flow.get("view") != "combined":
            continue
        flows.append(
            {
                "id": flow_id,
                "label": str(flow.get("label") or flow_id),
                "category": str(flow.get("category") or ""),
            }
        )
    return flows


def _stored_process_matrix(db: Session | object, *, flows: list[dict] | None = None) -> dict[str, dict]:
    try:
        stored = get_json_setting(db, ALLOCATION_PROCESS_MATRIX_KEY, default={})  # type: ignore[arg-type]
    except Exception:
        stored = {}
    return bridge.normalize_process_matrix(stored, flows=flows)


def _active_area_codes_for_user(db: Session, user: User) -> set[str]:
    query = db.query(func.upper(Area.code)).filter(Area.is_active.is_(True))
    if not is_super_user(user):
        business_id = user_business_id(db, user)
        if business_id is not None:
            query = query.filter(Area.business_id == business_id)
    return {code for (code,) in query.all() if code}


def _process_matrix_response(db: Session, user: User) -> dict:
    flows = _allocation_process_matrix_flows()
    matrix = _stored_process_matrix(db, flows=flows)
    return bridge.process_matrix_public_payload(matrix, flows=flows, area_codes=_active_area_codes_for_user(db, user))


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


def _business_code_for_id(db: Session, user: User, business_id: int | None) -> str | None:
    if business_id is None:
        return None
    assert_user_can_access_business(db, user, business_id)
    business = db.get(Business, business_id)
    return normalize_business_code(getattr(business, "code", None)) if business is not None else None


def _business_id_from_area_focus(db: Session, user: User, area_focus: str | None) -> int | None:
    focus = bridge.normalize_process_area_focus(area_focus)
    if not focus or focus == "ALLT":
        return None

    area_id_match = focus.removeprefix("AREA:")
    if area_id_match.isdigit() and focus.startswith("AREA:"):
        area = db.get(Area, int(area_id_match))
        if area is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Omrade hittades inte")
        return getattr(area, "business_id", None)

    try:
        area = (
            db.query(Area)
            .filter(func.upper(Area.code) == focus)
            .filter(Area.is_active.is_(True))
            .order_by(Area.sort_order.asc(), Area.id.asc())
            .first()
        )
        if area is not None:
            return getattr(area, "business_id", None)
    except Exception:
        pass

    try:
        business = get_business_by_code(db, focus)
        if business is not None:
            return getattr(business, "id", None)
    except Exception:
        pass
    return None


def _allocation_business_code(db: Session, user: User, area_focus: str | None = None) -> str:
    try:
        focus_business_code = _business_code_for_id(db, user, _business_id_from_area_focus(db, user, area_focus))
        if focus_business_code:
            return focus_business_code
        business_id = user_business_id(db, user)
        return _business_code_for_id(db, user, business_id) or DEFAULT_BUSINESS_CODE
    except HTTPException:
        raise
    except Exception:
        return DEFAULT_BUSINESS_CODE


def _business_coredata_default_files(flow_id: str, files: dict, business_code: str) -> dict:
    defaults: dict = {}
    for file_key, coredata_type in BUSINESS_COREDATA_FLOW_DEFAULTS.get(flow_id, {}).items():
        if file_key in files:
            continue
        try:
            defaults[file_key] = find_coredata_file(coredata_type, business_code=business_code)
        except CoreDataError:
            continue
    return defaults


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


def _attach_required_session_artifacts(flow_id: str, params: dict, user: User) -> None:
    if flow_id != "ytgenerering":
        return
    forecast_session_id = str(params.get("forecast_session_id") or "").strip()
    if not forecast_session_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Kör Forecast först.")
    _assert_session_allowed(forecast_session_id, user)
    session = bridge.SESSIONS.get(forecast_session_id)
    if session is None or session.get("flow_id") != "forecast":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Forecast-sessionen hittades inte.")
    forecast_df = (session.get("tables") or {}).get("forecast")
    if forecast_df is not None:
        params["__forecast_df"] = forecast_df
        return
    artifact = (session.get("artifacts") or {}).get("forecast_json")
    if not artifact:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Forecast-resultatet saknar data för Ytgenerering.")
    params["__forecast_json"] = json.dumps(artifact, ensure_ascii=False)


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


@router.get("/process-matrix")
def get_process_matrix(
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("allocationProcess", "view")),
) -> dict:
    return _process_matrix_response(db, user)


@router.put("/process-matrix")
def update_process_matrix(
    payload: AllocationProcessMatrixUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_view_access("allocationProcessMatrix", "edit")),
) -> dict:
    flows = _allocation_process_matrix_flows()
    before = bridge.process_matrix_public_payload(_stored_process_matrix(db, flows=flows), flows=flows)
    next_matrix = bridge.normalize_process_matrix({"matrix": payload.matrix}, flows=flows)
    after = bridge.process_matrix_public_payload(next_matrix, flows=flows)
    set_json_setting(
        db,
        ALLOCATION_PROCESS_MATRIX_KEY,
        bridge.process_matrix_storage_payload(next_matrix),
        user_id=getattr(admin, "id", None),
    )
    if before.get("matrix") != after.get("matrix"):
        audit.log(
            db,
            entity_type="app_setting",
            entity_id=0,
            action="update_allocation_process_matrix",
            old_value={"key": ALLOCATION_PROCESS_MATRIX_KEY, "value": before.get("matrix")},
            new_value={"key": ALLOCATION_PROCESS_MATRIX_KEY, "value": after.get("matrix")},
            user_id=getattr(admin, "id", None),
            business_id=None,
        )
    db.commit()
    return _process_matrix_response(db, admin)


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
    area_focus: str | None = Form(None),
    user: User = Depends(require_allocation_tools_user),
    db: Session = Depends(get_db),
) -> dict:
    _assert_flow_allowed("observations-update", user, _role_access_for_user(db, user))
    engine_module, _flows_module = bridge.require_available()
    area_focus = bridge.normalize_process_area_focus(area_focus)
    business_code = _allocation_business_code(db, user, area_focus=area_focus)
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
            "area_focus": area_focus,
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
        "area_focus": area_focus,
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
        area_focus = bridge.normalize_process_area_focus(params.pop(bridge.PROCESS_AREA_FOCUS_PARAM, ""))
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
        process_matrix = _stored_process_matrix(db)
        if area_focus and not bridge.process_flow_visible(flow_id, area_focus, process_matrix):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Funktionen ar inte tillganglig for vald toggle")
        _attach_required_session_artifacts(flow_id, params, user)
        default_max_csv_path = None
        business_code = _allocation_business_code(db, user, area_focus=area_focus)
        coredata_files = _business_coredata_default_files(flow_id, files, business_code)
        if coredata_files:
            files = {**coredata_files, **files}
        files, filter_temp_paths, area_filter_log = bridge.apply_process_area_filters(files, area_focus, process_matrix)
        temp_paths.extend(filter_temp_paths)
        if flow_id in BUSINESS_ARTICLE_MAX_FLOW_IDS and "max_csv" not in files:
            default_max_csv_path = bridge.business_allocation_data_paths(business_code)["article_max_path"]
        if default_max_csv_path is not None:
            result = bridge.run_flow_handler(flow_id, files, params, default_max_csv_path=default_max_csv_path)
        else:
            result = bridge.run_flow_handler(flow_id, files, params)
        if area_filter_log:
            result["log"] = area_filter_log + list(result.get("log") or [])
            result["area_filter"] = {
                "area_focus": area_focus,
                "lines": area_filter_log,
            }
        session_id = result.get("session_id")
        if session_id in bridge.SESSIONS:
            bridge.SESSIONS[session_id]["owner"] = _session_owner_payload(user)
        _audit_allocation_event(
            db,
            user,
            action="flow_run",
            payload=_flow_audit_payload(flow_id, files, params, result=result, area_focus=area_focus),
        )
        return result
    except Exception as exc:
        _audit_allocation_event(
            db,
            user,
            action="flow_failed",
            payload=_flow_audit_payload(flow_id, files, params, error_type=type(exc).__name__, area_focus=area_focus),
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

from __future__ import annotations

import json
import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import audit
from .. import allocation_bridge as bridge
from ..business_scope import (
    DEFAULT_BUSINESS_CODE,
    assert_user_can_access_business,
    business_id_from_area_focus,
    normalize_business_id_param,
    normalize_business_code,
    user_business_id,
    visible_business_id,
)
from ..coredata_service import CoreDataError, find_coredata_file
from ..deps import get_db, require_allocation_tools_user, require_any_view_access, require_view_access
from ..models import AllocationUserFilterProfile, Area, Business, User
from ..observability import add_span_attributes, start_span
from ..settings_service import ALLOCATION_PROCESS_MATRIX_KEY, get_json_setting, get_role_view_access, set_json_setting
from ..user_access import can_access_view, can_use_allocation_process, is_super_user
from ..workflow_data import WorkflowDataError, allocation_api_source_map, resolve_sources, source_public_metadata


router = APIRouter(
    prefix="/api/allokering",
    tags=["allokering"],
)

SELF_SERVICE_FLOW_IDS = {"split-values"}
BUSINESS_ARTICLE_MAX_FLOW_IDS = {"ordersaldo", "lyx", "pafyllnadsprio"}
FORECAST_COREDATA_DEFAULTS = {
    "custom": "custom",
    "item": "item",
    "item_alias": "item_alias",
    "dimension": "dimension",
    "pallet_type": "pallet_type",
    "item_option": "item_option",
    "trans_agency": "trans_agency",
}
BUSINESS_COREDATA_FLOW_DEFAULTS = {
    "allocate": {"items": "item_option"},
    "goods-declaration": {"item_security_info": "item_security_info"},
    "forecast": FORECAST_COREDATA_DEFAULTS,
    "ytgenerering": {**FORECAST_COREDATA_DEFAULTS, "location": "location"},
}
PROCESS_MATRIX_HIDDEN_FLOW_IDS = {"observations-update", "observations-sync", "update-check", "split-values"}
logger = logging.getLogger(__name__)
ALLOCATION_FLOW_ERROR_CODE = "allocation_flow_failed"
ALLOCATION_FLOW_PATH_PREFIX = "/api/allokering/flow"
YTGENERERING_MAP_LAYOUT_KEY = "ytgenerering_map_layout"


class AllocationProcessMatrixUpdate(BaseModel):
    matrix: dict[str, dict] = Field(default_factory=dict)


class YtgenereringMapLayoutUpdate(BaseModel):
    locations: list[dict] = Field(default_factory=list)


class AllocationFilterProfileUpdate(BaseModel):
    profile: dict = Field(default_factory=dict)


class AllocationFilterProfileImport(BaseModel):
    user_id: int


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
    error_code: str | None = None,
    status_code: int | None = None,
    message: str | None = None,
    technical_message: str | None = None,
    area_focus: str | None = None,
    business_code: str | None = None,
    filter_log: list[str] | None = None,
    source_status: list[dict] | None = None,
    path: str | None = None,
) -> dict:
    payload = {
        "flow_id": flow_id,
        "file_keys": sorted(str(key) for key in (files or {}).keys()),
        "param_keys": sorted(str(key) for key in (params or {}).keys() if not str(key).startswith("__")),
    }
    if area_focus:
        payload["area_focus"] = area_focus
    if business_code:
        payload["business_code"] = business_code
    if filter_log:
        payload["filter_log"] = [_clean_audit_text(line, max_length=220) for line in filter_log[:8]]
    if source_status:
        payload["source_status"] = source_status
    if path:
        payload["path"] = path
    if result is not None:
        payload["table_count"] = len(result.get("tables") or [])
        payload["has_session"] = bool(result.get("session_id"))
    if error_type:
        payload["error_type"] = error_type
    if error_code:
        payload["error_code"] = error_code
    if status_code is not None:
        payload["status_code"] = status_code
    if message:
        payload["message"] = _clean_audit_text(message)
    if technical_message and technical_message != message:
        payload["technical_message"] = _clean_audit_text(technical_message)
    return payload


def _upload_failure_payload(
    *,
    flow_id: str | None = None,
    stage: str,
    error_type: str,
    status_code: int | None = None,
    message: str | None = None,
) -> dict:
    payload = {
        "stage": stage,
        "error_type": error_type,
    }
    if flow_id:
        payload["flow_id"] = flow_id
    if status_code is not None:
        payload["status_code"] = status_code
    if message:
        payload["message"] = _clean_audit_text(message)
    return payload


def _clean_audit_text(value: Any, *, max_length: int = 500) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    if not text:
        return None
    text = re.sub(r"[A-Za-z]:\\[^\s]+", "[path]", text)
    text = re.sub(r"/(?:[^/\s]+/){2,}[^\s]+", "[path]", text)
    return text[: max_length - 3] + "..." if len(text) > max_length else text


def _detail_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return _clean_audit_text(value)
    if isinstance(value, dict):
        for key in ("message", "detail", "error"):
            cleaned = _clean_audit_text(value.get(key))
            if cleaned:
                return cleaned
        return None
    return _clean_audit_text(value)


def _exception_audit_fields(exc: Exception) -> dict[str, Any]:
    status_code = getattr(exc, "status_code", None)
    detail = getattr(exc, "detail", None)
    error_type = type(exc).__name__
    error_code = None
    message = _clean_audit_text(str(exc))
    technical_message = None

    if isinstance(detail, dict):
        error_type = _clean_audit_text(detail.get("error_type"), max_length=120) or error_type
        error_code = _clean_audit_text(detail.get("error_code") or detail.get("code"), max_length=120)
        message = _detail_text(detail) or message
        technical_message = _clean_audit_text(detail.get("technical_message"))
    elif detail is not None:
        message = _detail_text(detail) or message

    return {
        "error_type": error_type,
        "error_code": error_code or (ALLOCATION_FLOW_ERROR_CODE if status_code else None),
        "status_code": status_code,
        "message": message,
        "technical_message": technical_message,
    }


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


def _allocation_flow_required_file_keys(flow: dict | None) -> set[str]:
    required: set[str] = set()
    for item in (flow or {}).get("inputs") or []:
        if item.get("type") == "file" and item.get("required"):
            required.add(str(item.get("key") or ""))
    for item in (flow or {}).get("coredata") or []:
        if item.get("required"):
            required.add(str(item.get("key") or ""))
    return {key for key in required if key}


def _with_api_source_metadata(flow: dict) -> dict:
    source_map = allocation_api_source_map(str(flow.get("id") or ""))
    if not source_map:
        return flow
    result = dict(flow)
    result["apiFirstSources"] = source_map
    source_meta: dict[str, dict] = {}
    for source_key in sorted(set(source_map.values())):
        try:
            source_meta[source_key] = source_public_metadata(source_key)
        except WorkflowDataError:
            continue
    if source_meta:
        result["apiSourceMetadata"] = source_meta

    inputs = []
    for item in flow.get("inputs") or []:
        next_item = dict(item)
        source_key = source_map.get(str(item.get("key") or ""))
        if source_key:
            next_item["apiPreferred"] = True
            next_item["apiSourceKey"] = source_key
            if source_key in source_meta:
                next_item["apiSource"] = source_meta[source_key]
        inputs.append(next_item)
    result["inputs"] = inputs

    coredata = []
    for item in flow.get("coredata") or []:
        next_item = dict(item)
        source_key = source_map.get(str(item.get("key") or ""))
        if source_key:
            next_item["apiPreferred"] = True
            next_item["apiSourceKey"] = source_key
            if source_key in source_meta:
                next_item["apiSource"] = source_meta[source_key]
        coredata.append(next_item)
    if coredata:
        result["coredata"] = coredata
    return result


def _stored_process_matrix(
    db: Session | object,
    *,
    flows: list[dict] | None = None,
    business_id: int | None = None,
) -> dict[str, dict]:
    try:
        stored = get_json_setting(db, ALLOCATION_PROCESS_MATRIX_KEY, default={}, business_id=business_id)  # type: ignore[arg-type]
    except Exception:
        stored = {}
    return bridge.normalize_process_matrix(stored, flows=flows)


def _process_matrix_area_options_for_user(
    db: Session,
    user: User,
    business_id: int | None = None,
) -> list[dict[str, object]]:
    query = db.query(Area).filter(Area.is_active.is_(True))
    scoped_business_id = visible_business_id(db, user, business_id)
    if scoped_business_id is not None:
        query = query.filter(Area.business_id == scoped_business_id)
    areas = (
        query.outerjoin(Business, Area.business_id == Business.id)
        .order_by(Business.sort_order.asc(), Area.sort_order.asc(), Area.name.asc(), Area.id.asc())
        .all()
    )
    return [
        {
            "code": bridge.normalize_process_area_focus(area.code),
            "label": bridge.normalize_process_area_focus(area.code) or area.name,
            "title": area.name,
            "areaId": area.id,
            "businessId": area.business_id,
        }
        for area in areas
        if bridge.normalize_process_area_focus(area.code)
    ]


def _merge_process_matrix_update(
    current_matrix: dict[str, dict],
    incoming_matrix: dict[str, dict],
    *,
    flows: list[dict],
    area_options: list[dict[str, object]],
) -> dict[str, dict]:
    current = bridge.normalize_process_matrix(current_matrix, flows=flows)
    incoming = bridge.normalize_process_matrix({"matrix": incoming_matrix}, flows=flows, area_options=area_options)
    editable_codes = {
        bridge.normalize_process_area_focus(area.get("code"))
        for area in bridge.normalize_process_area_options(area_options)
    }
    merged = dict(current)
    for raw_code in incoming_matrix:
        code = bridge.normalize_process_area_focus(raw_code)
        if code in editable_codes and code in incoming:
            merged[code] = incoming[code]
    return bridge.normalize_process_matrix(merged, flows=flows)


def _process_matrix_business_id(
    db: Session,
    user: User,
    *,
    business_id: int | None = None,
    area_focus: str | None = None,
) -> int | None:
    business_id = normalize_business_id_param(business_id)
    if business_id is not None:
        return visible_business_id(db, user, business_id)
    focus_business_id = business_id_from_area_focus(db, area_focus)
    if focus_business_id is not None:
        return visible_business_id(db, user, focus_business_id)
    return visible_business_id(db, user, business_id)


def _process_matrix_response(
    db: Session,
    user: User,
    *,
    business_id: int | None = None,
    area_focus: str | None = None,
) -> dict:
    flows = _allocation_process_matrix_flows()
    scoped_business_id = _process_matrix_business_id(db, user, business_id=business_id, area_focus=area_focus)
    matrix = _stored_process_matrix(db, flows=flows, business_id=scoped_business_id)
    area_options = _process_matrix_area_options_for_user(db, user, business_id=scoped_business_id)
    return bridge.process_matrix_public_payload(matrix, flows=flows, area_options=area_options)


def _allocation_settings_business_id(
    db: Session,
    user: User,
    area_focus: str | None = None,
    business_id: int | None = None,
) -> int | None:
    business_id = normalize_business_id_param(business_id)
    if business_id is not None:
        return visible_business_id(db, user, business_id)
    scoped_business_id = _business_id_from_area_focus(db, user, area_focus)
    if scoped_business_id is None:
        scoped_business_id = user_business_id(db, user)
    assert_user_can_access_business(db, user, scoped_business_id)
    return scoped_business_id


def _stored_ytgenerering_map_layout(db: Session, *, business_id: int | None = None) -> dict[str, object]:
    stored = get_json_setting(db, YTGENERERING_MAP_LAYOUT_KEY, default=None, business_id=business_id)
    return bridge.ytgenerering_map_layout_payload(stored)


def _stored_ytgenerering_map_rows(db: Session, *, business_id: int | None = None) -> list[dict[str, object]]:
    stored = get_json_setting(db, YTGENERERING_MAP_LAYOUT_KEY, default=None, business_id=business_id)
    return bridge.normalize_ytgenerering_map_location_rows(stored)


def _ytgenerering_map_layout_response(db: Session, user: User, *, business_id: int | None = None) -> dict[str, object]:
    payload = _stored_ytgenerering_map_layout(db, business_id=business_id)
    access = _role_access_for_user(db, user)
    return {
        **payload,
        "can_edit": can_access_view(user, access, "allocationSettings", "edit"),
    }


def _ytgenerering_location_options(
    db: Session,
    user: User,
    *,
    area_focus: str | None = None,
    business_id: int | None = None,
) -> list[dict[str, object]]:
    try:
        business_code = None
        if business_id is not None:
            try:
                business_code = _business_code_for_id(db, user, business_id)
            except Exception:
                business_code = None
        if not business_code:
            business_code = _allocation_business_code(db, user, area_focus=area_focus)
        location_path = find_coredata_file("location", business_code=business_code, db=db)
        return bridge.ytgenerering_location_option_rows(location_path)
    except Exception:
        logger.warning("Could not load ytgenerering location options.", exc_info=True)
        return []


def _ytgenerering_map_layout_with_options(
    db: Session,
    user: User,
    *,
    area_focus: str | None = None,
    business_id: int | None = None,
) -> dict[str, object]:
    business_id = _allocation_settings_business_id(db, user, area_focus, business_id)
    return {
        **_ytgenerering_map_layout_response(db, user, business_id=business_id),
        "available_locations": _ytgenerering_location_options(db, user, area_focus=area_focus, business_id=business_id),
    }


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


def _empty_filter_profile() -> dict:
    return {"version": bridge.USER_FILTER_PROFILE_VERSION, "flows": {}}


def _user_filter_profile(db: Session | object, user: User) -> dict:
    user_id = getattr(user, "id", None)
    if user_id is None or not hasattr(db, "query"):
        return _empty_filter_profile()
    try:
        row = db.query(AllocationUserFilterProfile).filter(AllocationUserFilterProfile.user_id == user_id).first()
    except Exception:
        return _empty_filter_profile()
    return bridge.normalize_user_filter_profile(getattr(row, "profile", None) if row is not None else None)


def _filter_profile_display_name(user: User) -> str:
    return str(getattr(user, "display_name", None) or getattr(user, "username", None) or getattr(user, "id", "")).strip()


def _accessible_filter_profile_user_query(db: Session, user: User):
    query = db.query(User).filter(User.is_active.is_(True))
    if not is_super_user(user):
        business_id = getattr(user, "business_id", None)
        if business_id is not None:
            query = query.filter(User.business_id == business_id)
    return query


def _assert_filter_profile_source_allowed(db: Session, user: User, source_user_id: int) -> User:
    source_user = _accessible_filter_profile_user_query(db, user).filter(User.id == source_user_id).first()
    if source_user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Anvandarens filtreringar hittades inte")
    return source_user


def _filter_profile_users(db: Session, user: User) -> list[dict]:
    users = _accessible_filter_profile_user_query(db, user).order_by(func.lower(User.username)).all()
    user_ids = [int(item.id) for item in users if getattr(item, "id", None) is not None]
    rows = []
    if user_ids:
        rows = db.query(AllocationUserFilterProfile).filter(AllocationUserFilterProfile.user_id.in_(user_ids)).all()
    profile_by_user = {int(row.user_id): bridge.normalize_user_filter_profile(row.profile) for row in rows}
    result = []
    for item in users:
        item_id = int(item.id)
        profile = profile_by_user.get(item_id, _empty_filter_profile())
        count = bridge.user_filter_profile_count(profile)
        result.append({
            "id": item_id,
            "username": str(item.username),
            "name": _filter_profile_display_name(item),
            "is_current": item_id == getattr(user, "id", None),
            "has_filters": count > 0,
            "filter_count": count,
        })
    return result


def _filter_profile_response(db: Session, user: User) -> dict:
    return {
        "profile": _user_filter_profile(db, user),
        "users": _filter_profile_users(db, user),
    }


def _set_user_filter_profile(db: Session, user: User, profile: object) -> dict:
    user_id = getattr(user, "id", None)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Anvandare saknas")
    normalized = bridge.normalize_user_filter_profile(profile, flows=bridge.public_registry())
    row = db.query(AllocationUserFilterProfile).filter(AllocationUserFilterProfile.user_id == user_id).first()
    if row is None:
        row = AllocationUserFilterProfile(user_id=user_id, profile=normalized)
        db.add(row)
    else:
        row.profile = normalized
    db.flush()
    return normalized


def _filter_profile_from_params_or_db(params: dict, db: Session | object, user: User) -> dict:
    raw = params.pop(bridge.USER_FILTERS_PARAM, None)
    if raw:
        try:
            return bridge.normalize_user_filter_profile(json.loads(raw), flows=bridge.public_registry())
        except Exception:
            return _empty_filter_profile()
    return _user_filter_profile(db, user)


def _business_code_for_id(db: Session, user: User, business_id: int | None) -> str | None:
    if business_id is None:
        return None
    assert_user_can_access_business(db, user, business_id)
    business = db.get(Business, business_id)
    return normalize_business_code(getattr(business, "code", None)) if business is not None else None


def _business_id_from_area_focus(db: Session, user: User, area_focus: str | None) -> int | None:
    return business_id_from_area_focus(db, bridge.normalize_process_area_focus(area_focus))


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


def _business_coredata_default_files(
    flow_id: str,
    files: dict,
    business_code: str,
    db: Session | None = None,
) -> dict:
    defaults: dict = {}
    for file_key, coredata_type in BUSINESS_COREDATA_FLOW_DEFAULTS.get(flow_id, {}).items():
        if file_key in files:
            continue
        try:
            defaults[file_key] = find_coredata_file(coredata_type, business_code=business_code, db=db)
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
        return
    _assert_session_allowed(forecast_session_id, user)
    session = bridge.SESSIONS.get(forecast_session_id)
    if session is None or session.get("flow_id") != "forecast":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Forecast-sessionen hittades inte.")
    submitted_clusters = str(params.get("carrier_clusters_json") or "").strip()
    artifacts = bridge.session_artifacts(session)
    if submitted_clusters:
        params["__carrier_clusters_json"] = submitted_clusters
    elif artifacts.get("carrier_clusters"):
        params["__carrier_clusters_json"] = json.dumps(artifacts["carrier_clusters"], ensure_ascii=False)
    forecast_df = bridge.session_table(session, "forecast")
    if forecast_df is not None:
        params["__forecast_df"] = forecast_df
        return
    artifact = artifacts.get("forecast_json")
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
    flows = [_with_api_source_metadata(flow) for flow in bridge.public_registry()]
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
    business_id: int | None = Query(None),
    area_focus: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_any_view_access(("allocationProcess", "allocationProcessMatrix"), "view")),
) -> dict:
    return _process_matrix_response(db, user, business_id=business_id, area_focus=area_focus)


@router.put("/process-matrix")
def update_process_matrix(
    payload: AllocationProcessMatrixUpdate,
    business_id: int | None = Query(None),
    area_focus: str | None = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_view_access("allocationProcessMatrix", "edit")),
) -> dict:
    flows = _allocation_process_matrix_flows()
    scoped_business_id = _process_matrix_business_id(db, admin, business_id=business_id, area_focus=area_focus)
    area_options = _process_matrix_area_options_for_user(db, admin, business_id=scoped_business_id)
    current_matrix = _stored_process_matrix(db, flows=flows, business_id=scoped_business_id)
    before = bridge.process_matrix_public_payload(current_matrix, flows=flows, area_options=area_options)
    next_matrix = _merge_process_matrix_update(
        current_matrix,
        payload.matrix,
        flows=flows,
        area_options=area_options,
    )
    after = bridge.process_matrix_public_payload(next_matrix, flows=flows, area_options=area_options)
    set_json_setting(
        db,
        ALLOCATION_PROCESS_MATRIX_KEY,
        bridge.process_matrix_storage_payload(next_matrix),
        user_id=getattr(admin, "id", None),
        business_id=scoped_business_id,
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
            business_id=scoped_business_id,
        )
    db.commit()
    return _process_matrix_response(db, admin, business_id=scoped_business_id)


@router.get("/filter-profile")
def get_filter_profile(
    db: Session = Depends(get_db),
    user: User = Depends(require_allocation_tools_user),
) -> dict:
    return _filter_profile_response(db, user)


@router.put("/filter-profile")
def update_filter_profile(
    payload: AllocationFilterProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_allocation_tools_user),
) -> dict:
    before = _user_filter_profile(db, user)
    after = _set_user_filter_profile(db, user, payload.profile)
    if before != after:
        audit.log(
            db,
            entity_type="allocation_filter_profile",
            entity_id=int(getattr(user, "id", 0) or 0),
            action="update_allocation_filter_profile",
            old_value={"filter_count": bridge.user_filter_profile_count(before)},
            new_value={"filter_count": bridge.user_filter_profile_count(after)},
            user_id=getattr(user, "id", None),
            business_id=getattr(user, "business_id", None),
        )
    db.commit()
    return _filter_profile_response(db, user)


@router.post("/filter-profile/import")
def import_filter_profile(
    payload: AllocationFilterProfileImport,
    db: Session = Depends(get_db),
    user: User = Depends(require_allocation_tools_user),
) -> dict:
    source_user = _assert_filter_profile_source_allowed(db, user, payload.user_id)
    source_profile = _user_filter_profile(db, source_user)
    if bridge.user_filter_profile_count(source_profile) <= 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Anvandaren har inga sparade filtreringar")
    before = _user_filter_profile(db, user)
    after = _set_user_filter_profile(db, user, source_profile)
    audit.log(
        db,
        entity_type="allocation_filter_profile",
        entity_id=int(getattr(user, "id", 0) or 0),
        action="import_allocation_filter_profile",
        old_value={"filter_count": bridge.user_filter_profile_count(before)},
        new_value={
            "filter_count": bridge.user_filter_profile_count(after),
            "source_user_id": getattr(source_user, "id", None),
        },
        user_id=getattr(user, "id", None),
        business_id=getattr(user, "business_id", None),
    )
    db.commit()
    return _filter_profile_response(db, user)


@router.get("/ytgenerering-map-layout")
def get_ytgenerering_map_layout(
    area_focus: str | None = None,
    business_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("allocationSettings", "view")),
) -> dict:
    return _ytgenerering_map_layout_with_options(
        db,
        user,
        area_focus=bridge.normalize_process_area_focus(area_focus or ""),
        business_id=business_id,
    )


@router.put("/ytgenerering-map-layout")
def update_ytgenerering_map_layout(
    payload: YtgenereringMapLayoutUpdate,
    area_focus: str | None = None,
    business_id: int | None = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_view_access("allocationSettings", "edit")),
) -> dict:
    business_id = _allocation_settings_business_id(db, admin, area_focus, business_id)
    before = _stored_ytgenerering_map_layout(db, business_id=business_id)
    rows = bridge.normalize_ytgenerering_map_location_rows(payload.locations)
    if not rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ytkartan behöver minst en giltig UTL-yta.")
    set_json_setting(
        db,
        YTGENERERING_MAP_LAYOUT_KEY,
        {"version": 1, "locations": rows},
        user_id=getattr(admin, "id", None),
        business_id=business_id,
    )
    after = _stored_ytgenerering_map_layout(db, business_id=business_id)
    if before.get("locations") != after.get("locations"):
        audit.log(
            db,
            entity_type="app_setting",
            entity_id=0,
            action="update_ytgenerering_map_layout",
            old_value={"key": YTGENERERING_MAP_LAYOUT_KEY, "count": len(before.get("locations") or [])},
            new_value={"key": YTGENERERING_MAP_LAYOUT_KEY, "count": len(after.get("locations") or [])},
            user_id=getattr(admin, "id", None),
            business_id=business_id,
        )
    db.commit()
    return _ytgenerering_map_layout_with_options(
        db,
        admin,
        area_focus=bridge.normalize_process_area_focus(area_focus or ""),
        business_id=business_id,
    )


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
                message=str(exc),
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
            payload=_upload_failure_payload(stage="detect", error_type=type(exc).__name__, message=str(exc)),
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
                message=str(exc),
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
                message=str(exc),
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
    add_span_attributes({"allocation.flow_id": flow_id})
    _assert_flow_allowed(flow_id, user, _role_access_for_user(db, user))
    try:
        with start_span("allocation.flow.parse_upload", {"allocation.flow_id": flow_id}):
            form = await request.form()
            files, params, temp_paths = await bridge.form_to_flow_payload(form, cache_scope=_upload_cache_scope(user))
            area_focus = bridge.normalize_process_area_focus(params.pop(bridge.PROCESS_AREA_FOCUS_PARAM, ""))
            add_span_attributes({
                "allocation.file_key_count": len(files),
                "allocation.param_key_count": len([key for key in params if not str(key).startswith("__")]),
                "allocation.area_focus": area_focus or "ALLT",
            })
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
                message=str(exc),
            ),
        )
        raise
    business_code = None
    area_filter_log: list[str] = []
    user_filter_log: list[str] = []
    source_log: list[str] = []
    source_status: list[dict] = []
    flow_path = f"{ALLOCATION_FLOW_PATH_PREFIX}/{flow_id}"
    try:
        user_filter_profile = _filter_profile_from_params_or_db(params, db, user)
        process_matrix = _stored_process_matrix(db)
        if area_focus and not bridge.process_flow_visible(flow_id, area_focus, process_matrix):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Funktionen ar inte tillganglig for vald toggle")
        _attach_required_session_artifacts(flow_id, params, user)
        default_max_csv_path = None
        business_code = _allocation_business_code(db, user, area_focus=area_focus)
        add_span_attributes({"allocation.business_code": business_code})
        coredata_files = _business_coredata_default_files(flow_id, files, business_code, db)
        if coredata_files:
            files = {**coredata_files, **files}
        source_map = bridge.api_source_map_for_user_profile(
            allocation_api_source_map(flow_id),
            flow_id,
            user_filter_profile,
        )
        if source_map:
            flow = bridge.public_registry()
            flow_by_id = {str(item.get("id") or ""): item for item in flow}
            required_keys = _allocation_flow_required_file_keys(flow_by_id.get(flow_id))
            try:
                with start_span("allocation.flow.resolve_sources", {"allocation.flow_id": flow_id}):
                    source_resolution = resolve_sources(source_map, files, required_keys=required_keys)
            except WorkflowDataError as exc:
                source_status = exc.audit_entries
                raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
            files = source_resolution.files
            temp_paths.extend(source_resolution.temp_paths)
            source_log = source_resolution.log_lines
            source_status = source_resolution.audit_entries
        with start_span("allocation.flow.apply_filters", {"allocation.flow_id": flow_id, "allocation.area_focus": area_focus or "ALLT"}):
            files, filter_temp_paths, area_filter_log = bridge.apply_process_area_filters(files, area_focus, process_matrix)
            temp_paths.extend(filter_temp_paths)
            files, user_filter_temp_paths, user_filter_log = bridge.apply_user_flow_filters(files, flow_id, user_filter_profile)
            temp_paths.extend(user_filter_temp_paths)
        if flow_id == "ytgenerering":
            ytgenerering_focus = area_focus or "ALLT"
            map_business_id = _allocation_settings_business_id(db, user, area_focus)
            if area_focus:
                params[bridge.PROCESS_AREA_FOCUS_PARAM] = area_focus
            bridge.apply_ytgenerering_user_settings(params, user_filter_profile, area_focus=ytgenerering_focus)
            params["__ytgenerering_map_locations_json"] = json.dumps(
                _stored_ytgenerering_map_rows(db, business_id=map_business_id),
                ensure_ascii=False,
            )
        if flow_id in BUSINESS_ARTICLE_MAX_FLOW_IDS and "max_csv" not in files:
            try:
                default_max_csv_path = bridge.business_article_max_path_for_flow(business_code)
            except FileNotFoundError as exc:
                raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        if default_max_csv_path is not None:
            with start_span("allocation.flow.engine_run", {"allocation.flow_id": flow_id, "allocation.default_max_csv": True}):
                result = bridge.run_flow_handler(flow_id, files, params, default_max_csv_path=default_max_csv_path)
        else:
            with start_span("allocation.flow.engine_run", {"allocation.flow_id": flow_id, "allocation.default_max_csv": False}):
                result = bridge.run_flow_handler(flow_id, files, params)
        add_span_attributes({
            "allocation.result_table_count": len(result.get("tables") or []),
            "allocation.has_session": bool(result.get("session_id")),
        })
        if area_filter_log:
            result["log"] = area_filter_log + list(result.get("log") or [])
            result["area_filter"] = {
                "area_focus": area_focus,
                "lines": area_filter_log,
            }
        if user_filter_log:
            result["log"] = user_filter_log + list(result.get("log") or [])
            result["user_filter"] = {
                "lines": user_filter_log,
            }
        if source_log:
            result["log"] = source_log + list(result.get("log") or [])
            result["source_status"] = source_status
        session_id = result.get("session_id")
        if session_id in bridge.SESSIONS:
            bridge.SESSIONS[session_id]["owner"] = _session_owner_payload(user)
        _audit_allocation_event(
            db,
            user,
            action="flow_run",
            payload=_flow_audit_payload(
                flow_id,
                files,
                params,
                result=result,
                area_focus=area_focus,
                business_code=business_code,
                filter_log=area_filter_log + user_filter_log,
                source_status=source_status,
            ),
        )
        return result
    except Exception as exc:
        error_fields = _exception_audit_fields(exc)
        _audit_allocation_event(
            db,
            user,
            action="flow_failed",
            payload=_flow_audit_payload(
                flow_id,
                files,
                params,
                error_type=error_fields["error_type"],
                error_code=error_fields["error_code"],
                status_code=error_fields["status_code"],
                message=error_fields["message"],
                technical_message=error_fields["technical_message"],
                area_focus=area_focus,
                business_code=business_code,
                filter_log=area_filter_log + user_filter_log,
                source_status=source_status,
                path=flow_path,
            ),
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
    with start_span("allocation.open_excel"):
        _assert_session_allowed(req.session_id, user)
        return bridge.open_excel_result(req)


@router.get("/table-column/{session_id}/{key}/{column_index}")
def table_column(
    session_id: str,
    key: str,
    column_index: int,
    user: User = Depends(require_allocation_tools_user),
) -> dict:
    with start_span("allocation.table_column", {"allocation.column_index": column_index}):
        _assert_session_allowed(session_id, user)
        return bridge.table_column_text(session_id, key, column_index)


@router.get("/download/{session_id}/{key}")
def download(
    session_id: str,
    key: str,
    user: User = Depends(require_allocation_tools_user),
):
    with start_span("allocation.download"):
        _assert_session_allowed(session_id, user)
        return bridge.download_result(session_id, key)

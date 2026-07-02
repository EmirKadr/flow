from __future__ import annotations

from copy import deepcopy
import json
import logging
from pathlib import Path
import re
import threading
import time
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

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


from . import allocation_helpers

router = APIRouter(
    prefix="/api/allokering",
    tags=["allokering"],
)

logger = logging.getLogger(__name__)
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
    flows = [allocation_helpers._with_api_source_metadata(flow) for flow in bridge.public_registry()]
    if not can_use_allocation_process(user, allocation_helpers._role_access_for_user(db, user)):
        flows = [flow for flow in flows if flow.get("id") in allocation_helpers.SELF_SERVICE_FLOW_IDS]
    return {"flows": flows}


@router.get("/pool")
def list_pool(
    user: User = Depends(require_allocation_tools_user),
    db: Session = Depends(get_db),
) -> dict:
    if not can_use_allocation_process(user, allocation_helpers._role_access_for_user(db, user)):
        return {"pool": []}
    return {"pool": bridge.public_pool()}


@router.get("/process-matrix")
def get_process_matrix(
    business_id: int | None = Query(None),
    area_focus: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_any_view_access(("allocationProcess", "allocationProcessMatrix"), "view")),
) -> dict:
    return allocation_helpers._process_matrix_response(db, user, business_id=business_id, area_focus=area_focus)


@router.put("/process-matrix")
def update_process_matrix(
    payload: allocation_helpers.AllocationProcessMatrixUpdate,
    business_id: int | None = Query(None),
    area_focus: str | None = Query(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_view_access("allocationProcessMatrix", "edit")),
) -> dict:
    flows = allocation_helpers._allocation_process_matrix_flows()
    scoped_business_id = allocation_helpers._process_matrix_business_id(db, admin, business_id=business_id, area_focus=area_focus)
    area_options = allocation_helpers._process_matrix_area_options_for_user(db, admin, business_id=scoped_business_id)
    current_matrix = allocation_helpers._stored_process_matrix(db, flows=flows, business_id=scoped_business_id)
    before = bridge.process_matrix_public_payload(current_matrix, flows=flows, area_options=area_options)
    next_matrix = allocation_helpers._merge_process_matrix_update(
        current_matrix,
        payload.matrix,
        flows=flows,
        area_options=area_options,
    )
    after = bridge.process_matrix_public_payload(next_matrix, flows=flows, area_options=area_options)
    allocation_helpers.set_json_setting(
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
    return allocation_helpers._process_matrix_response(db, admin, business_id=scoped_business_id)


@router.get("/filter-profile")
def get_filter_profile(
    db: Session = Depends(get_db),
    user: User = Depends(require_allocation_tools_user),
) -> dict:
    return allocation_helpers._filter_profile_response(db, user)


@router.put("/filter-profile")
def update_filter_profile(
    payload: allocation_helpers.AllocationFilterProfileUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_allocation_tools_user),
) -> dict:
    before = allocation_helpers._user_filter_profile(db, user)
    after = allocation_helpers._set_user_filter_profile(db, user, payload.profile)
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
    return allocation_helpers._filter_profile_response(db, user)


@router.post("/filter-profile/import")
def import_filter_profile(
    payload: allocation_helpers.AllocationFilterProfileImport,
    db: Session = Depends(get_db),
    user: User = Depends(require_allocation_tools_user),
) -> dict:
    source_user = allocation_helpers._assert_filter_profile_source_allowed(db, user, payload.user_id)
    source_profile = allocation_helpers._user_filter_profile(db, source_user)
    if bridge.user_filter_profile_count(source_profile) <= 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Anvandaren har inga sparade filtreringar")
    before = allocation_helpers._user_filter_profile(db, user)
    after = allocation_helpers._set_user_filter_profile(db, user, source_profile)
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
    return allocation_helpers._filter_profile_response(db, user)


@router.get("/ytgenerering-map-layout")
def get_ytgenerering_map_layout(
    area_focus: str | None = None,
    business_id: int | None = Query(None),
    include_options: bool = Query(True),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("allocationSettings", "view")),
) -> dict:
    return allocation_helpers._ytgenerering_map_layout_with_options(
        db,
        user,
        area_focus=bridge.normalize_process_area_focus(area_focus or ""),
        business_id=business_id,
        include_options=include_options,
    )


@router.get("/ytgenerering-location-options")
def get_ytgenerering_location_options(
    area_focus: str | None = None,
    business_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("allocationSettings", "view")),
) -> dict:
    scoped_business_id = allocation_helpers._allocation_settings_business_id(db, user, area_focus, business_id)
    return {
        "available_locations": allocation_helpers._ytgenerering_location_options(
            db,
            user,
            area_focus=bridge.normalize_process_area_focus(area_focus or ""),
            business_id=scoped_business_id,
        )
    }


@router.put("/ytgenerering-map-layout")
def update_ytgenerering_map_layout(
    payload: allocation_helpers.YtgenereringMapLayoutUpdate,
    area_focus: str | None = None,
    business_id: int | None = Query(None),
    include_options: bool = Query(True),
    db: Session = Depends(get_db),
    admin: User = Depends(require_view_access("allocationSettings", "edit")),
) -> dict:
    business_id = allocation_helpers._allocation_settings_business_id(db, admin, area_focus, business_id)
    before = allocation_helpers._stored_ytgenerering_map_layout(db, business_id=business_id)
    rows = bridge.normalize_ytgenerering_map_location_rows(payload.locations)
    if not rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ytkartan behöver minst en giltig UTL-yta.")
    allocation_helpers.set_json_setting(
        db,
        allocation_helpers.YTGENERERING_MAP_LAYOUT_KEY,
        {"version": 1, "locations": rows},
        user_id=getattr(admin, "id", None),
        business_id=business_id,
    )
    after = allocation_helpers._stored_ytgenerering_map_layout(db, business_id=business_id)
    if before.get("locations") != after.get("locations"):
        audit.log(
            db,
            entity_type="app_setting",
            entity_id=0,
            action="update_ytgenerering_map_layout",
            old_value={"key": allocation_helpers.YTGENERERING_MAP_LAYOUT_KEY, "count": len(before.get("locations") or [])},
            new_value={"key": allocation_helpers.YTGENERERING_MAP_LAYOUT_KEY, "count": len(after.get("locations") or [])},
            user_id=getattr(admin, "id", None),
            business_id=business_id,
        )
    db.commit()
    return allocation_helpers._ytgenerering_map_layout_with_options(
        db,
        admin,
        area_focus=bridge.normalize_process_area_focus(area_focus or ""),
        business_id=business_id,
        include_options=include_options,
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
        allocation_helpers._audit_allocation_event(
            db,
            user,
            action="upload_failed",
            payload=allocation_helpers._upload_failure_payload(
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
        allocation_helpers._audit_allocation_event(
            db,
            user,
            action="detect_failed",
            payload=allocation_helpers._upload_failure_payload(stage="detect", error_type=type(exc).__name__, message=str(exc)),
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
    allocation_helpers._assert_flow_allowed("observations-update", user, allocation_helpers._role_access_for_user(db, user))
    engine_module, _flows_module = bridge.require_available()
    area_focus = bridge.normalize_process_area_focus(area_focus)
    business_code = allocation_helpers._allocation_business_code(db, user, area_focus=area_focus)
    data_paths = bridge.business_allocation_data_paths(business_code)
    try:
        path = await bridge.save_upload(file)
    except Exception as exc:
        allocation_helpers._audit_allocation_event(
            db,
            user,
            action="upload_failed",
            payload=allocation_helpers._upload_failure_payload(
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
        allocation_helpers._audit_allocation_event(
            db,
            user,
            action="upload_failed",
            payload=allocation_helpers._upload_failure_payload(
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
    allocation_helpers._audit_allocation_event(
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
    allocation_helpers._assert_flow_allowed(flow_id, user, allocation_helpers._role_access_for_user(db, user))
    try:
        with start_span("allocation.flow.parse_upload", {"allocation.flow_id": flow_id}):
            form = await request.form()
            files, params, temp_paths = await bridge.form_to_flow_payload(form, cache_scope=allocation_helpers._upload_cache_scope(user))
            area_focus = bridge.normalize_process_area_focus(params.pop(bridge.PROCESS_AREA_FOCUS_PARAM, ""))
            add_span_attributes({
                "allocation.file_key_count": len(files),
                "allocation.param_key_count": len([key for key in params if not str(key).startswith("__")]),
                "allocation.area_focus": area_focus or "ALLT",
            })
    except Exception as exc:
        allocation_helpers._audit_allocation_event(
            db,
            user,
            action="upload_failed",
            payload=allocation_helpers._upload_failure_payload(
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
    flow_path = f"{allocation_helpers.ALLOCATION_FLOW_PATH_PREFIX}/{flow_id}"
    try:
        user_filter_profile = allocation_helpers._filter_profile_from_params_or_db(params, db, user)
        process_matrix = allocation_helpers._stored_process_matrix(db)
        if area_focus and not bridge.process_flow_visible(flow_id, area_focus, process_matrix):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Funktionen ar inte tillganglig for vald toggle")
        allocation_helpers._attach_required_session_artifacts(flow_id, params, user)
        default_max_csv_path = None
        business_code = allocation_helpers._allocation_business_code(db, user, area_focus=area_focus)
        add_span_attributes({"allocation.business_code": business_code})
        coredata_files = allocation_helpers._business_coredata_default_files(flow_id, files, business_code, db)
        if coredata_files:
            files = {**coredata_files, **files}
        source_map = bridge.api_source_map_for_user_profile(
            allocation_helpers.allocation_api_source_map(flow_id),
            flow_id,
            user_filter_profile,
        )
        if source_map:
            flow = bridge.public_registry()
            flow_by_id = {str(item.get("id") or ""): item for item in flow}
            required_keys = allocation_helpers._allocation_flow_required_file_keys(flow_by_id.get(flow_id))
            try:
                with start_span("allocation.flow.resolve_sources", {"allocation.flow_id": flow_id}):
                    source_resolution = allocation_helpers.resolve_sources(
                        source_map,
                        files,
                        required_keys=required_keys,
                        tenant=allocation_helpers._business_tenant_for_code(db, business_code),
                    )
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
            map_business_id = allocation_helpers._allocation_settings_business_id(db, user, area_focus)
            if area_focus:
                params[bridge.PROCESS_AREA_FOCUS_PARAM] = area_focus
            bridge.apply_ytgenerering_user_settings(params, user_filter_profile, area_focus=ytgenerering_focus)
            params["__ytgenerering_map_locations_json"] = json.dumps(
                allocation_helpers._stored_ytgenerering_map_rows(db, business_id=map_business_id),
                ensure_ascii=False,
            )
        if flow_id in allocation_helpers.BUSINESS_ARTICLE_MAX_FLOW_IDS and "max_csv" not in files:
            try:
                default_max_csv_path = bridge.business_article_max_path_for_flow(business_code)
            except FileNotFoundError as exc:
                raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        if default_max_csv_path is not None:
            with start_span("allocation.flow.engine_run", {"allocation.flow_id": flow_id, "allocation.default_max_csv": True}):
                result = await run_in_threadpool(
                    bridge.run_flow_handler,
                    flow_id,
                    files,
                    params,
                    default_max_csv_path=default_max_csv_path,
                )
        else:
            with start_span("allocation.flow.engine_run", {"allocation.flow_id": flow_id, "allocation.default_max_csv": False}):
                result = await run_in_threadpool(bridge.run_flow_handler, flow_id, files, params)
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
            bridge.SESSIONS[session_id]["owner"] = allocation_helpers._session_owner_payload(user)
        allocation_helpers._audit_allocation_event(
            db,
            user,
            action="flow_run",
            payload=allocation_helpers._flow_audit_payload(
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
        error_fields = allocation_helpers._exception_audit_fields(exc)
        allocation_helpers._audit_allocation_event(
            db,
            user,
            action="flow_failed",
            payload=allocation_helpers._flow_audit_payload(
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
        allocation_helpers._assert_session_allowed(req.session_id, user)
        return bridge.open_excel_result(req)


@router.get("/table-column/{session_id}/{key}/{column_index}")
def table_column(
    session_id: str,
    key: str,
    column_index: int,
    user: User = Depends(require_allocation_tools_user),
) -> dict:
    with start_span("allocation.table_column", {"allocation.column_index": column_index}):
        allocation_helpers._assert_session_allowed(session_id, user)
        return bridge.table_column_text(session_id, key, column_index)


@router.get("/download/{session_id}/{key}")
def download(
    session_id: str,
    key: str,
    user: User = Depends(require_allocation_tools_user),
):
    with start_span("allocation.download"):
        allocation_helpers._assert_session_allowed(session_id, user)
        return bridge.download_result(session_id, key)

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from .. import allocation_bridge as bridge
from ..deps import require_allocation_tools_user
from ..models import User
from ..user_access import can_use_allocation_process


router = APIRouter(
    prefix="/api/allokering",
    tags=["allokering"],
    dependencies=[Depends(require_allocation_tools_user)],
)

SELF_SERVICE_FLOW_IDS = {"eftersok", "split-values"}


def _flow_allowed_for_user(flow_id: str, user: User) -> bool:
    return can_use_allocation_process(user) or flow_id in SELF_SERVICE_FLOW_IDS


def _assert_flow_allowed(flow_id: str, user: User) -> None:
    if not _flow_allowed_for_user(flow_id, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Bearbeta kräver Super User")


@router.get("/health")
def health(_user: User = Depends(require_allocation_tools_user)) -> dict:
    try:
        engine_module, _flows_module = bridge.require_available()
    except Exception:
        return bridge.unavailable_detail()
    return {
        "available": True,
        "status": "ok",
        "version": getattr(engine_module, "APP_VERSION", ""),
        "title": getattr(engine_module, "APP_TITLE", "Allokering"),
        "backend_dir": str(bridge.warehouse_tools_dir()),
    }


@router.get("/flows")
def list_flows(user: User = Depends(require_allocation_tools_user)) -> dict:
    _engine_module, flows_module = bridge.require_available()
    flows = flows_module.public_registry()
    if not can_use_allocation_process(user):
        flows = [flow for flow in flows if flow.get("id") in SELF_SERVICE_FLOW_IDS]
    return {"flows": flows}


@router.get("/pool")
def list_pool(user: User = Depends(require_allocation_tools_user)) -> dict:
    _engine_module, flows_module = bridge.require_available()
    if not can_use_allocation_process(user):
        return {"pool": []}
    return {"pool": flows_module.public_pool()}


@router.post("/detect")
async def detect(
    file: UploadFile = File(...),
    _user: User = Depends(require_allocation_tools_user),
) -> dict:
    engine_module, _flows_module = bridge.require_available()
    path = await bridge.save_upload(file)
    try:
        file_type = engine_module.detect_file_type(str(path))
    except Exception:
        file_type = None
    finally:
        path.unlink(missing_ok=True)
    return {"file_type": file_type}


@router.post("/observations/update")
async def update_observations(
    file: UploadFile = File(...),
    user: User = Depends(require_allocation_tools_user),
) -> dict:
    _assert_flow_allowed("observations-update", user)
    engine_module, _flows_module = bridge.require_available()
    path = await bridge.save_upload(file)
    try:
        buffer_df = engine_module.read_table(str(path))
        result = engine_module.build_observations_update_result(buffer_df, push_to_github=True)
    finally:
        path.unlink(missing_ok=True)
    return {
        "new_rows": int(result.new_row_count),
        "article_max_rows": int(result.article_max_rows),
        "pushed_to_github": bool(result.pushed_to_github),
        "observations_path": result.observations_path,
        "article_max_path": result.article_max_path,
    }


@router.post("/flow/{flow_id}")
async def run_flow(
    flow_id: str,
    request: Request,
    user: User = Depends(require_allocation_tools_user),
) -> dict:
    _assert_flow_allowed(flow_id, user)
    form = await request.form()
    files, params, temp_paths = await bridge.form_to_flow_payload(form)
    try:
        return bridge.run_flow_handler(flow_id, files, params)
    finally:
        for path in temp_paths:
            path.unlink(missing_ok=True)


@router.post("/open-excel")
def open_excel(
    req: bridge.OpenAllocationExcelRequest,
    _user: User = Depends(require_allocation_tools_user),
) -> dict:
    return bridge.open_excel_result(req)


@router.get("/table-column/{session_id}/{key}/{column_index}")
def table_column(
    session_id: str,
    key: str,
    column_index: int,
    _user: User = Depends(require_allocation_tools_user),
) -> dict:
    return bridge.table_column_text(session_id, key, column_index)


@router.get("/download/{session_id}/{key}")
def download(
    session_id: str,
    key: str,
    _user: User = Depends(require_allocation_tools_user),
):
    return bridge.download_result(session_id, key)

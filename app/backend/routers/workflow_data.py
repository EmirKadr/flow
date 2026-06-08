from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from ..deps import get_current_user, get_db
from ..models import User
from ..settings_service import get_role_view_access
from ..user_access import can_access_view, can_use_allocation_process
from ..workflow_data import WorkflowDataError, allocation_api_source_map, fetch_source_to_temp, productivity_api_source_map


router = APIRouter(prefix="/api/workflow-data", tags=["workflow-data"])


class WorkflowSourceRequest(BaseModel):
    feature: str = Field(min_length=2, max_length=40)
    flow_id: str = Field(default="", max_length=80)
    source_key: str = Field(min_length=2, max_length=80)


def _assert_workflow_source_allowed(payload: WorkflowSourceRequest, user: User, db: Session) -> None:
    feature = payload.feature.strip().lower()
    source_key = payload.source_key.strip()
    access = get_role_view_access(db, business_id=getattr(user, "business_id", None))
    if feature == "allocation":
        if not can_use_allocation_process(user, access):
            raise HTTPException(status_code=403, detail="Bearbeta kräver behörighet")
        allowed = set(allocation_api_source_map(payload.flow_id).values())
        if source_key not in allowed:
            raise HTTPException(status_code=400, detail="API-källan hör inte till flödet.")
        return
    if feature == "productivity":
        if not can_access_view(user, access, "productivity", "view"):
            raise HTTPException(status_code=403, detail="Sidan kräver behörighet")
        allowed = set(productivity_api_source_map().values())
        if source_key not in allowed:
            raise HTTPException(status_code=400, detail="API-källan hör inte till flödet.")
        return
    raise HTTPException(status_code=400, detail="Okänd workflow-källa.")


@router.post("/source")
def workflow_source(
    payload: WorkflowSourceRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    _assert_workflow_source_allowed(payload, user, db)
    try:
        path, entry = fetch_source_to_temp(payload.source_key)
    except WorkflowDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    filename = f"{entry.key}.csv"
    return FileResponse(
        str(path),
        filename=filename,
        media_type="text/csv; charset=utf-8",
        headers={
            "X-Flow-Source-Key": entry.key,
            "X-Flow-Source-View": entry.view,
            "X-Flow-Source-Rows": str(entry.row_count),
        },
        background=BackgroundTask(lambda target: Path(str(target)).unlink(missing_ok=True), str(path)),
    )

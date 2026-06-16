from __future__ import annotations

import logging
from pathlib import Path
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from .. import audit
from ..deps import get_current_user, get_db
from ..models import Business, User
from ..observability import add_span_attributes, start_span
from ..settings_service import get_role_view_access
from ..user_access import can_access_view, can_use_allocation_process
from ..workflow_data import WorkflowDataError, allocation_api_source_map, fetch_source_to_temp, productivity_api_source_map


router = APIRouter(prefix="/api/workflow-data", tags=["workflow-data"])
logger = logging.getLogger(__name__)


class WorkflowSourceRequest(BaseModel):
    feature: str = Field(min_length=2, max_length=40)
    flow_id: str = Field(default="", max_length=80)
    source_key: str = Field(min_length=2, max_length=80)


def _clean_text(value: object, *, max_length: int = 240) -> str | None:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if not text:
        return None
    text = re.sub(r"[A-Za-z]:\\[^\s]+", "[path]", text)
    text = re.sub(r"/(?:[^/\s]+/){2,}[^\s]+", "[path]", text)
    return text[: max_length - 3] + "..." if len(text) > max_length else text


def _workflow_source_payload(
    payload: WorkflowSourceRequest,
    *,
    status_text: str,
    entry=None,
    error_type: str | None = None,
    status_code: int | None = None,
    message: str | None = None,
) -> dict:
    result = {
        "feature": _clean_text(payload.feature, max_length=40),
        "flow_id": _clean_text(payload.flow_id, max_length=80),
        "source_key": _clean_text(payload.source_key, max_length=80),
        "status": status_text,
    }
    if entry is not None:
        result["view"] = _clean_text(getattr(entry, "view", ""), max_length=120)
        result["row_count"] = int(getattr(entry, "row_count", 0) or 0)
    if error_type:
        result["error_type"] = _clean_text(error_type, max_length=120)
    if status_code is not None:
        result["status_code"] = int(status_code)
    if message:
        result["message"] = _clean_text(message, max_length=400)
    return {key: value for key, value in result.items() if value not in (None, "")}


def _audit_workflow_source(
    db: Session,
    user: User,
    *,
    action: str,
    payload: dict,
) -> None:
    audit.log_and_commit(
        db,
        entity_type="workflow_source",
        entity_id=0,
        action=action,
        old_value=None,
        new_value=payload,
        user_id=getattr(user, "id", None),
        business_id=getattr(user, "business_id", None),
        logger=logger,
        context=f"workflow source audit event action={action}",
    )


def _workflow_source_tenant(db: Session, user: User) -> str | None:
    business_id = getattr(user, "business_id", None)
    if business_id is None or not hasattr(db, "get"):
        return None
    business = db.get(Business, business_id)
    return getattr(business, "tenant", None) if business is not None else None


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
    with start_span(
        "workflow_data.source",
        {
            "workflow.feature": payload.feature,
            "workflow.flow_id": payload.flow_id,
            "workflow.source": payload.source_key,
        },
    ):
        _assert_workflow_source_allowed(payload, user, db)
        tenant = _workflow_source_tenant(db, user)
        try:
            if tenant:
                path, entry = fetch_source_to_temp(payload.source_key, tenant=tenant)
            else:
                path, entry = fetch_source_to_temp(payload.source_key)
        except WorkflowDataError as exc:
            add_span_attributes({"workflow.status": "error", "workflow.error_type": type(exc).__name__})
            _audit_workflow_source(
                db,
                user,
                action="source_fetch_failed",
                payload=_workflow_source_payload(
                    payload,
                    status_text="error",
                    error_type=type(exc).__name__,
                    status_code=exc.status_code,
                    message=str(exc),
                ),
            )
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        add_span_attributes({
            "workflow.status": "ok",
            "workflow.view": entry.view,
            "workflow.row_count": entry.row_count,
        })
        _audit_workflow_source(
            db,
            user,
            action="source_fetch",
            payload=_workflow_source_payload(payload, status_text="ok", entry=entry),
        )
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

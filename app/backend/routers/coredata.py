from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from .. import audit
from .. import allocation_bridge as bridge
from ..business_scope import DEFAULT_BUSINESS_CODE, normalize_business_code, user_business_id
from ..coredata_service import (
    CoreDataError,
    build_coredata_status,
    classify_coredata_file,
    find_coredata_file,
    save_coredata_file,
)
from ..deps import get_db, require_allocation_tools_user, require_view_access
from ..models import Business, User


router = APIRouter(prefix="/api/coredata", tags=["coredata"])
logger = logging.getLogger(__name__)
ARTICLE_MAX_FILE_TYPE = "article_max"
ARTICLE_MAX_PREFIXES = ("artikel_max", "article_max")


def _coredata_business_code(db: Session, user: User) -> str:
    try:
        business_id = user_business_id(db, user)
        business = db.get(Business, business_id) if business_id is not None else None
        return normalize_business_code(getattr(business, "code", None)) or DEFAULT_BUSINESS_CODE
    except Exception:
        return DEFAULT_BUSINESS_CODE


def _format_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} kB"
    return f"{size} B"


def _file_status_payload(*, key: str, label: str, prefix: str, path: Path | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "key": key,
        "label": label,
        "prefix": prefix,
        "uploaded": path is not None and path.is_file(),
        "name": None,
        "modified_at": None,
        "size": None,
        "size_label": None,
    }
    if path is None or not path.is_file():
        return payload
    stat = path.stat()
    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).astimezone()
    payload.update(
        {
            "name": path.name,
            "modified_at": modified.isoformat(timespec="seconds"),
            "size": stat.st_size,
            "size_label": _format_size(stat.st_size),
        }
    )
    return payload


def _article_max_path(business_code: str) -> Path:
    return Path(bridge.business_allocation_data_paths(business_code)["article_max_path"])


def _article_max_status(business_code: str) -> dict[str, Any]:
    try:
        path = _article_max_path(business_code)
    except Exception:
        path = None
    return _file_status_payload(
        key=ARTICLE_MAX_FILE_TYPE,
        label="artikel_max.csv",
        prefix="artikel_max",
        path=path,
    )


def _coredata_status(business_code: str) -> dict[str, Any]:
    payload = build_coredata_status(business_code=business_code)
    payload["files"] = {
        ARTICLE_MAX_FILE_TYPE: _article_max_status(business_code),
        **payload.get("files", {}),
    }
    return payload


def _classify_upload_file(filename: str | None) -> str | None:
    stem = Path(filename or "").stem.lower().replace("\ufeff", "").strip()
    if any(stem == prefix or re.match(rf"^{re.escape(prefix)}[-_.\s]", stem) for prefix in ARTICLE_MAX_PREFIXES):
        return ARTICLE_MAX_FILE_TYPE
    return classify_coredata_file(filename)


def _save_article_max_file(*, source_path: Path, filename: str | None, business_code: str) -> dict[str, Any]:
    final_path = _article_max_path(business_code)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = final_path.with_name(f".{final_path.name}.{os.getpid()}.tmp")
    shutil.copyfile(source_path, tmp_path)
    for path in final_path.parent.glob("*.csv"):
        stem = path.stem.lower()
        if any(stem == prefix or re.match(rf"^{re.escape(prefix)}[-_.\s]", stem) for prefix in ARTICLE_MAX_PREFIXES):
            path.unlink()
    tmp_path.replace(final_path)
    return _file_status_payload(
        key=ARTICLE_MAX_FILE_TYPE,
        label="artikel_max.csv",
        prefix="artikel_max",
        path=final_path,
    )


def _warm_coredata_caches(file_type: str, business_code: str) -> None:
    if file_type != "location":
        return
    try:
        _engine_module, flows_module = bridge.require_available()
        clear_cache = getattr(flows_module, "clear_prepared_location_cache", None)
        if callable(clear_cache):
            clear_cache()
        location_path = find_coredata_file("location", business_code=business_code)
        warm_cache = getattr(flows_module, "warm_prepared_locations", None)
        if callable(warm_cache):
            warm_cache(location_path)
    except Exception:
        logger.warning("Could not warm location coredata cache.", exc_info=True)


async def _save_raw_upload_temp(request: Request, filename: str | None) -> Path:
    suffix = Path(filename or "").suffix or ".csv"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        async for chunk in request.stream():
            if chunk:
                tmp.write(chunk)
    finally:
        tmp.close()
    return Path(tmp.name)


def _audit_coredata_file(
    db: Session,
    user: User,
    *,
    action: str,
    business_code: str,
    file_type: str | None = None,
    error_type: str | None = None,
    status_code: int | None = None,
) -> None:
    payload = {"business_code": business_code}
    if file_type:
        payload["file_type"] = file_type
    if error_type:
        payload["error_type"] = error_type
    if status_code is not None:
        payload["status_code"] = status_code
    audit.log_and_commit(
        db,
        entity_type="coredata_file",
        entity_id=0,
        action=action,
        old_value=None,
        new_value=payload,
        user_id=getattr(user, "id", None),
        logger=logger,
        context=f"coredata audit event action={action}",
    )


@router.get("/files")
def get_coredata_files(
    user: User = Depends(require_allocation_tools_user),
    db: Session = Depends(get_db),
) -> dict:
    business_code = _coredata_business_code(db, user)
    return _coredata_status(business_code)


@router.post("/files/raw")
async def upload_coredata_file_raw(
    request: Request,
    filename: str = Query(default=""),
    user: User = Depends(require_view_access("allocationUploads", "edit")),
    db: Session = Depends(get_db),
) -> dict:
    business_code = _coredata_business_code(db, user)
    file_type = _classify_upload_file(filename)
    if file_type is None:
        _audit_coredata_file(
            db,
            user,
            action="upload_rejected",
            business_code=business_code,
            error_type="unknown_file_type",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Okand karnfil")
    if file_type == "kpi":
        _audit_coredata_file(
            db,
            user,
            action="upload_rejected",
            business_code=business_code,
            file_type=file_type,
            error_type="productivity_kpi_route_required",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="KPI-mal laddas via Produktivitet")

    try:
        temp_path = await _save_raw_upload_temp(request, filename)
        try:
            if file_type == ARTICLE_MAX_FILE_TYPE:
                saved = _save_article_max_file(
                    source_path=temp_path,
                    filename=filename,
                    business_code=business_code,
                )
            else:
                saved = save_coredata_file(
                    source_path=temp_path,
                    filename=filename,
                    file_type=file_type,
                    business_code=business_code,
                )
        finally:
            temp_path.unlink(missing_ok=True)
    except CoreDataError as exc:
        _audit_coredata_file(
            db,
            user,
            action="upload_failed",
            business_code=business_code,
            file_type=file_type,
            error_type=type(exc).__name__,
            status_code=status.HTTP_400_BAD_REQUEST,
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        _audit_coredata_file(
            db,
            user,
            action="upload_failed",
            business_code=business_code,
            file_type=file_type,
            error_type=type(exc).__name__,
            status_code=getattr(exc, "status_code", None),
        )
        raise

    _warm_coredata_caches(file_type, business_code)
    _audit_coredata_file(db, user, action="upload", business_code=business_code, file_type=file_type)
    return {
        "saved": [saved],
        "unknown": [],
        "status": _coredata_status(business_code),
    }

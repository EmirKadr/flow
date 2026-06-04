from __future__ import annotations

import gzip
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import audit
from .. import allocation_bridge as bridge
from ..compiled_data_paths import article_max_path, legacy_article_max_path
from ..business_scope import DEFAULT_BUSINESS_CODE, normalize_business_code, user_business_id
from ..coredata_service import (
    CORE_DATA_SPEC_BY_KEY,
    CoreDataError,
    build_coredata_status,
    classify_coredata_file,
    find_coredata_file,
    save_coredata_file,
)
from ..deps import get_db, require_allocation_tools_user, require_view_access
from ..models import Business, User
from ..productivity_service import (
    COMPILED_PRODUCTIVITY_LOG_SPECS,
    build_productivity_compiled_data_status,
    productivity_compiled_log_path,
)


router = APIRouter(prefix="/api/coredata", tags=["coredata"])
logger = logging.getLogger(__name__)
ARTICLE_MAX_FILE_TYPE = "article_max"
ARTICLE_MAX_PREFIXES = ("artikel_max", "article_max")
CORE_DATA_PREVIEW_MAX_BYTES = 256 * 1024
COMPILED_PRODUCTIVITY_LOG_BY_KEY = {spec.key: spec for spec in COMPILED_PRODUCTIVITY_LOG_SPECS}


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


def _ensure_article_max_file(path: Path, business_code: str | None) -> Path:
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path = legacy_article_max_path(business_code)
    if legacy_path.exists() and legacy_path.resolve() != path.resolve():
        shutil.copy2(legacy_path, path)
        return path
    if normalize_business_code(business_code) == DEFAULT_BUSINESS_CODE:
        legacy_root_path = legacy_path.parent.parent / "artikel_max.csv"
        if legacy_root_path.exists() and legacy_root_path.resolve() != path.resolve():
            shutil.copy2(legacy_root_path, path)
            return path
    path.write_text("artikelnummer,max,pallid\n", encoding="utf-8-sig")
    return path


def _article_max_path(business_code: str) -> Path:
    return _ensure_article_max_file(article_max_path(business_code), business_code)


def _article_max_status(business_code: str) -> dict[str, Any]:
    try:
        path = _article_max_path(business_code)
    except Exception:
        path = None
    payload = _file_status_payload(
        key=ARTICLE_MAX_FILE_TYPE,
        label="artikel_max.csv",
        prefix="artikel_max",
        path=path,
    )
    payload["kind"] = "compiled_data"
    return payload


def _persistent_data_preview_path(file_key: str, business_code: str, db: Session | None = None) -> tuple[Path, dict[str, Any]]:
    if file_key == ARTICLE_MAX_FILE_TYPE:
        path = _article_max_path(business_code)
        return path, {
            "key": ARTICLE_MAX_FILE_TYPE,
            "label": "artikel_max.csv",
            "kind": "compiled_data",
        }

    productivity_spec = COMPILED_PRODUCTIVITY_LOG_BY_KEY.get(file_key)
    if productivity_spec is not None:
        path = productivity_compiled_log_path(productivity_spec.source_key, business_code=business_code)
        return path, {
            "key": productivity_spec.key,
            "label": productivity_spec.label,
            "kind": "compiled_data",
        }

    spec = CORE_DATA_SPEC_BY_KEY.get(file_key)
    if spec is None:
        raise CoreDataError("Okänd filtyp")
    return find_coredata_file(file_key, business_code=business_code, db=db), {
        "key": spec.key,
        "label": spec.label,
        "kind": "coredata",
    }


def _read_preview_bytes(path: Path, max_bytes: int = CORE_DATA_PREVIEW_MAX_BYTES) -> tuple[bytes, bool]:
    opener = gzip.open if path.name.lower().endswith(".gz") else open
    with opener(path, "rb") as handle:
        data = handle.read(max_bytes + 1)
    return data[:max_bytes], len(data) > max_bytes


def _decode_preview_text(data: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8-replace"


def _persistent_data_preview_payload(file_key: str, business_code: str, db: Session | None = None) -> dict[str, Any]:
    path, meta = _persistent_data_preview_path(file_key, business_code, db)
    if not path.is_file():
        raise CoreDataError("Filen hittades inte")
    stat = path.stat()
    preview_bytes, truncated = _read_preview_bytes(path)
    text, encoding = _decode_preview_text(preview_bytes)
    return {
        **meta,
        "name": path.name,
        "size": stat.st_size,
        "size_label": _format_size(stat.st_size),
        "encoding": encoding,
        "text": text,
        "truncated": truncated,
        "compressed": path.name.lower().endswith(".gz"),
        "max_bytes": CORE_DATA_PREVIEW_MAX_BYTES,
    }


def _coredata_status(business_code: str, db: Session | None = None) -> dict[str, Any]:
    payload = build_coredata_status(business_code=business_code, db=db)
    payload["files"] = {
        ARTICLE_MAX_FILE_TYPE: _article_max_status(business_code),
        **build_productivity_compiled_data_status(business_code=business_code),
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
    payload = _file_status_payload(
        key=ARTICLE_MAX_FILE_TYPE,
        label="artikel_max.csv",
        prefix="artikel_max",
        path=final_path,
    )
    payload["kind"] = "compiled_data"
    return payload


def _warm_coredata_caches(file_type: str, business_code: str, db: Session | None = None) -> None:
    if file_type != "location":
        return
    try:
        _engine_module, flows_module = bridge.require_available()
        clear_cache = getattr(flows_module, "clear_prepared_location_cache", None)
        if callable(clear_cache):
            clear_cache()
        location_path = find_coredata_file("location", business_code=business_code, db=db)
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
    return _coredata_status(business_code, db)


@router.get("/files/{file_key}/preview")
def preview_coredata_file(
    file_key: str,
    user: User = Depends(require_view_access("allocationUploads", "view")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    business_code = _coredata_business_code(db, user)
    try:
        return _persistent_data_preview_payload(file_key, business_code, db)
    except CoreDataError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Filen hittades inte.") from exc


@router.get("/files/{file_key}/download")
def download_coredata_file(
    file_key: str,
    user: User = Depends(require_view_access("allocationUploads", "view")),
    db: Session = Depends(get_db),
):
    business_code = _coredata_business_code(db, user)
    try:
        path, meta = _persistent_data_preview_path(file_key, business_code, db)
    except CoreDataError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Filen hittades inte.") from exc
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Filen hittades inte.")
    media_type = "application/gzip" if path.name.lower().endswith(".gz") else "text/csv"
    return FileResponse(path, media_type=media_type, filename=path.name or f"{meta.get('key') or file_key}.csv")


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
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Okänd kärnfil eller sammanställd datafil")
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
                    db=db,
                    uploaded_by=getattr(user, "id", None),
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

    _warm_coredata_caches(file_type, business_code, db)
    _audit_coredata_file(db, user, action="upload", business_code=business_code, file_type=file_type)
    return {
        "saved": [saved],
        "unknown": [],
        "status": _coredata_status(business_code, db),
    }

from datetime import date
import logging
import tempfile
from pathlib import Path
import re
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from .. import audit
from ..deps import get_db, require_view_access
from ..models import User
from ..productivity_service import (
    ProductivitySourceError,
    build_productivity_report_from_files,
    build_productivity_session_file_status,
    classify_productivity_file,
    clear_productivity_cache,
    clear_productivity_file,
    read_productivity_targets,
    save_productivity_file,
    source_files_from_session_logs,
)


router = APIRouter(prefix="/api/productivity", tags=["productivity"])
logger = logging.getLogger(__name__)

LOCAL_FILE_TYPES = {"pick", "trans", "pallet"}


def _session_upload_dir(request: Request) -> Path:
    upload_id = request.session.get("productivity_upload_id")
    if not upload_id:
        upload_id = uuid4().hex
        request.session["productivity_upload_id"] = upload_id
    target = Path(tempfile.gettempdir()) / "flow-productivity" / upload_id
    target.mkdir(parents=True, exist_ok=True)
    return target


def _session_log_files(request: Request) -> dict[str, Path]:
    raw = request.session.get("productivity_files") or {}
    files: dict[str, Path] = {}
    for key, value in raw.items():
        if key in LOCAL_FILE_TYPES and value:
            path = Path(str(value))
            if path.is_file():
                files[key] = path
    return files


def _safe_local_name(filename: str | None, file_type: str) -> str:
    original = Path(filename or f"{file_type}.csv").name
    suffix = Path(original).suffix.lower() or ".csv"
    if suffix != ".csv":
        suffix = ".csv"
    stem = Path(original).stem or file_type
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._-") or file_type
    return f"{file_type}-{safe[:110]}{suffix}"


def _save_session_log_file(
    *,
    request: Request,
    temp_path: Path,
    filename: str | None,
    file_type: str,
) -> dict:
    target_dir = _session_upload_dir(request)
    target_path = target_dir / _safe_local_name(filename, file_type)
    existing = request.session.get("productivity_files") or {}
    old_path = existing.get(file_type)
    if old_path:
        Path(str(old_path)).unlink(missing_ok=True)
    temp_path.replace(target_path)
    request.session["productivity_files"] = {**existing, file_type: str(target_path)}
    clear_productivity_cache()
    return {
        "key": file_type,
        "label": {
            "pick": "Plocklogg",
            "trans": "Translogg",
            "pallet": "Palllastningslogg",
        }.get(file_type, file_type),
        "visible": True,
        "name": target_path.name,
    }


async def _save_upload_temp(upload: UploadFile) -> tuple[Path, bytes]:
    suffix = Path(upload.filename or "").suffix or ".csv"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    sample = b""
    try:
        while chunk := await upload.read(1024 * 1024):
            if len(sample) < 8192:
                sample += chunk[: 8192 - len(sample)]
            tmp.write(chunk)
    finally:
        tmp.close()
    return Path(tmp.name), sample


async def _save_raw_upload_temp(request: Request, filename: str | None) -> tuple[Path, bytes]:
    suffix = Path(filename or "").suffix or ".csv"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    sample = b""
    try:
        async for chunk in request.stream():
            if not chunk:
                continue
            if len(sample) < 8192:
                sample += chunk[: 8192 - len(sample)]
            tmp.write(chunk)
    finally:
        tmp.close()
    return Path(tmp.name), sample


def _save_classified_productivity_file(
    *,
    request: Request,
    temp_path: Path,
    filename: str | None,
    sample: bytes,
) -> tuple[list[dict], list[str]]:
    file_type = classify_productivity_file(filename, sample)
    if file_type is None:
        return [], [filename or "okänd fil"]
    if file_type in LOCAL_FILE_TYPES:
        return [
            _save_session_log_file(
                request=request,
                temp_path=temp_path,
                filename=filename,
                file_type=file_type,
            )
        ], []
    return [
        save_productivity_file(
            source_path=temp_path,
            filename=filename,
            file_type=file_type,
        )
    ], []


def _saved_file_types(saved: list[dict]) -> list[str]:
    return sorted({str(item.get("key") or "") for item in saved if item.get("key")})


def _audit_productivity_files(
    db: Session,
    user: User,
    *,
    action: str,
    attempted_count: int | None = None,
    saved: list[dict] | None = None,
    unknown: list[str] | None = None,
    file_type: str | None = None,
    scope: str | None = None,
    error_type: str | None = None,
    status_code: int | None = None,
) -> None:
    payload = {
        "saved_types": _saved_file_types(saved or []),
        "saved_count": len(saved or []),
        "unknown_count": len(unknown or []),
    }
    if attempted_count is not None:
        payload["attempted_count"] = max(0, attempted_count)
    if file_type:
        payload["file_type"] = file_type
    if scope:
        payload["scope"] = scope
    if error_type:
        payload["error_type"] = error_type
    if status_code is not None:
        payload["status_code"] = status_code
    audit.log_and_commit(
        db,
        entity_type="productivity_file",
        entity_id=0,
        action=action,
        old_value=None,
        new_value=payload,
        user_id=getattr(user, "id", None),
        logger=logger,
        context=f"productivity audit event action={action}",
    )


@router.get("/files")
def get_productivity_files(
    request: Request,
    _: User = Depends(require_view_access("productivity", "view")),
) -> dict:
    return build_productivity_session_file_status(_session_log_files(request))


@router.get("/targets")
def get_productivity_targets(
    _: User = Depends(require_view_access("productivity", "view")),
) -> dict:
    try:
        return read_productivity_targets()
    except ProductivitySourceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte l\u00e4sa KPI-m\u00e5l: {exc}",
        ) from exc


@router.post("/files")
async def upload_productivity_files(
    request: Request,
    files: list[UploadFile] = File(...),
    user: User = Depends(require_view_access("productivity", "edit")),
    db: Session = Depends(get_db),
) -> dict:
    if not files:
        _audit_productivity_files(
            db,
            user,
            action="upload_failed",
            attempted_count=0,
            error_type="HTTPException",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Inga filer skickades")

    saved: list[dict] = []
    unknown: list[str] = []
    try:
        for upload in files:
            temp_path, sample = await _save_upload_temp(upload)
            try:
                saved_items, unknown_items = _save_classified_productivity_file(
                    request=request,
                    temp_path=temp_path,
                    filename=upload.filename,
                    sample=sample,
                )
                saved.extend(saved_items)
                unknown.extend(unknown_items)
            finally:
                temp_path.unlink(missing_ok=True)
    except Exception as exc:
        _audit_productivity_files(
            db,
            user,
            action="upload_failed",
            attempted_count=len(files),
            saved=saved,
            unknown=unknown,
            error_type=type(exc).__name__,
            status_code=getattr(exc, "status_code", None),
        )
        raise

    _audit_productivity_files(db, user, action="upload", attempted_count=len(files), saved=saved, unknown=unknown)
    return {
        "saved": saved,
        "unknown": unknown,
        "status": build_productivity_session_file_status(_session_log_files(request)),
    }


@router.post("/files/raw")
async def upload_productivity_file_raw(
    request: Request,
    filename: str = Query(default=""),
    user: User = Depends(require_view_access("productivity", "edit")),
    db: Session = Depends(get_db),
) -> dict:
    try:
        temp_path, sample = await _save_raw_upload_temp(request, filename)
        try:
            saved, unknown = _save_classified_productivity_file(
                request=request,
                temp_path=temp_path,
                filename=filename,
                sample=sample,
            )
        finally:
            temp_path.unlink(missing_ok=True)
    except Exception as exc:
        _audit_productivity_files(
            db,
            user,
            action="upload_failed",
            attempted_count=1,
            error_type=type(exc).__name__,
            status_code=getattr(exc, "status_code", None),
        )
        raise

    _audit_productivity_files(db, user, action="upload", attempted_count=1, saved=saved, unknown=unknown)
    return {
        "saved": saved,
        "unknown": unknown,
        "status": build_productivity_session_file_status(_session_log_files(request)),
    }


@router.delete("/files/{file_type}")
def delete_productivity_file(
    file_type: str,
    request: Request,
    user: User = Depends(require_view_access("productivity", "edit")),
    db: Session = Depends(get_db),
) -> dict:
    if file_type not in LOCAL_FILE_TYPES:
        try:
            clear_productivity_file(file_type)
        except ProductivitySourceError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        _audit_productivity_files(db, user, action="delete", file_type=file_type, scope="server")
        return build_productivity_session_file_status(_session_log_files(request))
    existing = request.session.get("productivity_files") or {}
    old_path = existing.pop(file_type, None)
    if old_path:
        Path(str(old_path)).unlink(missing_ok=True)
    request.session["productivity_files"] = existing
    clear_productivity_cache()
    _audit_productivity_files(db, user, action="delete", file_type=file_type, scope="session")
    return build_productivity_session_file_status(_session_log_files(request))


@router.get("")
def get_productivity(
    request: Request,
    date_filter: date | None = Query(default=None, alias="date"),
    _: User = Depends(require_view_access("productivity", "view")),
) -> dict:
    try:
        files = source_files_from_session_logs(_session_log_files(request))
        return build_productivity_report_from_files(files, report_date=date_filter)
    except ProductivitySourceError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte läsa produktivitetsunderlag: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte beräkna produktivitet: {exc}",
        ) from exc

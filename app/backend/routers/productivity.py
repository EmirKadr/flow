from datetime import date
import tempfile
from pathlib import Path
import re
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status

from ..deps import require_super_user
from ..models import User
from ..productivity_service import (
    ProductivitySourceError,
    build_productivity_report_from_files,
    build_productivity_session_file_status,
    classify_productivity_file,
    clear_productivity_cache,
    clear_productivity_file,
    save_productivity_file,
    source_files_from_session_logs,
)


router = APIRouter(prefix="/api/productivity", tags=["productivity"])

LOCAL_FILE_TYPES = {"pick", "trans", "pallet"}


def _session_upload_dir(request: Request) -> Path:
    upload_id = request.session.get("productivity_upload_id")
    if not upload_id:
        upload_id = uuid4().hex
        request.session["productivity_upload_id"] = upload_id
    target = Path(tempfile.gettempdir()) / "bemanning-productivity" / upload_id
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


@router.get("/files")
def get_productivity_files(
    request: Request,
    _: User = Depends(require_super_user),
) -> dict:
    return build_productivity_session_file_status(_session_log_files(request))


@router.post("/files")
async def upload_productivity_files(
    request: Request,
    files: list[UploadFile] = File(...),
    _: User = Depends(require_super_user),
) -> dict:
    if not files:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Inga filer skickades")

    saved: list[dict] = []
    unknown: list[str] = []
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

    return {
        "saved": saved,
        "unknown": unknown,
        "status": build_productivity_session_file_status(_session_log_files(request)),
    }


@router.post("/files/raw")
async def upload_productivity_file_raw(
    request: Request,
    filename: str = Query(default=""),
    _: User = Depends(require_super_user),
) -> dict:
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

    return {
        "saved": saved,
        "unknown": unknown,
        "status": build_productivity_session_file_status(_session_log_files(request)),
    }


@router.delete("/files/{file_type}")
def delete_productivity_file(
    file_type: str,
    request: Request,
    _: User = Depends(require_super_user),
) -> dict:
    if file_type not in LOCAL_FILE_TYPES:
        try:
            clear_productivity_file(file_type)
        except ProductivitySourceError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return build_productivity_session_file_status(_session_log_files(request))
    existing = request.session.get("productivity_files") or {}
    old_path = existing.pop(file_type, None)
    if old_path:
        Path(str(old_path)).unlink(missing_ok=True)
    request.session["productivity_files"] = existing
    clear_productivity_cache()
    return build_productivity_session_file_status(_session_log_files(request))


@router.get("")
def get_productivity(
    request: Request,
    date_filter: date | None = Query(default=None, alias="date"),
    _: User = Depends(require_super_user),
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

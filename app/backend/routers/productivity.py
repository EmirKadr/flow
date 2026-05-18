from datetime import date
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status

from ..deps import require_super_user
from ..models import User
from ..productivity_service import (
    ProductivitySourceError,
    build_productivity_file_status,
    build_productivity_report,
    classify_productivity_file,
    clear_productivity_file,
    save_productivity_file,
)


router = APIRouter(prefix="/api/productivity", tags=["productivity"])


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
    temp_path: Path,
    filename: str | None,
    sample: bytes,
) -> tuple[list[dict], list[str]]:
    file_type = classify_productivity_file(filename, sample)
    if file_type is None:
        return [], [filename or "okänd fil"]
    return [
        save_productivity_file(
            source_path=temp_path,
            filename=filename,
            file_type=file_type,
        )
    ], []


@router.get("/files")
def get_productivity_files(_: User = Depends(require_super_user)) -> dict:
    return build_productivity_file_status()


@router.post("/files")
async def upload_productivity_files(
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
        "status": build_productivity_file_status(),
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
            temp_path=temp_path,
            filename=filename,
            sample=sample,
        )
    finally:
        temp_path.unlink(missing_ok=True)

    return {
        "saved": saved,
        "unknown": unknown,
        "status": build_productivity_file_status(),
    }


@router.delete("/files/{file_type}")
def delete_productivity_file(
    file_type: str,
    _: User = Depends(require_super_user),
) -> dict:
    try:
        clear_productivity_file(file_type)
    except ProductivitySourceError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return build_productivity_file_status()


@router.get("")
def get_productivity(
    date_filter: date | None = Query(default=None, alias="date"),
    _: User = Depends(require_super_user),
) -> dict:
    try:
        return build_productivity_report(report_date=date_filter)
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

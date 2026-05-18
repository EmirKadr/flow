from datetime import date
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

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
            file_type = classify_productivity_file(upload.filename, sample)
            if file_type is None:
                unknown.append(upload.filename or "okänd fil")
                continue
            saved.append(
                save_productivity_file(
                    source_path=temp_path,
                    filename=upload.filename,
                    file_type=file_type,
                )
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

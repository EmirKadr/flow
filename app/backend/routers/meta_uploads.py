from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import logging
import mimetypes
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import threading
import time

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from openpyxl import Workbook
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from starlette.background import BackgroundTask

from ..audit import log as audit_log, log_and_commit as audit_log_and_commit
from ..config import settings
from ..deps import get_db, require_super_user
from ..media_store import get_media_store
from ..meta_analysis_service import (
    analyze_meta_upload,
    ensure_shipment_observations,
    meta_analysis_configured,
    refresh_record_hash,
    run_meta_analysis_background,
)
from ..models import MetaMediaUpload, MetaShipmentObservation, User


router = APIRouter(prefix="/api/meta", tags=["meta"])
logger = logging.getLogger(__name__)

UPLOAD_CHUNK_BYTES = 1024 * 1024
PUBLIC_UPLOAD_FAILURE_DETAIL = (
    "Uppladdningen misslyckades på servern. Försök igen eller dela upp videorna i färre filer."
)

# Enkel per-IP rate-limit (fast fönster) för den publika uppladdningsendpointen.
_RATE_LOCK = threading.Lock()
_RATE_HITS: dict[str, list[float]] = {}
META_PLAYABLE_TRANSCODE_LIMIT = 1
_PLAYABLE_TRANSCODE_SEMAPHORE = threading.BoundedSemaphore(META_PLAYABLE_TRANSCODE_LIMIT)


def _enforce_upload_rate_limit(request: Request) -> None:
    limit = int(settings.META_UPLOAD_RATE_LIMIT_PER_MINUTE or 0)
    if limit <= 0:
        return
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window_start = now - 60.0
    with _RATE_LOCK:
        hits = [ts for ts in _RATE_HITS.get(client, []) if ts >= window_start]
        if len(hits) >= limit:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail="För många uppladdningar. Vänta en stund och försök igen.",
            )
        hits.append(now)
        _RATE_HITS[client] = hits
        # Lätt städning så dicten inte växer obegränsat.
        if len(_RATE_HITS) > 2048:
            for key in [k for k, v in _RATE_HITS.items() if not any(ts >= window_start for ts in v)]:
                _RATE_HITS.pop(key, None)

IMAGE_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".gif",
    ".heic",
    ".heif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}
VIDEO_EXTENSIONS = {
    ".3g2",
    ".3gp",
    ".avi",
    ".m4v",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".webm",
}


def _clean_filename(filename: str | None) -> str:
    name = Path(str(filename or "media").replace("\\", "/")).name
    name = re.sub(r"[\r\n\t]+", " ", name).strip()
    return (name or "media")[:255]


def _media_type(filename: str, content_type: str | None) -> str:
    normalized_type = str(content_type or "").split(";", 1)[0].strip().lower()
    if normalized_type.startswith("image/"):
        return "image"
    if normalized_type.startswith("video/"):
        return "video"
    suffix = Path(filename).suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Bara bilder och videor kan laddas upp.")


def _safe_media_content_type(filename: str | None, content_type: str | None, media_type: str | None) -> str:
    normalized_type = str(content_type or "").split(";", 1)[0].strip().lower()
    expected_prefix = f"{media_type}/" if media_type in {"image", "video"} else ""
    if expected_prefix and normalized_type.startswith(expected_prefix):
        return normalized_type
    guessed = mimetypes.guess_type(_clean_filename(filename))[0]
    if guessed and expected_prefix and guessed.startswith(expected_prefix):
        return guessed
    if media_type == "video":
        return "video/mp4"
    if media_type == "image":
        return "image/jpeg"
    return normalized_type or "application/octet-stream"


def _imageio_ffmpeg_exe() -> str | None:
    try:
        import imageio_ffmpeg
    except Exception:
        return None
    try:
        return str(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        return None


def _resolve_ffmpeg() -> str | None:
    return shutil.which("ffmpeg") or _imageio_ffmpeg_exe()


def _format_size(bytes_count: int) -> str:
    if bytes_count >= 1024 * 1024:
        return f"{bytes_count / (1024 * 1024):.1f} MB"
    if bytes_count >= 1024:
        return f"{bytes_count / 1024:.1f} kB"
    return f"{bytes_count} B"


def _format_duration(seconds: float | int | None) -> str | None:
    if seconds is None:
        return None
    try:
        total = max(0, int(round(float(seconds))))
    except (TypeError, ValueError):
        return None
    minutes, sec = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes}:{sec:02d}"


def _public_upload_error_message(status_code: int) -> str:
    if status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE:
        return "Meta-uppladdningen var för stor."
    if status_code == status.HTTP_409_CONFLICT:
        return "Meta-uppladdningen stoppades av en dubblettkonflikt."
    if status_code == status.HTTP_400_BAD_REQUEST:
        return "Meta-uppladdningen kunde inte valideras."
    return "Meta-uppladdningen misslyckades på servern."


def _write_public_upload_failure_audit(
    db: Session,
    *,
    status_code: int,
    error_code: str,
    error_type: str,
    attempted_count: int,
    accepted_count: int,
    skipped_count: int,
    uploaded_bytes: int,
) -> None:
    payload: dict[str, Any] = {
        "path": "/api/meta/uploads",
        "method": "POST",
        "status_code": status_code,
        "error_code": error_code,
        "error_type": error_type,
        "message": _public_upload_error_message(status_code),
        "attempted_count": max(0, int(attempted_count or 0)),
        "accepted_count": max(0, int(accepted_count or 0)),
        "skipped_count": max(0, int(skipped_count or 0)),
        "uploaded_bytes": max(0, int(uploaded_bytes or 0)),
        "uploaded_size_label": _format_size(max(0, int(uploaded_bytes or 0))),
        "source": "public_upload",
    }
    try:
        db.rollback()
    except Exception:
        pass
    audit_log_and_commit(
        db,
        entity_type="meta_media_upload",
        entity_id=0,
        action="upload_failed",
        old_value=None,
        new_value=payload,
        user_id=None,
        business_id=None,
        logger=logger,
        context="public meta upload failure audit event",
    )


def _probe_video_duration_from_path(path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if result.returncode != 0:
            logger.info("Kunde inte läsa videolängd med ffprobe: %s", result.stderr[:200])
            return None
        duration = float(str(result.stdout or "").strip())
        return duration if duration > 0 else None
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        logger.info("Kunde inte läsa videolängd för meta-video: %s", exc)
        return None


def _stored_filename(uploaded_at: datetime, index: int, original_filename: str, media_type: str) -> str:
    suffix = Path(original_filename).suffix.lower()
    if suffix not in IMAGE_EXTENSIONS and suffix not in VIDEO_EXTENSIONS:
        suffix = ".mp4" if media_type == "video" else ".jpg"
    timestamp = uploaded_at.astimezone(timezone.utc).strftime("%Y%m%d_%H%M%S_%fZ")
    return f"{timestamp}_{index:02d}{suffix}"[:255]


def _media_upload_out(row: MetaMediaUpload) -> dict:
    return {
        "id": row.id,
        "batch_id": row.batch_id,
        "filename": row.stored_filename or row.original_filename,
        "stored_filename": row.stored_filename or row.original_filename,
        "original_filename": row.original_filename,
        "content_type": row.content_type,
        "media_type": row.media_type,
        "size_bytes": row.size_bytes,
        "size_label": _format_size(row.size_bytes),
        "duration_seconds": row.duration_seconds,
        "duration_label": _format_duration(row.duration_seconds),
        "content_hash": row.content_hash,
        "status": row.status,
        "source": row.source,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _media_upload_audit_snapshot(row: MetaMediaUpload) -> dict:
    return {
        "batch_id": row.batch_id,
        "filename": row.stored_filename or row.original_filename,
        "original_filename": row.original_filename,
        "content_type": row.content_type,
        "media_type": row.media_type,
        "size_bytes": row.size_bytes,
        "duration_seconds": row.duration_seconds,
        "content_hash": row.content_hash,
        "status": row.status,
        "source": row.source,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _shipment_observation_out(row: MetaShipmentObservation) -> dict:
    video_id = row.media_upload_id
    label_id = row.label_image_upload_id
    video = row.media_upload
    return {
        "id": row.id,
        "media_upload_id": video_id,
        "label_image_upload_id": label_id,
        "video_hash": row.video_hash,
        "label_image_hash": row.label_image_hash,
        "record_hash": row.record_hash,
        "order_number": row.order_number,
        "shipment_number": row.shipment_number,
        "username": row.username,
        "customer_name": row.customer_name,
        "pallet_id": row.pallet_id,
        "deviations": row.deviations or [],
        "uncertainty_notes": row.uncertainty_notes,
        "label_frame_time_seconds": row.label_frame_time_seconds,
        "analysis_status": row.analysis_status,
        "analysis_error": row.analysis_error,
        "llm_model": row.llm_model,
        "video_filename": (video.stored_filename or video.original_filename) if video else None,
        "video_original_filename": video.original_filename if video else None,
        "video_duration_seconds": video.duration_seconds if video else None,
        "video_duration_label": _format_duration(video.duration_seconds) if video else None,
        "video_size_bytes": video.size_bytes if video else None,
        "video_size_label": _format_size(video.size_bytes) if video else None,
        "video_url": f"/api/meta/uploads/{video_id}/content" if video_id else None,
        "label_still_url": f"/api/meta/uploads/{label_id}/content" if label_id else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


META_SHIPMENT_EXPORT_HEADERS = [
    "Ordernummer",
    "Sändningsnummer",
    "Användarnamn",
    "Kund",
    "Pall-ID",
    "Avvikelser",
    "Status",
    "Osäkerhet",
    "Uppdaterad",
    "Video",
    "Längd",
    "Storlek",
    "Etikett",
    "Rad-ID",
]


def _safe_excel_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, list):
        value = ", ".join(str(item) for item in value if str(item or "").strip())
    if isinstance(value, (int, float, datetime)):
        return value
    text = str(value)
    if text.startswith(("=", "+", "-", "@")):
        return f"'{text}"
    return text


def _shipment_export_row(row: MetaShipmentObservation) -> list[Any]:
    video = row.media_upload
    return [
        row.order_number,
        row.shipment_number,
        row.username,
        row.customer_name,
        row.pallet_id,
        row.deviations or [],
        row.analysis_status,
        row.uncertainty_notes,
        row.updated_at.isoformat(sep=" ", timespec="seconds") if row.updated_at else "",
        (video.stored_filename or video.original_filename) if video else "",
        _format_duration(video.duration_seconds) if video else "",
        _format_size(video.size_bytes) if video else "",
        "Finns" if row.label_image_upload_id else "",
        row.record_hash,
    ]


def _write_shipment_observations_excel(rows: list[MetaShipmentObservation]) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sändningsanalys"
    sheet.append(META_SHIPMENT_EXPORT_HEADERS)
    for row in rows:
        sheet.append([_safe_excel_value(value) for value in _shipment_export_row(row)])
    for column_cells in sheet.columns:
        max_length = max(len(str(cell.value or "")) for cell in column_cells)
        sheet.column_dimensions[column_cells[0].column_letter].width = min(max(12, max_length + 2), 42)
    fd, output_name = tempfile.mkstemp(prefix="flow_meta_sandningsanalys_", suffix=".xlsx")
    os.close(fd)
    output_path = Path(output_name)
    workbook.save(output_path)
    workbook.close()
    return output_path


def _parse_export_ids(raw_ids: str | None) -> list[int]:
    if not raw_ids:
        return []
    result: list[int] = []
    for part in raw_ids.split(","):
        text = part.strip()
        if not text:
            continue
        try:
            value = int(text)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Exporten innehåller ogiltiga rad-id:n.") from exc
        if value <= 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Exporten innehåller ogiltiga rad-id:n.")
        result.append(value)
    if len(result) > 500:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Du kan exportera max 500 filtrerade rader åt gången.")
    return result


async def _stream_upload_to_store(upload: UploadFile, *, store, batch_total: int):
    """Strömma en uppladdad fil direkt till MediaStore.

    Aldrig mer än en chunk i RAM. Returnerar (StoredObject, size). Gränser
    kontrolleras under strömningen så att en för stor fil avbryts tidigt.
    """
    max_file = int(settings.MAX_META_UPLOAD_FILE_BYTES)
    max_batch = int(settings.MAX_META_UPLOAD_BATCH_BYTES)
    suffix = Path(_clean_filename(upload.filename)).suffix.lower()
    writer = store.create_writer(suffix=suffix)
    size = 0
    try:
        while chunk := await upload.read(UPLOAD_CHUNK_BYTES):
            size += len(chunk)
            if size > max_file:
                raise HTTPException(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"{_clean_filename(upload.filename)} är större än {_format_size(max_file)}.",
                )
            if batch_total + size > max_batch:
                raise HTTPException(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Uppladdningen är större än {_format_size(max_batch)} totalt.",
                )
            writer.write(chunk)
    except BaseException:
        writer.abort()
        await upload.close()
        raise
    await upload.close()
    if size <= 0:
        writer.abort()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"{_clean_filename(upload.filename)} är tom.")
    return writer.commit(), size


@router.post("/uploads", status_code=status.HTTP_201_CREATED)
async def upload_meta_media(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> dict:
    _enforce_upload_rate_limit(request)
    store = get_media_store()
    max_files = int(settings.MAX_META_UPLOAD_FILES)
    attempted_count = len(files or [])
    batch_id = uuid4().hex
    batch_total = 0
    rows: list[MetaMediaUpload] = []
    saved: list[dict] = []
    skipped: list[dict] = []
    pending_hashes: dict[str, str] = {}

    try:
        if not files:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Inga filer skickades.")
        if len(files) > max_files:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Du kan ladda upp max {max_files} filer åt gången.",
            )

        for index, upload in enumerate(files, start=1):
            filename = _clean_filename(upload.filename)
            content_type = str(upload.content_type or "application/octet-stream").split(";", 1)[0].strip().lower()
            media_type = _media_type(filename, content_type)
            safe_content_type = _safe_media_content_type(filename, content_type, media_type)
            stored, size = await _stream_upload_to_store(upload, store=store, batch_total=batch_total)
            batch_total += size
            content_hash = stored.sha256
            pending_duplicate = pending_hashes.get(content_hash)
            if pending_duplicate:
                # Innehållet är redan lagrat under samma (hash-baserade) nyckel.
                skipped.append(
                    _duplicate_item(
                        filename=filename,
                        content_type=safe_content_type,
                        media_type=media_type,
                        size=size,
                        duplicate_of_id=None,
                        duplicate_of_filename=pending_duplicate,
                    )
                )
                continue
            existing = db.query(MetaMediaUpload).filter(MetaMediaUpload.content_hash == content_hash).first()
            if existing is not None:
                skipped.append(
                    _duplicate_item(
                        filename=filename,
                        content_type=safe_content_type,
                        media_type=media_type,
                        size=size,
                        duplicate_of_id=existing.id,
                        duplicate_of_filename=existing.stored_filename or existing.original_filename,
                    )
                )
                continue
            uploaded_at = datetime.now(timezone.utc)
            stored_filename = _stored_filename(uploaded_at, index, filename, media_type)
            pending_hashes[content_hash] = stored_filename
            duration_seconds = (
                _probe_video_duration_from_path(store.materialize_to_temp(stored.key))
                if media_type == "video"
                else None
            )
            row = MetaMediaUpload(
                batch_id=batch_id,
                original_filename=filename,
                stored_filename=stored_filename,
                content_type=safe_content_type,
                media_type=media_type,
                size_bytes=size,
                duration_seconds=duration_seconds,
                content_hash=content_hash,
                storage_backend=store.backend,
                storage_key=stored.key,
                status="pending_analysis",
                source="public_upload",
                created_at=uploaded_at,
            )
            rows.append(row)
            saved.append(
                {
                    "filename": stored_filename,
                    "stored_filename": stored_filename,
                    "original_filename": filename,
                    "content_type": safe_content_type,
                    "media_type": media_type,
                    "size_bytes": size,
                    "size_label": _format_size(size),
                    "duration_seconds": duration_seconds,
                    "duration_label": _format_duration(duration_seconds),
                }
            )

        if rows:
            db.add_all(rows)
            db.flush()  # tilldela id:n utan att ladda blobbar (ingen db.refresh på data)
            for row, item in zip(rows, saved):
                item["id"] = row.id
            shipment_rows = ensure_shipment_observations(db, rows)
            db.commit()
            if shipment_rows and meta_analysis_configured() and settings.META_ANALYSIS_AUTO_START:
                background_tasks.add_task(run_meta_analysis_background, [row.media_upload_id for row in shipment_rows])
        else:
            shipment_rows = []
    except HTTPException as exc:
        status_code = int(exc.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR)
        _write_public_upload_failure_audit(
            db,
            status_code=status_code,
            error_code=f"HTTP {status_code}",
            error_type="HTTPException",
            attempted_count=attempted_count,
            accepted_count=len(saved),
            skipped_count=len(skipped),
            uploaded_bytes=batch_total,
        )
        raise
    except IntegrityError as exc:
        _write_public_upload_failure_audit(
            db,
            status_code=status.HTTP_409_CONFLICT,
            error_code="HTTP 409",
            error_type=exc.__class__.__name__,
            attempted_count=attempted_count,
            accepted_count=len(saved),
            skipped_count=len(skipped),
            uploaded_bytes=batch_total,
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="En eller flera filer fanns redan och sparades inte dubbelt. Försök ladda upp igen om andra filer saknas.",
        ) from exc
    except Exception as exc:
        _write_public_upload_failure_audit(
            db,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="HTTP 500",
            error_type=exc.__class__.__name__,
            attempted_count=attempted_count,
            accepted_count=len(saved),
            skipped_count=len(skipped),
            uploaded_bytes=batch_total,
        )
        logger.exception("Public meta upload failed")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=PUBLIC_UPLOAD_FAILURE_DETAIL) from exc

    return {
        "batch_id": batch_id,
        "saved_count": len(saved),
        "skipped_count": len(skipped),
        "shipment_count": len(shipment_rows),
        "analysis_status": "queued" if shipment_rows and meta_analysis_configured() else "needs_configuration" if shipment_rows else None,
        "saved": saved,
        "skipped": skipped,
        "status": "pending_analysis",
    }


@router.get("/uploads")
def list_meta_media_uploads(
    limit: int = Query(200, ge=1, le=500),
    media_type: str | None = Query(None, pattern="^(image|video)$"),
    db: Session = Depends(get_db),
    _: User = Depends(require_super_user),
) -> dict:
    query = db.query(MetaMediaUpload)
    if media_type:
        query = query.filter(MetaMediaUpload.media_type == media_type)
    rows = (
        query.order_by(MetaMediaUpload.created_at.desc(), MetaMediaUpload.id.desc())
        .limit(limit)
        .all()
    )
    return {
        "count": len(rows),
        "items": [_media_upload_out(row) for row in rows],
    }


@router.get("/shipment-observations")
def list_meta_shipment_observations(
    limit: int = Query(200, ge=1, le=500),
    status_filter: str | None = Query(None, alias="status", max_length=40),
    db: Session = Depends(get_db),
    _: User = Depends(require_super_user),
) -> dict:
    query = db.query(MetaShipmentObservation).options(joinedload(MetaShipmentObservation.media_upload))
    if status_filter:
        query = query.filter(MetaShipmentObservation.analysis_status == status_filter)
    rows = (
        query.order_by(MetaShipmentObservation.updated_at.desc(), MetaShipmentObservation.id.desc())
        .limit(limit)
        .all()
    )
    return {
        "count": len(rows),
        "items": [_shipment_observation_out(row) for row in rows],
    }


@router.get("/shipment-observations/export")
def export_meta_shipment_observations(
    ids: str | None = Query(None, max_length=8000),
    limit: int = Query(5000, ge=1, le=10000),
    db: Session = Depends(get_db),
    _: User = Depends(require_super_user),
) -> FileResponse:
    export_ids = _parse_export_ids(ids)
    query = db.query(MetaShipmentObservation).options(joinedload(MetaShipmentObservation.media_upload))
    if export_ids:
        rows = query.filter(MetaShipmentObservation.id.in_(export_ids)).all()
        by_id = {int(row.id): row for row in rows}
        rows = [by_id[row_id] for row_id in export_ids if row_id in by_id]
        filename = "meta-sandningsanalys-filtrerad.xlsx"
    else:
        rows = (
            query.order_by(MetaShipmentObservation.updated_at.desc(), MetaShipmentObservation.id.desc())
            .limit(limit)
            .all()
        )
        filename = "meta-sandningsanalys.xlsx"
    output_path = _write_shipment_observations_excel(rows)
    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
        background=BackgroundTask(_cleanup_path, output_path),
    )


@router.post("/uploads/{upload_id}/analyze")
def analyze_meta_media_upload(
    upload_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_user),
) -> dict:
    upload = db.get(MetaMediaUpload, upload_id)
    if upload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Uppladdningen hittades inte.")
    if upload.media_type != "video":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Bara videor kan analyseras.")
    row = analyze_meta_upload(db, upload_id)
    return {
        "item": _shipment_observation_out(row),
        "status": row.analysis_status,
        "message": row.analysis_error,
    }


@router.delete("/uploads/{upload_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_meta_media_upload(
    upload_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_super_user),
) -> None:
    row = db.get(MetaMediaUpload, upload_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Uppladdningen hittades inte.")
    before = _media_upload_audit_snapshot(row)
    db.query(MetaShipmentObservation).filter(MetaShipmentObservation.media_upload_id == upload_id).delete(
        synchronize_session=False
    )
    label_refs = db.query(MetaShipmentObservation).filter(MetaShipmentObservation.label_image_upload_id == upload_id).all()
    for observation in label_refs:
        observation.label_image_upload_id = None
        observation.label_image_hash = None
        refresh_record_hash(observation)
    storage_key = row.storage_key
    db.delete(row)
    db.flush()
    # Radera bytena ur lagringen först när ingen annan rad delar samma
    # (innehållsadresserade) nyckel.
    if storage_key:
        still_referenced = (
            db.query(MetaMediaUpload.id)
            .filter(MetaMediaUpload.storage_key == storage_key)
            .first()
            is not None
        )
        if not still_referenced:
            get_media_store().delete(storage_key)
    audit_log(
        db,
        entity_type="meta_media_upload",
        entity_id=row.id,
        action="delete",
        old_value=before,
        new_value=None,
        user_id=user.id,
        business_id=None,
    )
    db.commit()


def _content_disposition(filename: str, *, attachment: bool = False) -> str:
    safe_filename = _clean_filename(filename)
    disposition = "attachment" if attachment else "inline"
    return f"{disposition}; filename*=UTF-8''{quote(safe_filename)}"


def _duplicate_item(
    *,
    filename: str,
    content_type: str,
    media_type: str,
    size: int,
    duplicate_of_id: int | None,
    duplicate_of_filename: str,
) -> dict:
    return {
        "filename": filename,
        "original_filename": filename,
        "content_type": content_type,
        "media_type": media_type,
        "size_bytes": size,
        "size_label": _format_size(size),
        "reason": "duplicate",
        "duplicate_of_id": duplicate_of_id,
        "duplicate_of_filename": duplicate_of_filename,
    }


def _cleanup_path(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.info("Could not remove temporary playable meta video %s", path)


def _transcode_video_to_playable(row: MetaMediaUpload) -> Path:
    ffmpeg = _resolve_ffmpeg()
    if not ffmpeg:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="ffmpeg saknas for spelbar video.")
    if not row.storage_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mediafilen saknar lagringsreferens.")
    source_path = get_media_store().materialize_to_temp(row.storage_key)
    fd, output_name = tempfile.mkstemp(prefix="flow_meta_playable_", suffix=".mp4")
    try:
        try:
            os.close(fd)
        except OSError:
            pass
        output_path = Path(output_name)
        output_path.unlink(missing_ok=True)
        command = [
            ffmpeg,
            "-y",
            "-i",
            str(source_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "24",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        completed = subprocess.run(command, capture_output=True, timeout=240, check=False)
        if completed.returncode != 0 or not output_path.exists() or output_path.stat().st_size <= 0:
            _cleanup_path(output_path)
            detail = (completed.stderr or b"").decode("utf-8", errors="replace")[:500]
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Kunde inte skapa spelbar video. {detail}".strip(),
            )
        return output_path
    except BaseException:
        try:
            Path(output_name).unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _transcode_video_to_playable_queued(row: MetaMediaUpload) -> Path:
    with _PLAYABLE_TRANSCODE_SEMAPHORE:
        return _transcode_video_to_playable(row)


def _playable_video_response(row: MetaMediaUpload, *, as_attachment: bool = False) -> Response:
    output_path = _transcode_video_to_playable_queued(row)
    filename = row.stored_filename or row.original_filename or f"meta-video-{row.id}.mp4"
    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=_clean_filename(filename),
        content_disposition_type="attachment" if as_attachment else "inline",
        background=BackgroundTask(_cleanup_path, output_path),
    )


def _media_headers(row: MetaMediaUpload, *, as_attachment: bool = False) -> tuple[str, dict[str, str], int]:
    filename = row.stored_filename or row.original_filename
    content_type = _safe_media_content_type(filename, row.content_type, row.media_type)
    base_headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": _content_disposition(filename, attachment=as_attachment),
    }

    # All media strömmas från MediaStore — hela filen hamnar aldrig i RAM.
    if not row.storage_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mediafilen saknar lagringsreferens.")
    store = get_media_store()
    stat = store.stat(row.storage_key)
    if stat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mediafilen hittades inte i lagringen.")
    base_headers["Content-Length"] = str(stat.size)
    return content_type, base_headers, stat.size


def _media_response(row: MetaMediaUpload, request: Request, *, as_attachment: bool = False) -> Response:
    content_type, base_headers, total = _media_headers(row, as_attachment=as_attachment)

    # All media strÃ¶mmas frÃ¥n MediaStore â€” hela filen hamnar aldrig i RAM.
    store = get_media_store()
    range_header = request.headers.get("range") or request.headers.get("Range") or ""
    match = re.match(r"bytes=(\d*)-(\d*)$", range_header.strip())
    if match and total:
        start, end = _resolve_range(match.groups(), total)
        if start is None:
            return Response(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                headers={**base_headers, "Content-Range": f"bytes */{total}"},
            )
        return StreamingResponse(
            store.open_range(row.storage_key, start, end),
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            media_type=content_type,
            headers={
                **base_headers,
                "Content-Range": f"bytes {start}-{end}/{total}",
                "Content-Length": str(end - start + 1),
            },
        )
    return StreamingResponse(
        store.open_all(row.storage_key),
        media_type=content_type,
        headers={**base_headers, "Content-Length": str(total)},
    )


def _meta_media_head_response(row: MetaMediaUpload, *, variant: str | None, as_attachment: bool = False) -> Response:
    if variant == "playable" and row.media_type == "video":
        if not _resolve_ffmpeg():
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="ffmpeg saknas for spelbar video.")
        filename = row.stored_filename or row.original_filename or f"meta-video-{row.id}.mp4"
        return Response(
            media_type="video/mp4",
            headers={
                "Accept-Ranges": "bytes",
                "Content-Disposition": _content_disposition(filename, attachment=as_attachment),
            },
        )
    content_type, headers, _total = _media_headers(row, as_attachment=as_attachment)
    return Response(media_type=content_type, headers=headers)


def _resolve_range(groups: tuple[str, str], total: int) -> tuple[int | None, int | None]:
    start_text, end_text = groups
    if not start_text and end_text:
        length = min(int(end_text), total)
        start = total - length
        end = total - 1
    else:
        start = int(start_text or 0)
        end = int(end_text) if end_text else total - 1
        end = min(end, total - 1)
    if start > end or start >= total:
        return None, None
    return start, end


@router.head("/uploads/{upload_id}/content")
def head_meta_media_content(
    upload_id: int,
    variant: str | None = Query(None, pattern="^(original|playable)$"),
    download: bool = Query(False),
    db: Session = Depends(get_db),
    _: User = Depends(require_super_user),
) -> Response:
    row = db.get(MetaMediaUpload, upload_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Uppladdningen hittades inte.")
    return _meta_media_head_response(row, variant=variant, as_attachment=download)


@router.get("/uploads/{upload_id}/content")
def get_meta_media_content(
    upload_id: int,
    request: Request,
    variant: str | None = Query(None, pattern="^(original|playable)$"),
    download: bool = Query(False),
    db: Session = Depends(get_db),
    _: User = Depends(require_super_user),
) -> Response:
    row = db.get(MetaMediaUpload, upload_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Uppladdningen hittades inte.")
    if variant == "playable" and row.media_type == "video":
        return _playable_video_response(row, as_attachment=download)
    return _media_response(row, request, as_attachment=download)

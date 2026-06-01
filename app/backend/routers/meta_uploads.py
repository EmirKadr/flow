from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from ..audit import log as audit_log, log_and_commit as audit_log_and_commit
from ..config import settings
from ..deps import get_db, require_super_user
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

MAX_META_UPLOAD_FILES = 25
MAX_META_UPLOAD_FILE_BYTES = 256 * 1024 * 1024
MAX_META_UPLOAD_BATCH_BYTES = 1024 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024
PUBLIC_UPLOAD_FAILURE_DETAIL = (
    "Uppladdningen misslyckades på servern. Försök igen eller dela upp videorna i färre filer."
)

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


def _probe_video_duration_seconds(data: bytes, original_filename: str) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not data:
        return None
    suffix = Path(original_filename).suffix.lower()
    if suffix not in VIDEO_EXTENSIONS:
        suffix = ".mp4"
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(data)
            temp_path = temp_file.name
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                temp_path,
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
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass


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
        "video_size_label": _format_size(video.size_bytes) if video else None,
        "video_url": f"/api/meta/uploads/{video_id}/content" if video_id else None,
        "label_still_url": f"/api/meta/uploads/{label_id}/content" if label_id else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def _read_upload_data(upload: UploadFile, *, batch_total: int) -> tuple[bytes, int]:
    chunks: list[bytes] = []
    size = 0
    try:
        while chunk := await upload.read(UPLOAD_CHUNK_BYTES):
            size += len(chunk)
            if size > MAX_META_UPLOAD_FILE_BYTES:
                raise HTTPException(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"{_clean_filename(upload.filename)} är större än {_format_size(MAX_META_UPLOAD_FILE_BYTES)}.",
                )
            if batch_total + size > MAX_META_UPLOAD_BATCH_BYTES:
                raise HTTPException(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Uppladdningen är större än {_format_size(MAX_META_UPLOAD_BATCH_BYTES)} totalt.",
                )
            chunks.append(chunk)
    finally:
        await upload.close()
    if size <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"{_clean_filename(upload.filename)} är tom.")
    return b"".join(chunks), size


@router.post("/uploads", status_code=status.HTTP_201_CREATED)
async def upload_meta_media(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> dict:
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
        if len(files) > MAX_META_UPLOAD_FILES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Du kan ladda upp max {MAX_META_UPLOAD_FILES} filer åt gången.",
            )

        for index, upload in enumerate(files, start=1):
            filename = _clean_filename(upload.filename)
            content_type = str(upload.content_type or "application/octet-stream").split(";", 1)[0].strip().lower()
            media_type = _media_type(filename, content_type)
            data, size = await _read_upload_data(upload, batch_total=batch_total)
            batch_total += size
            content_hash = hashlib.sha256(data).hexdigest()
            pending_duplicate = pending_hashes.get(content_hash)
            if pending_duplicate:
                skipped.append(
                    _duplicate_item(
                        filename=filename,
                        content_type=content_type or "application/octet-stream",
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
                        content_type=content_type or "application/octet-stream",
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
            row = MetaMediaUpload(
                batch_id=batch_id,
                original_filename=filename,
                stored_filename=stored_filename,
                content_type=content_type or "application/octet-stream",
                media_type=media_type,
                size_bytes=size,
                duration_seconds=_probe_video_duration_seconds(data, filename) if media_type == "video" else None,
                content_hash=content_hash,
                data=data,
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
                    "content_type": row.content_type,
                    "media_type": media_type,
                    "size_bytes": size,
                    "size_label": _format_size(size),
                    "duration_seconds": row.duration_seconds,
                    "duration_label": _format_duration(row.duration_seconds),
                }
            )

        if rows:
            db.add_all(rows)
            db.commit()

            for row, item in zip(rows, saved):
                db.refresh(row)
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
    db.delete(row)
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


def _content_disposition(filename: str) -> str:
    safe_filename = _clean_filename(filename)
    return f"inline; filename*=UTF-8''{quote(safe_filename)}"


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


def _media_response(row: MetaMediaUpload, request: Request) -> Response:
    data = row.data or b""
    total = len(data)
    filename = row.stored_filename or row.original_filename
    base_headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": _content_disposition(filename),
    }
    range_header = request.headers.get("range") or request.headers.get("Range") or ""
    match = re.match(r"bytes=(\d*)-(\d*)$", range_header.strip())
    if match and total:
        start_text, end_text = match.groups()
        if not start_text and end_text:
            length = min(int(end_text), total)
            start = total - length
            end = total - 1
        else:
            start = int(start_text or 0)
            end = int(end_text) if end_text else total - 1
            end = min(end, total - 1)
        if start > end or start >= total:
            return Response(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                headers={**base_headers, "Content-Range": f"bytes */{total}"},
            )
        chunk = data[start : end + 1]
        headers = {
            **base_headers,
            "Content-Range": f"bytes {start}-{end}/{total}",
            "Content-Length": str(len(chunk)),
        }
        return Response(content=chunk, status_code=status.HTTP_206_PARTIAL_CONTENT, media_type=row.content_type, headers=headers)

    return Response(
        content=data,
        media_type=row.content_type,
        headers={**base_headers, "Content-Length": str(total)},
    )


@router.get("/uploads/{upload_id}/content")
def get_meta_media_content(
    upload_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_user),
) -> Response:
    row = db.get(MetaMediaUpload, upload_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Uppladdningen hittades inte.")
    return _media_response(row, request)

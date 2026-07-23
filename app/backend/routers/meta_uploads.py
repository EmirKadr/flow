from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4

import time

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from starlette.background import BackgroundTask

from ..audit import log as audit_log
from ..config import settings
from ..deps import get_db, require_super_user
from ..media_store import get_media_store
from ..meta_analysis_service import (
    analyze_meta_upload,
    ensure_shipment_observations,
    extract_audio_file,
    MetaAnalysisFailed,
    meta_analysis_configured,
    refresh_record_hash,
    run_meta_analysis_background,
)
from ..models import MetaMediaUpload, MetaShipmentObservation, User
from ..observability import add_span_attributes, emit_flow_event, start_span


from .meta_uploads_helpers import (  # noqa: F401
    UPLOAD_CHUNK_BYTES,
    PUBLIC_UPLOAD_FAILURE_DETAIL,
    _RATE_LOCK,
    _RATE_HITS,
    _enforce_upload_rate_limit,
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    _clean_filename,
    _media_type,
    _safe_media_content_type,
    _imageio_ffmpeg_exe,
    _resolve_ffmpeg,
    _format_size,
    _format_duration,
    _public_upload_error_message,
    _write_public_upload_failure_audit,
    _write_public_upload_success_audit,
    _probe_video_duration_from_path,
    _stored_filename,
    _media_upload_out,
    _media_upload_audit_snapshot,
    _shipment_observation_out,
    META_SHIPMENT_EXPORT_HEADERS,
    _safe_excel_value,
    _shipment_export_row,
    _write_shipment_observations_excel,
    _parse_export_ids,
    _stream_upload_to_store,
    _content_disposition,
    _duplicate_item,
    _cleanup_path,
    _media_headers,
    _media_response,
    _meta_media_head_response,
    _resolve_range,
)

router = APIRouter(prefix="/api/meta", tags=["meta"])
logger = logging.getLogger(__name__)

# Statusar en Super User får sätta manuellt på en sändningsrad. Speglar
# SHIPMENT_STATUS_LABELS i app/frontend/js/meta.js — håll dem i synk.
EDITABLE_SHIPMENT_STATUSES = frozenset(
    {
        "pending_analysis",
        "needs_configuration",
        "queued",
        "analyzing",
        "analyzed",
        "manual_review",
        "analysis_failed",
    }
)


class ShipmentStatusUpdate(BaseModel):
    status: str


class ShipmentDispatchLookupUpdate(BaseModel):
    matched: bool = False
    order_number: str | None = None
    shipment_number: str | None = None
    username: str | None = None
    customer_name: str | None = None
    note: str | None = None
    source: str | None = None


class ShipmentLocalAnalysisUpdate(BaseModel):
    pallet_id: str | None = None
    deviations: list[str] = Field(default_factory=list)
    uncertainty_notes: str | None = None
    llm_model: str = "gpt-4o-transcribe + gpt-4o-mini"


DISPATCH_LOOKUP_NOTE_PREFIXES = (
    "Dispatchpallar kunde inte hamtas fran ASK",
    "Dispatchpallar och Plocklogg Full kunde inte hamtas fran ASK",
    "Dispatchpallar (inklusive arkivet) gav ingen traff",
    "Plocklogg Full kunde inte hamtas fran ASK",
    "Plocklogg Full (inklusive arkivet) gav ingen traff",
    "Plocklogg Full saknade anvandarnamn",
    "Extern datakalla ar inte konfigurerad, sa Dispatchpallar",
)


def _clean_dispatch_lookup_text(value: object, max_length: int) -> str | None:
    text = str(value or "").strip()
    return text[:max_length] if text else None


def _split_uncertainty_notes(notes: str | None) -> list[str]:
    return [part.strip() for part in str(notes or "").split(";") if part.strip()]


def _remove_dispatch_lookup_notes(notes: str | None) -> str | None:
    kept = [
        part
        for part in _split_uncertainty_notes(notes)
        if not any(part.startswith(prefix) for prefix in DISPATCH_LOOKUP_NOTE_PREFIXES)
    ]
    return "; ".join(kept)[:2000] or None


def _append_dispatch_lookup_note(existing: str | None, note: str | None) -> str | None:
    cleaned_note = _clean_dispatch_lookup_text(note, 2000)
    if not cleaned_note:
        return existing
    parts = _split_uncertainty_notes(existing)
    if cleaned_note not in parts:
        parts.append(cleaned_note)
    return "; ".join(parts)[:2000] or None


def _shipment_dispatch_lookup_audit_snapshot(row: MetaShipmentObservation) -> dict:
    return {
        "analysis_status": row.analysis_status,
        "order_number": row.order_number,
        "shipment_number": row.shipment_number,
        "username": row.username,
        "customer_name": row.customer_name,
        "pallet_id": row.pallet_id,
        "has_uncertainty_notes": bool(row.uncertainty_notes),
    }

@router.post("/uploads", status_code=status.HTTP_201_CREATED)
async def upload_meta_media(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> dict:
    operation_started = time.perf_counter()
    max_files = int(settings.MAX_META_UPLOAD_FILES)
    attempted_count = len(files or [])
    batch_id = uuid4().hex
    batch_total = 0
    rows: list[MetaMediaUpload] = []
    saved: list[dict] = []
    skipped: list[dict] = []
    pending_hashes: dict[str, str] = {}
    analysis_status: str | None = None

    try:
        _enforce_upload_rate_limit(request)
        store = get_media_store()
        add_span_attributes({
            "meta.attempted_count": attempted_count,
            "meta.max_files": max_files,
        })
        emit_flow_event(
            "flow.meta.upload",
            feature="meta",
            outcome="started",
            event_alias="meta_upload",
            logger_=logger,
            attributes={
                "attempted_count": attempted_count,
                "max_files": max_files,
            },
            message=f"Meta-uppladdning startad med {attempted_count} filer.",
        )
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
                # ffprobe (subprocess, 20s-tak) är den värsta blockeraren på
                # event-loopen i denna async-route -> kör i tråd.
                await asyncio.to_thread(
                    _probe_video_duration_from_path, store.materialize_to_temp(stored.key)
                )
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
        analysis_status = "queued" if shipment_rows and meta_analysis_configured() else "needs_configuration" if shipment_rows else None
        add_span_attributes({
            "meta.status": "ok",
            "meta.saved_count": len(saved),
            "meta.skipped_count": len(skipped),
            "meta.shipment_count": len(shipment_rows),
            "meta.uploaded_bytes": batch_total,
            "meta.analysis_status": analysis_status or "",
        })
        _write_public_upload_success_audit(
            db,
            batch_id=batch_id,
            attempted_count=attempted_count,
            saved_count=len(saved),
            skipped_count=len(skipped),
            shipment_count=len(shipment_rows),
            uploaded_bytes=batch_total,
            media_types=[str(item.get("media_type") or "") for item in saved + skipped],
            analysis_status=analysis_status,
        )
        emit_flow_event(
            "flow.meta.upload",
            feature="meta",
            outcome="ok",
            event_alias="meta_upload",
            logger_=logger,
            attributes={
                "attempted_count": attempted_count,
                "saved_count": len(saved),
                "skipped_count": len(skipped),
                "shipment_count": len(shipment_rows),
                "uploaded_bytes": batch_total,
                "analysis_status": analysis_status or "",
                "duration_ms": round((time.perf_counter() - operation_started) * 1000, 2),
            },
            message=(
                "Meta-uppladdning klar: "
                f"{len(saved)} sparade, {len(skipped)} hoppade over, {len(shipment_rows)} sandningar."
            ),
        )
    except HTTPException as exc:
        status_code = int(exc.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR)
        add_span_attributes({"meta.status": "error", "meta.error_type": "HTTPException", "meta.status_code": status_code})
        emit_flow_event(
            "flow.meta.upload",
            feature="meta",
            outcome="blocked" if status_code < 500 else "failed",
            level=logging.WARNING if status_code < 500 else logging.ERROR,
            event_alias="meta_upload",
            logger_=logger,
            attributes={
                "attempted_count": attempted_count,
                "saved_count": len(saved),
                "skipped_count": len(skipped),
                "uploaded_bytes": batch_total,
                "http_status_code": status_code,
                "error.type": "HTTPException",
                "duration_ms": round((time.perf_counter() - operation_started) * 1000, 2),
            },
            message=f"Meta-uppladdning stoppad med HTTP {status_code}.",
        )
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
        add_span_attributes({"meta.status": "error", "meta.error_type": exc.__class__.__name__, "meta.status_code": status.HTTP_409_CONFLICT})
        emit_flow_event(
            "flow.meta.upload",
            feature="meta",
            outcome="blocked",
            level=logging.WARNING,
            event_alias="meta_upload",
            logger_=logger,
            attributes={
                "attempted_count": attempted_count,
                "saved_count": len(saved),
                "skipped_count": len(skipped),
                "uploaded_bytes": batch_total,
                "http_status_code": status.HTTP_409_CONFLICT,
                "error.type": exc.__class__.__name__,
                "duration_ms": round((time.perf_counter() - operation_started) * 1000, 2),
            },
            message="Meta-uppladdning stoppad av dubbelt innehall.",
        )
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
        add_span_attributes({"meta.status": "error", "meta.error_type": exc.__class__.__name__, "meta.status_code": status.HTTP_500_INTERNAL_SERVER_ERROR})
        emit_flow_event(
            "flow.meta.upload",
            feature="meta",
            outcome="failed",
            level=logging.ERROR,
            event_alias="meta_upload",
            logger_=logger,
            attributes={
                "attempted_count": attempted_count,
                "saved_count": len(saved),
                "skipped_count": len(skipped),
                "uploaded_bytes": batch_total,
                "http_status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "error.type": exc.__class__.__name__,
                "duration_ms": round((time.perf_counter() - operation_started) * 1000, 2),
            },
            exc_info=True,
            message="Meta-uppladdning misslyckades.",
        )
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
        "analysis_status": analysis_status,
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
    with start_span("meta.shipment_observations.export", {"meta.filtered": bool(ids)}):
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
        add_span_attributes({"meta.row_count": len(rows)})
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
    operation_started = time.perf_counter()
    upload = db.get(MetaMediaUpload, upload_id)
    if upload is None:
        emit_flow_event(
            "flow.meta.analyze",
            feature="meta",
            outcome="blocked",
            level=logging.WARNING,
            event_alias="meta_analyze",
            logger_=logger,
            attributes={
                "upload_id": upload_id,
                "http_status_code": status.HTTP_404_NOT_FOUND,
                "error.type": "HTTPException",
                "duration_ms": round((time.perf_counter() - operation_started) * 1000, 2),
            },
            message="Meta-analys stoppad: uppladdningen hittades inte.",
        )
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Uppladdningen hittades inte.")
    if upload.media_type != "video":
        emit_flow_event(
            "flow.meta.analyze",
            feature="meta",
            outcome="blocked",
            level=logging.WARNING,
            event_alias="meta_analyze",
            logger_=logger,
            attributes={
                "upload_id": upload_id,
                "http_status_code": status.HTTP_400_BAD_REQUEST,
                "error.type": "HTTPException",
                "duration_ms": round((time.perf_counter() - operation_started) * 1000, 2),
            },
            message="Meta-analys stoppad: endast videor kan analyseras.",
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Bara videor kan analyseras.")
    try:
        with start_span("meta.upload.analyze", {"meta.upload_id": upload_id, "meta.media_type": upload.media_type}):
            row = analyze_meta_upload(db, upload_id)
            add_span_attributes({"meta.analysis_status": row.analysis_status or ""})
    except HTTPException as exc:
        status_code = int(exc.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR)
        emit_flow_event(
            "flow.meta.analyze",
            feature="meta",
            outcome="blocked" if status_code < 500 else "failed",
            level=logging.WARNING if status_code < 500 else logging.ERROR,
            event_alias="meta_analyze",
            logger_=logger,
            attributes={
                "upload_id": upload_id,
                "http_status_code": status_code,
                "error.type": "HTTPException",
                "duration_ms": round((time.perf_counter() - operation_started) * 1000, 2),
            },
            message=f"Meta-analys stoppad med HTTP {status_code}.",
        )
        raise
    except Exception as exc:
        emit_flow_event(
            "flow.meta.analyze",
            feature="meta",
            outcome="failed",
            level=logging.ERROR,
            event_alias="meta_analyze",
            logger_=logger,
            attributes={
                "upload_id": upload_id,
                "http_status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "error.type": exc.__class__.__name__,
                "duration_ms": round((time.perf_counter() - operation_started) * 1000, 2),
            },
            exc_info=True,
            message="Meta-analys misslyckades.",
        )
        raise
    outcome = "failed" if row.analysis_status == "analysis_failed" else "blocked" if row.analysis_status == "needs_configuration" else "ok"
    emit_flow_event(
        "flow.meta.analyze",
        feature="meta",
        outcome=outcome,
        level=logging.ERROR if outcome == "failed" else logging.WARNING if outcome == "blocked" else logging.INFO,
        event_alias="meta_analyze",
        logger_=logger,
        attributes={
            "upload_id": upload_id,
            "analysis_status": row.analysis_status or "",
            "duration_ms": round((time.perf_counter() - operation_started) * 1000, 2),
        },
        message=f"Meta-analys klar med status {row.analysis_status or 'ok'}.",
    )
    return {
        "item": _shipment_observation_out(row),
        "status": row.analysis_status,
        "message": row.analysis_error,
    }


@router.patch("/shipment-observations/{observation_id}/status")
def update_meta_shipment_status(
    observation_id: int,
    payload: ShipmentStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_super_user),
) -> dict:
    row = db.get(MetaShipmentObservation, observation_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Sändningsraden hittades inte.")
    new_status = (payload.status or "").strip()
    if new_status not in EDITABLE_SHIPMENT_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ogiltig status.")
    old_status = row.analysis_status
    if new_status != old_status:
        row.analysis_status = new_status
        db.flush()
        audit_log(
            db,
            entity_type="meta_shipment_observation",
            entity_id=row.id,
            action="update_status",
            old_value={"analysis_status": old_status},
            new_value={"analysis_status": new_status},
            user_id=user.id,
            business_id=None,
        )
        db.commit()
        db.refresh(row)
    return {
        "item": _shipment_observation_out(row),
        "status": row.analysis_status,
    }


@router.patch("/shipment-observations/{observation_id}/local-analysis")
def update_meta_shipment_local_analysis(
    observation_id: int,
    payload: ShipmentLocalAnalysisUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_super_user),
) -> dict:
    row = db.get(MetaShipmentObservation, observation_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Sändningsraden hittades inte.")
    old_status = row.analysis_status
    pallet_id = _clean_dispatch_lookup_text(payload.pallet_id, 120)
    deviations = [str(value).strip()[:500] for value in payload.deviations if str(value or "").strip()][:100]
    uncertainty_notes = _clean_dispatch_lookup_text(payload.uncertainty_notes, 2000)
    row.pallet_id = pallet_id
    row.deviations = deviations
    row.uncertainty_notes = uncertainty_notes
    row.llm_model = _clean_dispatch_lookup_text(payload.llm_model, 120)
    row.llm_raw_response = {
        "source": "local_cli",
        "has_pallet_id": bool(pallet_id),
        "deviation_count": len(deviations),
        "has_uncertainty_notes": bool(uncertainty_notes),
    }
    row.analysis_error = None
    row.analysis_status = "manual_review" if uncertainty_notes or not pallet_id or not deviations else "analyzed"
    refresh_record_hash(row)
    db.flush()
    audit_log(
        db,
        entity_type="meta_shipment_observation",
        entity_id=row.id,
        action="local_audio_analysis",
        old_value={"analysis_status": old_status},
        new_value={
            "analysis_status": row.analysis_status,
            "has_pallet_id": bool(pallet_id),
            "deviation_count": len(deviations),
            "has_uncertainty_notes": bool(uncertainty_notes),
            "llm_model": row.llm_model,
        },
        user_id=user.id,
        business_id=None,
    )
    db.commit()
    db.refresh(row)
    return {"item": _shipment_observation_out(row), "status": row.analysis_status}


@router.patch("/shipment-observations/{observation_id}/dispatch-lookup")
def update_meta_shipment_dispatch_lookup(
    observation_id: int,
    payload: ShipmentDispatchLookupUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_super_user),
) -> dict:
    row = db.get(MetaShipmentObservation, observation_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="SÃ¤ndningsraden hittades inte.")

    before = _shipment_dispatch_lookup_audit_snapshot(row)
    matched = bool(payload.matched)
    updates = {
        "order_number": _clean_dispatch_lookup_text(payload.order_number, 80),
        "shipment_number": _clean_dispatch_lookup_text(payload.shipment_number, 120),
        "username": _clean_dispatch_lookup_text(payload.username, 120),
        "customer_name": _clean_dispatch_lookup_text(payload.customer_name, 200),
    }
    for key, value in updates.items():
        if value:
            setattr(row, key, value)

    row.uncertainty_notes = _remove_dispatch_lookup_notes(row.uncertainty_notes)
    if payload.note:
        row.uncertainty_notes = _append_dispatch_lookup_note(row.uncertainty_notes, payload.note)
    if row.uncertainty_notes and row.analysis_status == "analyzed":
        row.analysis_status = "manual_review"
    elif row.analysis_status == "manual_review" and not row.uncertainty_notes:
        row.analysis_status = "analyzed"

    refresh_record_hash(row)
    db.flush()
    after = _shipment_dispatch_lookup_audit_snapshot(row)
    audit_log(
        db,
        entity_type="meta_shipment_observation",
        entity_id=row.id,
        action="local_dispatch_lookup",
        old_value=before,
        new_value={
            **after,
            "matched": matched,
            "source": _clean_dispatch_lookup_text(payload.source, 80) or "local_cli",
        },
        user_id=user.id,
        business_id=None,
    )
    db.commit()
    db.refresh(row)
    return {
        "item": _shipment_observation_out(row),
        "status": row.analysis_status,
        "matched": matched,
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
    user: User = Depends(require_super_user),
) -> Response:
    row = db.get(MetaMediaUpload, upload_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Uppladdningen hittades inte.")
    if download:
        audit_log(
            db,
            entity_type="meta_media_upload",
            entity_id=row.id,
            action="download_video",
            old_value=None,
            new_value={"media_type": "video", "size_bytes": int(row.size_bytes or 0)},
            user_id=user.id,
            business_id=None,
        )
        db.commit()
    # variant=playable är ett bakåtkompatibelt alias till original. Ingen
    # request-driven videotranskodning får köras i den enda serverpodden.
    return _media_response(row, request, variant=variant, as_attachment=download)


@router.get("/uploads/{upload_id}/audio")
def download_meta_media_audio(
    upload_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_super_user),
) -> FileResponse:
    row = db.get(MetaMediaUpload, upload_id)
    if row is None or row.media_type != "video":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Videon hittades inte.")
    with tempfile.NamedTemporaryFile(prefix="flow-meta-audio-", suffix=".mp3", delete=False) as temp_file:
        output = Path(temp_file.name)
    try:
        with extract_audio_file(row) as audio:
            shutil.copyfile(audio.path, output)
    except Exception as exc:
        output.unlink(missing_ok=True)
        audit_log(
            db,
            entity_type="meta_media_upload",
            entity_id=row.id,
            action="download_audio_failed",
            old_value=None,
            new_value={"media_type": "audio", "error_type": type(exc).__name__},
            user_id=user.id,
            business_id=None,
        )
        db.commit()
        if isinstance(exc, MetaAnalysisFailed):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
        raise
    audit_log(
        db,
        entity_type="meta_media_upload",
        entity_id=row.id,
        action="download_audio",
        old_value=None,
        new_value={"media_type": "audio", "size_bytes": output.stat().st_size},
        user_id=user.id,
        business_id=None,
    )
    db.commit()
    return FileResponse(
        output,
        media_type="audio/mpeg",
        filename=f"meta-audio-{upload_id}.mp3",
        background=BackgroundTask(_cleanup_path, output),
    )

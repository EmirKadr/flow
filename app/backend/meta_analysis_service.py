from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import re
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterator

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal
from .external_data_client import ExternalDataClient, ExternalDataClientError
from .media_store import get_media_store
from .models import MetaMediaUpload, MetaShipmentObservation
from .observability import add_span_attributes, start_span
from .workflow_data import WorkflowDataError, _api_client, source_spec, workflow_api_configured


logger = logging.getLogger(__name__)

# Begränsa hur många videoanalyser som körs samtidigt i processen (var och en
# kan dra igång ffmpeg + nätverksuppladdning).
_ANALYSIS_SEMAPHORE = threading.Semaphore(max(1, int(settings.META_ANALYSIS_MAX_CONCURRENCY or 1)))


@dataclass(frozen=True)
class AudioFile:
    path: Path
    size_bytes: int
    content_type: str = "audio/mpeg"
    display_name: str = "meta-audio.mp3"


def _media_size(upload: MetaMediaUpload) -> int:
    if upload.storage_key:
        stat = get_media_store().stat(upload.storage_key)
        if stat is not None:
            return stat.size
    return int(upload.size_bytes or 0)


def _hash_from_storage(upload: MetaMediaUpload) -> str:
    digest = hashlib.sha256()
    if upload.storage_key:
        for chunk in get_media_store().open_all(upload.storage_key):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def _media_file(upload: MetaMediaUpload) -> Iterator[Path]:
    """Ge en filväg till mediabytena utan att ladda dem i processminnet.

    Vägen pekar på själva lagringsfilen i MediaStore (läses bara).
    """
    if not upload.storage_key:
        raise MetaAnalysisFailed("Mediafilen saknar lagringsreferens.")
    yield get_media_store().materialize_to_temp(upload.storage_key)


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


def _audio_filename(upload: MetaMediaUpload) -> str:
    stem = Path(upload.stored_filename or upload.original_filename or f"meta-{upload.id}").stem[:180]
    return f"{stem}_audio.mp3"[:255]


@contextmanager
def extract_audio_file(upload: MetaMediaUpload) -> Iterator[AudioFile]:
    ffmpeg = _resolve_ffmpeg()
    if not ffmpeg:
        raise MetaAnalysisFailed("ffmpeg saknas, sa ljudet kunde inte extraheras.")
    with _media_file(upload) as input_path, tempfile.TemporaryDirectory() as temp_dir:
        output_path = Path(temp_dir) / "meta-audio.mp3"
        command = [
            ffmpeg,
            "-y",
            "-threads", "1",  # ffmpeg default = alla karnor; trådtak haller subprocess-minnet lagt i podden
            "-i",
            str(input_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "32k",
            str(output_path),
        ]
        try:
            completed = subprocess.run(command, capture_output=True, timeout=60, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            raise MetaAnalysisFailed(f"Kunde inte extrahera ljud ur videon: {exc}") from exc
        if completed.returncode != 0 or not output_path.exists():
            stderr = (completed.stderr or b"").decode("utf-8", errors="replace")[:500]
            raise MetaAnalysisFailed(f"Kunde inte extrahera ljud ur videon: {stderr}".strip())
        size = output_path.stat().st_size
        if size <= 0:
            raise MetaAnalysisFailed("Videon saknar ljud att analysera.")
        yield AudioFile(path=output_path, size_bytes=size, display_name=_audio_filename(upload))


META_ANALYSIS_INSTRUCTIONS = """
Analysera endast ljudet fran en Meta-video som en lotsvard har spelat in.

Du ska inte lasa eller tolka videobilden, etiketter, transportetiketter eller
innehallsforteckningar. Analysen ska bara bygga pa vad personen sager.

Forvantat talflode:
- Personen borjar med att saga "Pall ID", "Pall", "Godsmarkning" eller liknande.
- Personen sager sedan vilket nummer/id pallen har.
- Personen beskriver sedan vad som ar fel pa pallen eller pallarna.

Regler:
- Ett pall-id bestar ALLTID av exakt 7 siffror. Om din forsta tolkning ger 6
  eller 8 siffror har du raknat fel — lyssna om och justera till 7 siffror.
  Blir det fortfarande inte 7 siffror, skriv osakerheten i uncertainty_notes
  och behall den tolkning som later mest sannolik som exakt 7 siffror.
- Returnera exakt ett pallet_id: det pall-id som hors tydligast.
- Tolka "pall", "godsmärkning", "godsmarkning", "godsmärke" eller liknande
  som pallet_id nar personen anvander det som pallens identitet.
- Om flera pall-id namns, valj bara det tydligaste och skriv osakerheten i
  uncertainty_notes.
- Returnera deviations som en lista med korta avvikelsebeskrivningar.
- Fyll aldrig order_number, shipment_number, username eller customer_name. De
  ska vara tomma eftersom de hamtas fran uppladdad data senare.
- Gissa inte. Om pall-id eller avvikelser inte hors tydligt ska faltet lamnas
  tomt eller osakerheten beskrivas.

Returnera ett JSON-objekt med dessa falt:
pallet_id, deviations, uncertainty_notes, confidence.
""".strip()


class MetaAnalysisNotConfigured(RuntimeError):
    pass


class MetaAnalysisFailed(RuntimeError):
    pass


def meta_analysis_configured() -> bool:
    return bool(settings.GEMINI_API_KEY.strip())


def gemini_model_name() -> str:
    model = settings.GEMINI_MODEL.strip() or "gemini-2.5-pro"
    return model.removeprefix("models/")


def _clean_text(value: Any, max_length: int) -> str | None:
    if isinstance(value, list):
        value = ", ".join(str(item).strip() for item in value if str(item or "").strip())
    text = str(value or "").strip()
    if not text:
        return None
    return text[:max_length]


def _clean_single_text(value: Any, max_length: int) -> str | None:
    if isinstance(value, list):
        for item in value:
            cleaned = _clean_single_text(item, max_length)
            if cleaned:
                return cleaned
        return None
    if isinstance(value, dict):
        for key in ("pallet_id", "pallid", "id", "value", "text", "description"):
            cleaned = _clean_single_text(value.get(key), max_length)
            if cleaned:
                return cleaned
        return None
    text = str(value or "").strip()
    if not text:
        return None
    for separator in (",", ";", "\n", "|"):
        if separator in text:
            text = text.split(separator, 1)[0].strip()
            break
    return text[:max_length] if text else None


def _clean_hash(value: str | None) -> str:
    return str(value or "").strip().lower()


def normalize_deviations(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("description") or item.get("text") or item.get("avvikelse") or item.get("deviation")
            else:
                text = item
            cleaned = str(text or "").strip()
            if cleaned:
                result.append(cleaned[:500])
        return result
    return [str(value).strip()[:500]] if str(value).strip() else []


def calculate_record_hash(
    *,
    video_hash: str,
    order_number: str | None = None,
    shipment_number: str | None = None,
    username: str | None = None,
    customer_name: str | None = None,
    pallet_id: str | None = None,
    label_image_hash: str | None = None,
    deviations: Any = None,
) -> str:
    payload = {
        "version": "v2-audio-only",
        "video_hash": _clean_hash(video_hash),
        "label_image_hash": _clean_hash(label_image_hash),
        "pallet_id": str(pallet_id or "").strip().casefold(),
        "deviations": sorted(item.casefold() for item in normalize_deviations(deviations)),
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def refresh_record_hash(row: MetaShipmentObservation) -> None:
    row.record_hash = calculate_record_hash(
        video_hash=row.video_hash,
        order_number=row.order_number,
        shipment_number=row.shipment_number,
        username=row.username,
        customer_name=row.customer_name,
        pallet_id=row.pallet_id,
        label_image_hash=row.label_image_hash,
        deviations=row.deviations,
    )


def ensure_shipment_observation(db: Session, upload: MetaMediaUpload) -> MetaShipmentObservation | None:
    if upload.media_type != "video":
        return None
    existing = db.query(MetaShipmentObservation).filter_by(media_upload_id=upload.id).first()
    if existing is not None:
        return existing

    video_hash = upload.content_hash or _hash_from_storage(upload)
    if not upload.content_hash:
        upload.content_hash = video_hash
    row = MetaShipmentObservation(
        media_upload_id=upload.id,
        video_hash=video_hash,
        record_hash=calculate_record_hash(video_hash=video_hash),
        analysis_status="queued" if meta_analysis_configured() else "needs_configuration",
        analysis_error=None if meta_analysis_configured() else "GEMINI_API_KEY saknas.",
        llm_model=gemini_model_name(),
    )
    db.add(row)
    db.flush()
    return row


def ensure_shipment_observations(db: Session, uploads: list[MetaMediaUpload]) -> list[MetaShipmentObservation]:
    rows = [row for upload in uploads if (row := ensure_shipment_observation(db, upload)) is not None]
    return rows


def _size_label(bytes_count: int) -> str:
    if bytes_count >= 1024 * 1024:
        return f"{bytes_count / (1024 * 1024):.1f} MB"
    if bytes_count >= 1024:
        return f"{bytes_count / 1024:.1f} kB"
    return f"{bytes_count} B"


def _extract_json_candidate(payload: Any) -> dict:
    if isinstance(payload, dict):
        if isinstance(payload.get("result"), dict):
            return payload["result"]
        if isinstance(payload.get("analysis"), dict):
            return payload["analysis"]
        candidates = payload.get("candidates")
        if isinstance(candidates, list) and candidates:
            parts = candidates[0].get("content", {}).get("parts", []) if isinstance(candidates[0], dict) else []
            for part in parts:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    return json.loads(part["text"])
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            content = choices[0].get("message", {}).get("content") if isinstance(choices[0], dict) else None
            if isinstance(content, str):
                return json.loads(content)
            if isinstance(content, dict):
                return content
        output_text = payload.get("output_text")
        if isinstance(output_text, str):
            return json.loads(output_text)
        return payload
    if isinstance(payload, str):
        return json.loads(payload)
    raise MetaAnalysisFailed("LLM-svaret var inte JSON.")


def _gemini_base_url() -> str:
    base = settings.GEMINI_API_BASE_URL.strip().rstrip("/")
    # Osubstituerade deploy-platshållare ("#{GEMINI_API_BASE_URL}") och annat
    # som inte är http(s) ska falla tillbaka på standard-URL:en, inte krascha.
    if not base.lower().startswith(("https://", "http://")):
        return "https://generativelanguage.googleapis.com"
    return base


def _gemini_url(path: str, query: dict[str, str] | None = None) -> str:
    url = f"{_gemini_base_url()}{path}"
    return f"{url}?{urllib.parse.urlencode(query)}" if query else url


def _gemini_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    # Nyckeln i header (som mcp/chat.py), aldrig i URL:en — URL:er hamnar i loggar/undantag.
    return {"x-goog-api-key": settings.GEMINI_API_KEY.strip(), **(extra or {})}


def _scrub_secrets(text: str) -> str:
    """Maska API-nyckeln i text som sparas/visas (analysis_error, toasts)."""
    key = settings.GEMINI_API_KEY.strip()
    if key:
        text = text.replace(key, "***")
    return re.sub(r"(key=)[A-Za-z0-9_\-]+", r"\1***", text)


def _request_json(request: urllib.request.Request, *, timeout: int) -> dict:
    with start_span(
        "external.gemini.request",
        {
            "external.provider": "gemini",
            "external.method": request.get_method(),
            "external.timeout_seconds": timeout,
        },
    ):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                add_span_attributes({"external.http_status_code": getattr(response, "status", 0) or 0})
        except urllib.error.HTTPError as exc:
            add_span_attributes({"external.http_status_code": exc.code, "external.error_type": "HTTPError"})
            error_body = exc.read().decode("utf-8", errors="replace")
            raise MetaAnalysisFailed(f"Gemini svarade HTTP {exc.code}: {error_body[:500]}") from exc
        except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
            add_span_attributes({"external.error_type": type(exc).__name__})
            raise MetaAnalysisFailed("Gemini kunde inte nas inom timeout.") from exc
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            add_span_attributes({"external.error_type": "JSONDecodeError"})
            raise MetaAnalysisFailed("Gemini-svaret kunde inte tolkas som JSON.") from exc


def _gemini_upload_video_file(upload: MetaMediaUpload) -> dict:
    size = _media_size(upload)
    max_bytes = max(1, int(settings.META_ANALYSIS_MAX_VIDEO_BYTES or 1))
    if size > max_bytes:
        raise MetaAnalysisFailed(
            f"Videon ar {_size_label(size)}, vilket ar storre an grans for Gemini-analys {_size_label(max_bytes)}."
        )
    metadata = {
        "file": {
            "display_name": upload.stored_filename or upload.original_filename or f"meta-{upload.id}",
        }
    }
    start_request = urllib.request.Request(
        _gemini_url("/upload/v1beta/files"),
        data=json.dumps(metadata, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers=_gemini_headers({
            "Content-Type": "application/json",
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(size),
            "X-Goog-Upload-Header-Content-Type": upload.content_type,
        }),
    )
    with start_span("external.gemini.upload_start", {"external.provider": "gemini", "meta.media_size_bytes": size}):
        try:
            with urllib.request.urlopen(start_request, timeout=settings.META_ANALYSIS_TIMEOUT_SECONDS) as response:
                upload_url = response.headers.get("x-goog-upload-url")
                add_span_attributes({"external.http_status_code": getattr(response, "status", 0) or 0})
        except urllib.error.HTTPError as exc:
            add_span_attributes({"external.http_status_code": exc.code, "external.error_type": "HTTPError"})
            error_body = exc.read().decode("utf-8", errors="replace")
            raise MetaAnalysisFailed(f"Gemini upload-start svarade HTTP {exc.code}: {error_body[:500]}") from exc
        except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
            add_span_attributes({"external.error_type": type(exc).__name__})
            raise MetaAnalysisFailed("Gemini upload-start kunde inte nas inom timeout.") from exc
    if not upload_url:
        raise MetaAnalysisFailed("Gemini returnerade ingen upload-URL.")

    # Skicka videon strömmande från lagringsfilen — http.client läser
    # filobjektet i block, så hela filen hamnar aldrig i RAM.
    with _media_file(upload) as media_path, open(media_path, "rb") as handle:
        upload_request = urllib.request.Request(
            upload_url,
            data=handle,
            method="POST",
            headers={
                "Content-Type": upload.content_type,
                "Content-Length": str(size),
                "X-Goog-Upload-Offset": "0",
                "X-Goog-Upload-Command": "upload, finalize",
            },
        )
        return _request_json(upload_request, timeout=settings.META_ANALYSIS_TIMEOUT_SECONDS).get("file", {})


def _gemini_upload_audio(upload: MetaMediaUpload) -> dict:
    video_size = _media_size(upload)
    max_bytes = max(1, int(settings.META_ANALYSIS_MAX_VIDEO_BYTES or 1))
    if video_size > max_bytes:
        raise MetaAnalysisFailed(
            f"Videon ar {_size_label(video_size)}, vilket ar storre an grans for Gemini-analys {_size_label(max_bytes)}."
        )
    with extract_audio_file(upload) as audio:
        metadata = {"file": {"display_name": audio.display_name}}
        start_request = urllib.request.Request(
            _gemini_url("/upload/v1beta/files"),
            data=json.dumps(metadata, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers=_gemini_headers({
                "Content-Type": "application/json",
                "X-Goog-Upload-Protocol": "resumable",
                "X-Goog-Upload-Command": "start",
                "X-Goog-Upload-Header-Content-Length": str(audio.size_bytes),
                "X-Goog-Upload-Header-Content-Type": audio.content_type,
            }),
        )
        with start_span("external.gemini.upload_start", {"external.provider": "gemini", "meta.media_size_bytes": audio.size_bytes}):
            try:
                with urllib.request.urlopen(start_request, timeout=settings.META_ANALYSIS_TIMEOUT_SECONDS) as response:
                    upload_url = response.headers.get("x-goog-upload-url")
                    add_span_attributes({"external.http_status_code": getattr(response, "status", 0) or 0})
            except urllib.error.HTTPError as exc:
                add_span_attributes({"external.http_status_code": exc.code, "external.error_type": "HTTPError"})
                error_body = exc.read().decode("utf-8", errors="replace")
                raise MetaAnalysisFailed(f"Gemini upload-start svarade HTTP {exc.code}: {error_body[:500]}") from exc
            except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
                add_span_attributes({"external.error_type": type(exc).__name__})
                raise MetaAnalysisFailed("Gemini upload-start kunde inte nas inom timeout.") from exc
        if not upload_url:
            raise MetaAnalysisFailed("Gemini returnerade ingen upload-URL.")

        handle = audio.path.open("rb")
        try:
            upload_request = urllib.request.Request(
                upload_url,
                data=handle,
                method="POST",
                headers={
                    "Content-Type": audio.content_type,
                    "Content-Length": str(audio.size_bytes),
                    "X-Goog-Upload-Offset": "0",
                    "X-Goog-Upload-Command": "upload, finalize",
                },
            )
            return _request_json(upload_request, timeout=settings.META_ANALYSIS_TIMEOUT_SECONDS).get("file", {})
        finally:
            handle.close()


def _gemini_get_file(name: str) -> dict:
    safe_name = str(name or "").strip().lstrip("/")
    if not safe_name:
        raise MetaAnalysisFailed("Gemini-fil saknade namn.")
    return _request_json(
        urllib.request.Request(_gemini_url(f"/v1beta/{safe_name}"), method="GET", headers=_gemini_headers()),
        timeout=settings.META_ANALYSIS_TIMEOUT_SECONDS,
    )


def _gemini_wait_file_active(file_info: dict) -> dict:
    name = str(file_info.get("name") or "")
    state = str(file_info.get("state") or "")
    for _attempt in range(24):
        if state in {"ACTIVE", ""}:
            return file_info
        if state == "FAILED":
            raise MetaAnalysisFailed("Gemini kunde inte processa videofilen.")
        time.sleep(5)
        response = _gemini_get_file(name)
        file_info = response.get("file", response) if isinstance(response, dict) else file_info
        state = str(file_info.get("state") or "")
    raise MetaAnalysisFailed("Gemini blev inte klar med videoprocessningen i tid.")


def _gemini_generate_content(file_info: dict) -> dict:
    file_uri = file_info.get("uri")
    mime_type = file_info.get("mimeType") or file_info.get("mime_type")
    if not file_uri:
        raise MetaAnalysisFailed("Gemini-filen saknade URI.")
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "file_data": {
                            "mime_type": mime_type or "audio/mpeg",
                            "file_uri": file_uri,
                        }
                    },
                    {"text": META_ANALYSIS_INSTRUCTIONS},
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "response_mime_type": "application/json",
        },
    }
    request = urllib.request.Request(
        _gemini_url(f"/v1beta/models/{urllib.parse.quote(gemini_model_name(), safe='')}:generateContent"),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers=_gemini_headers({"Content-Type": "application/json"}),
    )
    return _request_json(request, timeout=settings.META_ANALYSIS_TIMEOUT_SECONDS)


def _call_meta_analysis_provider(upload: MetaMediaUpload) -> dict:
    if not meta_analysis_configured():
        raise MetaAnalysisNotConfigured("GEMINI_API_KEY saknas.")
    file_info = _gemini_wait_file_active(_gemini_upload_audio(upload))
    response = _gemini_generate_content(file_info)
    try:
        return _extract_json_candidate(response)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise MetaAnalysisFailed("Gemini-svaret kunde inte tolkas som JSON.") from exc


def _field(payload: dict, *names: str) -> Any:
    for name in names:
        if name in payload and payload[name] not in (None, ""):
            return payload[name]
    return None


def normalize_meta_analysis(payload: dict) -> dict:
    return {
        "order_number": None,
        "shipment_number": None,
        "username": None,
        "customer_name": None,
        "pallet_id": _clean_single_text(
            _field(
                payload,
                "pallet_id",
                "pallet_ids",
                "pallet_candidates",
                "pallid",
                "pall_id",
                "pall",
                "pallet",
                "godsmärkning",
                "godsmarkning",
                "godsmärke",
                "godsmarke",
                "goods_marking",
                "goodsmarking",
                "marking",
            ),
            120,
        ),
        "deviations": normalize_deviations(_field(payload, "deviations", "avvikelser", "faults", "issues")),
        "uncertainty_notes": _clean_text(
            _field(payload, "uncertainty_notes", "uncertainties", "osakerhet", "notes"),
            2000,
        ),
    }


def _row_field(row: dict[str, Any], *names: str) -> Any:
    if not isinstance(row, dict):
        return None
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    by_casefold = {str(key).casefold(): key for key in row}
    for name in names:
        actual = by_casefold.get(str(name).casefold())
        if actual is not None and row.get(actual) not in (None, ""):
            return row.get(actual)
    return None


def _append_uncertainty_note(existing: str | None, note: str | None) -> str | None:
    cleaned_note = _clean_text(note, 2000)
    if not cleaned_note:
        return existing
    cleaned_existing = _clean_text(existing, 2000)
    if not cleaned_existing:
        return cleaned_note
    if cleaned_note in cleaned_existing:
        return cleaned_existing
    return f"{cleaned_existing}; {cleaned_note}"[:2000]


# Live-vyn (v_ask_dispatch_pallet) haller bara ~14 dagar; aldre pallar finns
# enbart i arkivet (~800 dagar). Se wiki/ask-datalagring.md.
DISPATCH_ARCHIVE_VIEW = "dblog_dispatch_pallet_log"


def _pallet_filter_value(pallet: str) -> Any:
    # pick_pall_num ar numerisk i ASK-vyerna — skicka siffror som tal sa
    # EQ-filtret matchar oavsett hur API:t typjamfor.
    return int(pallet) if pallet.isdigit() else pallet


def lookup_dispatch_pallet_fields(pallet_id: str | None) -> dict[str, str | None]:
    """Bast-effort ASK-uppslag: far ALDRIG falla analysen — varje utfall utan
    traff blir en begriplig osakerhetsanteckning pa raden i stallet."""
    pallet = str(pallet_id or "").strip()
    if not pallet:
        return {"note": "Inget pall-id att sla upp i Dispatchpallar."}
    if not workflow_api_configured():
        return {"note": "Extern datakalla ar inte konfigurerad, sa Dispatchpallar kunde inte slas upp."}
    filters = [ExternalDataClient.eq("pick_pall_num", _pallet_filter_value(pallet))]
    try:
        client = _api_client(tenant=settings.META_ANALYSIS_DATA_SOURCE_TENANT or None)
        rows = client.fetch_data(source_spec("dispatch").view, filters=filters)
        if not rows:
            rows = client.fetch_data(DISPATCH_ARCHIVE_VIEW, filters=filters)
    except Exception as exc:  # noqa: BLE001 — aven ovantade fel ska bli en anteckning, inte analysis_failed
        logger.warning("Could not enrich Meta analysis from Dispatchpallar for pallet %s: %s", pallet, exc)
        return {
            "note": f"Dispatchpallar kunde inte hamtas fran ASK for pall-id {pallet} ({type(exc).__name__}).",
        }
    if not rows:
        return {
            "note": f"Dispatchpallar (inklusive arkivet) gav ingen traff for pall-id {pallet}.",
        }

    row = rows[0]
    return {
        "order_number": _clean_text(_row_field(row, "order_num", "Ordernr", "ordernr"), 80),
        "shipment_number": _clean_text(
            _row_field(row, "shipment_id", "Sändningsnr", "sandningsnr", "sändningsnr"),
            120,
        ),
        "username": _clean_text(_row_field(row, "user_id", "Användare", "anvandare", "användare"), 120),
        "customer_name": _clean_text(
            _row_field(row, "custom_desc", "custom_num", "Kund", "kund", "customer_name", "customer"),
            200,
        ),
        "note": None,
    }


def _apply_dispatch_lookup(observation: MetaShipmentObservation, fields: dict) -> None:
    lookup = lookup_dispatch_pallet_fields(fields.get("pallet_id"))
    if not lookup:
        return
    for target in ("order_number", "shipment_number", "username", "customer_name"):
        if lookup.get(target):
            setattr(observation, target, lookup[target])
    if lookup.get("note"):
        observation.uncertainty_notes = _append_uncertainty_note(
            observation.uncertainty_notes,
            lookup.get("note"),
        )


def _status_for_analysis(fields: dict) -> str:
    if fields.get("uncertainty_notes"):
        return "manual_review"
    if not fields.get("pallet_id") or not fields.get("deviations"):
        return "manual_review"
    return "analyzed"


def analyze_meta_upload(db: Session, upload_id: int) -> MetaShipmentObservation:
    upload = db.get(MetaMediaUpload, upload_id)
    if upload is None or upload.media_type != "video":
        raise MetaAnalysisFailed("Videon hittades inte.")
    observation = ensure_shipment_observation(db, upload)
    if observation is None:
        raise MetaAnalysisFailed("Ingen sändningsrad kunde skapas.")

    if not meta_analysis_configured():
        observation.analysis_status = "needs_configuration"
        observation.analysis_error = "GEMINI_API_KEY saknas."
        refresh_record_hash(observation)
        db.commit()
        db.refresh(observation)
        return observation

    observation.analysis_status = "analyzing"
    observation.analysis_error = None
    observation.llm_model = gemini_model_name()
    db.commit()

    try:
        raw_response = _call_meta_analysis_provider(upload)
        fields = normalize_meta_analysis(raw_response)
        observation.order_number = fields["order_number"]
        observation.shipment_number = fields["shipment_number"]
        observation.username = fields["username"]
        observation.customer_name = fields["customer_name"]
        observation.pallet_id = fields["pallet_id"]
        observation.deviations = fields["deviations"]
        observation.uncertainty_notes = fields["uncertainty_notes"]
        observation.llm_raw_response = raw_response
        _apply_dispatch_lookup(observation, fields)
        observation.analysis_status = _status_for_analysis(
            {**fields, "uncertainty_notes": observation.uncertainty_notes},
        )
        observation.analysis_error = None
        refresh_record_hash(observation)
        db.commit()
        db.refresh(observation)
        return observation
    except (MetaAnalysisFailed, IntegrityError) as exc:
        db.rollback()
        observation = db.query(MetaShipmentObservation).filter_by(media_upload_id=upload_id).first()
        if observation is None:
            raise
        observation.analysis_status = "analysis_failed"
        observation.analysis_error = _scrub_secrets(str(exc))
        refresh_record_hash(observation)
        db.commit()
        db.refresh(observation)
        return observation
    except Exception as exc:  # noqa: BLE001
        # Ett oväntat fel (t.ex. ffmpeg-timeout, DB-fel) får inte lämna raden
        # låst i "analyzing" med en naken 500 — då disablas Analysera-knappen
        # för alltid. Logga full traceback för rotorsak och markera raden som
        # analysis_failed med felet synligt i UI:t så den kan köras om.
        logger.exception("Meta-analys kraschade oväntat for upload %s", upload_id)
        db.rollback()
        observation = db.query(MetaShipmentObservation).filter_by(media_upload_id=upload_id).first()
        if observation is None:
            raise
        observation.analysis_status = "analysis_failed"
        observation.analysis_error = _scrub_secrets(f"Oväntat fel vid analys: {type(exc).__name__}: {exc}")[:2000]
        refresh_record_hash(observation)
        db.commit()
        db.refresh(observation)
        return observation


def run_meta_analysis_background(upload_ids: list[int]) -> None:
    with SessionLocal() as db:
        for index, upload_id in enumerate(upload_ids):
            # Semaforen håller nere samtidiga analyser (ffmpeg + uppladdning).
            with _ANALYSIS_SEMAPHORE:
                try:
                    delay = float(settings.META_ANALYSIS_START_DELAY_SECONDS or 0)
                    spacing = float(settings.META_ANALYSIS_SPACING_SECONDS or 0)
                    if delay > 0:
                        time.sleep(delay)
                    analyze_meta_upload(db, upload_id)
                    if spacing > 0 and index < len(upload_ids) - 1:
                        time.sleep(spacing)
                except Exception:
                    logger.exception("Meta analysis background job failed for upload %s", upload_id)


def queued_meta_analysis_upload_ids(db: Session, *, limit: int = 1) -> list[int]:
    rows = (
        db.query(MetaShipmentObservation.media_upload_id)
        .filter(MetaShipmentObservation.analysis_status == "queued")
        .order_by(MetaShipmentObservation.created_at.asc(), MetaShipmentObservation.id.asc())
        .limit(max(1, int(limit)))
        .all()
    )
    return [int(row[0]) for row in rows if row and row[0] is not None]


def run_queued_meta_analysis_once(*, limit: int = 1, spacing_seconds: float | None = None) -> int:
    processed = 0
    spacing = float(settings.META_ANALYSIS_SPACING_SECONDS if spacing_seconds is None else spacing_seconds or 0)
    with SessionLocal() as db:
        upload_ids = queued_meta_analysis_upload_ids(db, limit=limit)
        for index, upload_id in enumerate(upload_ids):
            with _ANALYSIS_SEMAPHORE:
                try:
                    analyze_meta_upload(db, upload_id)
                    processed += 1
                    if spacing > 0 and index < len(upload_ids) - 1:
                        time.sleep(spacing)
                except Exception:
                    logger.exception("Queued Meta analysis failed for upload %s", upload_id)
    return processed


def purge_expired_meta_media(retention_days: int | None = None) -> int:
    """Radera klaranalyserade meta-media äldre än retentiongränsen.

    Tar bort både DB-raden och bytena i lagringen. Returnerar antal raderade
    uppladdningar. Körs vid startup (se main.py).
    """
    days = int(settings.META_MEDIA_RETENTION_DAYS if retention_days is None else retention_days)
    if days < 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    store = get_media_store()
    removed = 0
    done_statuses = {"analyzed", "manual_review", "analysis_failed", "needs_configuration"}
    with SessionLocal() as db:
        observations = {
            obs.media_upload_id: obs.analysis_status
            for obs in db.query(
                MetaShipmentObservation.media_upload_id,
                MetaShipmentObservation.analysis_status,
            ).all()
        }
        rows = (
            db.query(MetaMediaUpload)
            .filter(MetaMediaUpload.created_at < cutoff)
            .order_by(MetaMediaUpload.id)
            .all()
        )
        for row in rows:
            # Behåll videor vars analys inte är klar.
            if row.media_type == "video":
                state = observations.get(row.id)
                if state is not None and state not in done_statuses:
                    continue
            storage_key = row.storage_key
            db.query(MetaShipmentObservation).filter(
                MetaShipmentObservation.media_upload_id == row.id
            ).delete(synchronize_session=False)
            label_refs = db.query(MetaShipmentObservation).filter(
                MetaShipmentObservation.label_image_upload_id == row.id
            ).all()
            for observation in label_refs:
                observation.label_image_upload_id = None
                observation.label_image_hash = None
                refresh_record_hash(observation)
            db.delete(row)
            db.flush()
            if storage_key:
                still_referenced = (
                    db.query(MetaMediaUpload.id)
                    .filter(MetaMediaUpload.storage_key == storage_key)
                    .first()
                    is not None
                )
                if not still_referenced:
                    store.delete(storage_key)
            removed += 1
        db.commit()
    if removed:
        logger.info("Retention: raderade %s meta-media äldre än %s dagar.", removed, days)
    return removed

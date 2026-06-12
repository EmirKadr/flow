"""Local Windows runtime for file-backed Flow calculations."""
from __future__ import annotations

import cgi
import json
import mimetypes
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, quote, urljoin

import requests

from app.backend import allocation_bridge as allocation
from app.backend import workflow_data
from app.backend.productivity_service import ProductivitySourceError
from app.backend.coredata_service import find_coredata_file


LOCAL_REF_PREFIX = "__flow_local_ref:"
ARTICLE_MAX_KEY = "article_max"
BUSINESS_ARTICLE_MAX_FLOW_IDS = {"ordersaldo", "lyx", "pafyllnadsprio"}
FORECAST_COREDATA_DEFAULTS = {
    "custom": "custom",
    "item": "item",
    "item_alias": "item_alias",
    "dimension": "dimension",
    "pallet_type": "pallet_type",
    "item_option": "item_option",
    "trans_agency": "trans_agency",
}
BUSINESS_COREDATA_FLOW_DEFAULTS = {
    "allocate": {"items": "item_option"},
    "goods-declaration": {"item_security_info": "item_security_info"},
    "forecast": FORECAST_COREDATA_DEFAULTS,
    "ytgenerering": {**FORECAST_COREDATA_DEFAULTS, "location": "location"},
}


def _allocation_required_file_keys(flow_id: str) -> set[str]:
    for flow in allocation.public_registry():
        if str(flow.get("id") or "") != str(flow_id or ""):
            continue
        required: set[str] = set()
        for item in flow.get("inputs") or []:
            if item.get("type") == "file" and item.get("required"):
                required.add(str(item.get("key") or ""))
        for item in flow.get("coredata") or []:
            if item.get("required"):
                required.add(str(item.get("key") or ""))
        return {key for key in required if key}
    return set()


def _response_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    return f"Extern datakälla kunde inte nås. Servern svarade HTTP {response.status_code}."


@dataclass(frozen=True)
class LocalFileEntry:
    ref: str
    path: Path
    name: str
    size: int
    last_modified_ms: int
    content_type: str
    file_type: str | None = None


def default_desktop_data_dir() -> Path:
    root = os.environ.get("APPDATA") or str(Path.home())
    return Path(root) / "flow" / "desktop-data"


def _safe_filename(value: str, fallback: str = "file.csv") -> str:
    name = Path(value or fallback).name
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name).strip(" ._")
    return cleaned or fallback


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _is_local_ref(value: str | None) -> bool:
    return str(value or "").startswith(LOCAL_REF_PREFIX)


def _ref_value(value: str) -> str:
    return str(value or "")[len(LOCAL_REF_PREFIX):]


def _format_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} kB"
    return f"{size} B"


class DesktopLocalRuntime:
    """Shared state between QWebEngine's bridge and the local HTTP server."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = (data_dir or default_desktop_data_dir()).resolve()
        self.cache_dir = self.data_dir / "cache"
        self.upload_dir = self.data_dir / "uploads"
        self._files: dict[str, LocalFileEntry] = {}
        self._jobs: dict[str, dict[str, Any]] = {}
        self._work_queue: queue.Queue[Callable[[], None]] = queue.Queue()
        self._work_thread_started = False
        self._lock = threading.RLock()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def _enqueue_work(self, worker: Callable[[], None]) -> None:
        with self._lock:
            if not self._work_thread_started:
                threading.Thread(target=self._work_loop, name="flowDesktopSyncWorker", daemon=True).start()
                self._work_thread_started = True
        self._work_queue.put(worker)

    def _work_loop(self) -> None:
        while True:
            worker = self._work_queue.get()
            try:
                worker()
            except Exception:
                pass
            finally:
                self._work_queue.task_done()

    def _next_ref(self) -> str:
        return uuid.uuid4().hex

    def register_path(self, raw_path: str | Path) -> dict[str, Any]:
        path = Path(raw_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Filen hittades inte: {path}")
        stat = path.stat()
        ref = self._next_ref()
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        file_type = self.detect_path(path)
        entry = LocalFileEntry(
            ref=ref,
            path=path,
            name=path.name,
            size=int(stat.st_size),
            last_modified_ms=int(stat.st_mtime * 1000),
            content_type=content_type,
            file_type=file_type,
        )
        with self._lock:
            self._files[ref] = entry
        return self.entry_payload(entry)

    def entry_payload(self, entry: LocalFileEntry) -> dict[str, Any]:
        return {
            "localRef": entry.ref,
            "name": entry.name,
            "size": entry.size,
            "type": entry.content_type,
            "lastModified": entry.last_modified_ms,
            "fileType": entry.file_type,
            "source": "desktop-local",
        }

    def file_for_ref(self, ref: str) -> LocalFileEntry:
        clean_ref = _ref_value(ref) if _is_local_ref(ref) else str(ref or "")
        with self._lock:
            entry = self._files.get(clean_ref)
        if entry is None:
            raise FileNotFoundError("Den lokala filreferensen hittades inte.")
        if not entry.path.is_file():
            raise FileNotFoundError(f"Filen finns inte längre på disk: {entry.name}")
        return entry

    def detect_path(self, path: Path) -> str | None:
        try:
            return allocation.detect_file_type(path)
        except Exception:
            return None

    def detect_ref(self, ref: str) -> dict[str, Any]:
        entry = self.file_for_ref(ref)
        file_type = entry.file_type or self.detect_path(entry.path)
        return {"file_type": file_type, "entry": self.entry_payload(entry)}

    def open_ref(self, ref: str, *, folder: bool = False) -> None:
        entry = self.file_for_ref(ref)
        target = entry.path.parent if folder else entry.path
        if os.name == "nt":
            if folder:
                subprocess.Popen(["explorer", f"/select,{entry.path}"])
            else:
                os.startfile(str(target))  # type: ignore[attr-defined]
            return
        if os.name == "posix":
            subprocess.Popen(["open" if os.uname().sysname == "Darwin" else "xdg-open", str(target)])

    def cache_file_path(self, key: str, filename: str | None = None) -> Path:
        if key == ARTICLE_MAX_KEY:
            return self.cache_dir / "artikel_max.csv"
        if key.startswith("productivity_"):
            return self.cache_dir / "compiled" / _safe_filename(filename or f"{key}.csv.gz")
        if key == "kpi":
            return self.cache_dir / _safe_filename(filename or "v_ask_kpi_target.csv")
        return self.cache_dir / "coredata" / _safe_filename(filename or f"{key}.csv")

    def _cached_coredata_file(self, file_type: str) -> Path:
        return find_coredata_file(file_type, self.cache_dir)

    def _cached_article_max(self) -> Path | None:
        path = self.cache_file_path(ARTICLE_MAX_KEY)
        return path if path.is_file() else None

    def _resolve_flow_files(self, fields: dict[str, str], uploads: dict[str, Path]) -> tuple[dict[str, Path], dict[str, str]]:
        files: dict[str, Path] = dict(uploads)
        params: dict[str, str] = {}
        for key, value in fields.items():
            if _is_local_ref(value):
                files[key] = self.file_for_ref(value).path
            else:
                params[key] = value
        return files, params

    def _download_workflow_source(
        self,
        *,
        upstream_root: str,
        headers: dict[str, str],
        feature: str,
        flow_id: str,
        source_key: str,
    ) -> tuple[Path, int]:
        if not str(upstream_root or "").strip():
            raise RuntimeError("Extern datakälla kunde inte nås.")
        response = requests.post(
            urljoin(upstream_root, "api/workflow-data/source"),
            data=json.dumps(
                {
                    "feature": feature,
                    "flow_id": flow_id,
                    "source_key": source_key,
                },
                ensure_ascii=False,
            ).encode("utf-8"),
            headers=_forward_headers(headers, content_type="application/json"),
            timeout=(8, 180),
        )
        if response.status_code >= 400:
            raise RuntimeError(_response_detail(response))
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{source_key}.csv")
        path = Path(tmp.name)
        try:
            tmp.write(response.content)
        finally:
            tmp.close()
        return path, int(response.headers.get("X-Flow-Source-Rows") or 0)

    def _resolve_api_first_sources(
        self,
        *,
        feature: str,
        flow_id: str,
        source_map: dict[str, str],
        files: dict[str, Path],
        required_keys: set[str],
        local_ref_keys: set[str],
        upstream_root: str,
        headers: dict[str, str],
    ) -> workflow_data.WorkflowResolution:
        resolved = dict(files)
        temp_paths: list[Path] = []
        entries: list[workflow_data.WorkflowSourceEntry] = []
        for file_key, source_key in source_map.items():
            spec = workflow_data.source_spec(source_key)
            required = file_key in required_keys
            try:
                path, row_count = self._download_workflow_source(
                    upstream_root=upstream_root,
                    headers=headers,
                    feature=feature,
                    flow_id=flow_id,
                    source_key=source_key,
                )
                resolved[file_key] = path
                temp_paths.append(path)
                entries.append(
                    workflow_data.WorkflowSourceEntry(
                        key=file_key,
                        label=spec.label,
                        view=spec.view,
                        status="api",
                        row_count=row_count,
                    )
                )
                continue
            except Exception as exc:  # noqa: BLE001
                fallback = None
                if file_key in files:
                    fallback = "local_ref_fallback" if file_key in local_ref_keys else "upload_fallback"
                if fallback:
                    entries.append(
                        workflow_data.WorkflowSourceEntry(
                            key=file_key,
                            label=spec.label,
                            view=spec.view,
                            status=fallback,
                            message=str(exc),
                        )
                    )
                    continue
                if not required:
                    entries.append(
                        workflow_data.WorkflowSourceEntry(
                            key=file_key,
                            label=spec.label,
                            view=spec.view,
                            status="optional_skipped",
                            message=str(exc),
                        )
                    )
                    continue
                for temp_path in temp_paths:
                    temp_path.unlink(missing_ok=True)
                raise RuntimeError(f"{exc} Ladda upp {spec.label} och kör igen.") from exc
        return workflow_data.WorkflowResolution(files=resolved, temp_paths=temp_paths, entries=entries)

    def run_allocation_flow(
        self,
        flow_id: str,
        fields: dict[str, str],
        uploads: dict[str, Path],
        *,
        upstream_root: str = "",
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        files, params = self._resolve_flow_files(fields, uploads)
        raw_filter_profile = params.pop(allocation.USER_FILTERS_PARAM, "")
        try:
            user_filter_profile = allocation.normalize_user_filter_profile(json.loads(raw_filter_profile)) if raw_filter_profile else {}
        except Exception:
            user_filter_profile = {}
        local_ref_keys = {key for key, value in fields.items() if _is_local_ref(value)}
        for file_key, coredata_type in BUSINESS_COREDATA_FLOW_DEFAULTS.get(flow_id, {}).items():
            if file_key in files:
                continue
            try:
                files[file_key] = self._cached_coredata_file(coredata_type)
                local_ref_keys.add(file_key)
            except Exception:
                pass
        default_max = None
        if flow_id in BUSINESS_ARTICLE_MAX_FLOW_IDS and "max_csv" not in files:
            default_max = self._cached_article_max()
        source_resolution: workflow_data.WorkflowResolution | None = None
        try:
            source_map = allocation.api_source_map_for_user_profile(
                workflow_data.allocation_api_source_map(flow_id),
                flow_id,
                user_filter_profile,
            )
            if source_map:
                source_resolution = self._resolve_api_first_sources(
                    feature="allocation",
                    flow_id=flow_id,
                    source_map=source_map,
                    files=files,
                    required_keys=_allocation_required_file_keys(flow_id),
                    local_ref_keys=local_ref_keys,
                    upstream_root=upstream_root,
                    headers=headers or {},
                )
                files = source_resolution.files
            files, user_filter_temp_paths, user_filter_log = allocation.apply_user_flow_filters(files, flow_id, user_filter_profile)
            if flow_id == "ytgenerering":
                allocation.apply_ytgenerering_user_settings(
                    params,
                    user_filter_profile,
                    area_focus=params.get(allocation.PROCESS_AREA_FOCUS_PARAM, "") or "ALLT",
                )
            result = allocation.run_flow_handler(flow_id, files, params, default_max_csv_path=default_max)
            if user_filter_log:
                result["log"] = user_filter_log + list(result.get("log") or [])
                result["user_filter"] = {"lines": user_filter_log}
            if source_resolution is not None:
                result["log"] = source_resolution.log_lines + list(result.get("log") or [])
                result["source_status"] = source_resolution.audit_entries
            result["local_run"] = True
            result["duration_ms"] = int((time.perf_counter() - started) * 1000)
            return result
        finally:
            for temp_path in (source_resolution.temp_paths if source_resolution is not None else []):
                temp_path.unlink(missing_ok=True)
            for temp_path in locals().get("user_filter_temp_paths", []):
                temp_path.unlink(missing_ok=True)

    def enqueue_upload(
        self,
        *,
        ref: str,
        upstream_root: str,
        upstream_path: str,
        filename: str,
        headers: dict[str, str],
        label: str,
    ) -> dict[str, Any]:
        entry = self.file_for_ref(ref)
        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "label": label,
            "state": "köad",
            "filename": filename or entry.name,
            "created_at": time.time(),
        }
        with self._lock:
            self._jobs[job_id] = job

        def worker() -> None:
            self._set_job(job_id, state="läser")
            try:
                url = urljoin(upstream_root, upstream_path.lstrip("/"))
                with entry.path.open("rb") as handle:
                    self._set_job(job_id, state="synkar")
                    response = requests.post(
                        url,
                        params={"filename": filename or entry.name},
                        data=handle,
                        headers=_forward_headers(headers, content_type="text/csv"),
                        timeout=(8, 180),
                    )
                if response.status_code >= 400:
                    raise RuntimeError(f"Servern svarade HTTP {response.status_code}")
                self._set_job(job_id, state="klar", status_code=response.status_code)
            except Exception as exc:  # noqa: BLE001
                self._set_job(job_id, state="fel", error=str(exc))

        self._enqueue_work(worker)
        return job

    def enqueue_local_audit(self, *, upstream_root: str, headers: dict[str, str], payload: dict[str, Any]) -> None:
        def worker() -> None:
            try:
                response = requests.post(
                    urljoin(upstream_root, "api/audit/local-run"),
                    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    headers=_forward_headers(headers, content_type="application/json"),
                    timeout=(4, 20),
                )
                if response.status_code >= 400:
                    response.close()
            except Exception:
                return

        threading.Thread(target=worker, name="flowDesktopAudit", daemon=True).start()

    def _set_job(self, job_id: str, **updates: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.update(updates)
            job["updated_at"] = time.time()

    def jobs_payload(self) -> dict[str, Any]:
        with self._lock:
            jobs = list(self._jobs.values())[-50:]
        return {"jobs": jobs}

    def sync_cache_from_upstream(self, *, upstream_root: str, headers: dict[str, str]) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        self._jobs[job_id] = {"id": job_id, "label": "Lokal cache", "state": "köad", "created_at": time.time()}

        def worker() -> None:
            self._set_job(job_id, state="synkar")
            try:
                status_url = urljoin(upstream_root, "api/coredata/files")
                response = requests.get(status_url, headers=_forward_headers(headers), timeout=(8, 60))
                response.raise_for_status()
                status_payload = response.json()
                downloaded = 0
                for key, item in (status_payload.get("files") or {}).items():
                    if not item.get("uploaded"):
                        continue
                    download_url = urljoin(upstream_root, f"api/coredata/files/{quote(str(key))}/download")
                    file_response = requests.get(download_url, headers=_forward_headers(headers), timeout=(8, 180))
                    if file_response.status_code >= 400:
                        continue
                    target = self.cache_file_path(str(key), item.get("name") or f"{key}.csv")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
                    tmp.write_bytes(file_response.content)
                    tmp.replace(target)
                    downloaded += 1
                self._set_job(job_id, state="klar", downloaded=downloaded)
            except Exception as exc:  # noqa: BLE001
                self._set_job(job_id, state="fel", error=str(exc))

        self._enqueue_work(worker)
        return self._jobs[job_id]


def _forward_headers(headers: dict[str, str], *, content_type: str | None = None) -> dict[str, str]:
    result = {}
    for key, value in headers.items():
        lowered = key.lower()
        if lowered in {"host", "connection", "content-length", "transfer-encoding"}:
            continue
        if lowered == "content-type" and content_type:
            continue
        result[key] = value
    if content_type:
        result["Content-Type"] = content_type
    return result


def parse_multipart(handler) -> tuple[dict[str, str], dict[str, Path], list[Path]]:
    form = cgi.FieldStorage(
        fp=handler.rfile,
        headers=handler.headers,
        environ={
            "REQUEST_METHOD": handler.command,
            "CONTENT_TYPE": handler.headers.get("Content-Type", ""),
        },
        keep_blank_values=True,
    )
    fields: dict[str, str] = {}
    uploads: dict[str, Path] = {}
    temp_paths: list[Path] = []
    items = form.list or []
    for item in items:
        key = item.name
        if not key:
            continue
        if item.filename:
            suffix = Path(item.filename).suffix or ".csv"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            try:
                shutil.copyfileobj(item.file, tmp)
            finally:
                tmp.close()
            path = Path(tmp.name)
            uploads[key] = path
            temp_paths.append(path)
        else:
            value = item.value
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="replace")
            if str(value or "").strip():
                fields[key] = str(value)
    return fields, uploads, temp_paths


def _audit_file_types(fields: dict[str, str], uploads: dict[str, Path]) -> list[str]:
    names = set(uploads.keys())
    names.update(key for key, value in fields.items() if _is_local_ref(value))
    return sorted(str(name)[:80] for name in names if name)


def _table_row_counts(result: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, table in (result.get("tables") or {}).items():
        if isinstance(table, dict) and isinstance(table.get("rows"), list):
            counts[str(key)] = len(table["rows"])
    return counts


def _allocation_audit_payload(
    flow_id: str,
    *,
    status: str,
    duration_ms: int,
    fields: dict[str, str],
    uploads: dict[str, Path],
    result: dict[str, Any] | None = None,
    error: Exception | None = None,
) -> dict[str, Any]:
    payload = {
        "feature": "allocation",
        "flow_id": flow_id,
        "status": status,
        "duration_ms": duration_ms,
        "file_types": _audit_file_types(fields, uploads),
        "row_counts": {},
        "result_counts": _table_row_counts(result or {}),
    }
    if error is not None:
        payload["error_type"] = type(error).__name__
    return payload


def _productivity_audit_payload(
    report: dict[str, Any] | None,
    *,
    status: str,
    duration_ms: int,
    file_types: list[str],
    error: Exception | None = None,
) -> dict[str, Any]:
    row_counts = {
        str(key): int(source.get("rows") or 0)
        for key, source in (report or {}).get("sources", {}).items()
        if isinstance(source, dict)
    }
    summary = (report or {}).get("summary") or {}
    result_counts = {
        key: int(summary.get(key) or 0)
        for key in ("sections", "users", "total_rows", "worked_hours")
    }
    payload = {
        "feature": "productivity",
        "flow_id": "productivity",
        "status": status,
        "duration_ms": duration_ms,
        "file_types": sorted(str(key)[:80] for key in file_types if key),
        "row_counts": row_counts,
        "result_counts": result_counts,
    }
    if error is not None:
        payload["error_type"] = type(error).__name__
    return payload


def _upstream_json(upstream_root: str, path: str, headers: dict[str, str]) -> dict[str, Any] | None:
    if not str(upstream_root or "").strip():
        return None
    try:
        response = requests.get(
            urljoin(upstream_root, path.lstrip("/")),
            headers=_forward_headers(headers),
            timeout=(4, 30),
        )
        if response.status_code >= 400:
            return None
        payload = response.json()
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def local_response_for_request(
    runtime: DesktopLocalRuntime,
    handler,
    *,
    parsed,
    upstream_root: str,
) -> tuple[int, str, bytes] | None:
    path = parsed.path
    method = handler.command.upper()
    headers = dict(handler.headers.items())
    try:
        if path == "/api/desktop/capabilities" and method == "GET":
            return 200, "application/json; charset=utf-8", _json_bytes({"desktop": True, "local_files": True})
        if path == "/api/desktop/jobs" and method == "GET":
            return 200, "application/json; charset=utf-8", _json_bytes(runtime.jobs_payload())
        if path == "/api/desktop/cache/sync" and method == "POST":
            return 200, "application/json; charset=utf-8", _json_bytes(runtime.sync_cache_from_upstream(upstream_root=upstream_root, headers=headers))
        if path.startswith("/api/desktop/files/") and method == "GET":
            parts = path.split("/")
            ref = parts[4] if len(parts) > 4 else ""
            action = parts[5] if len(parts) > 5 else "detect"
            if action == "detect":
                return 200, "application/json; charset=utf-8", _json_bytes(runtime.detect_ref(ref))
        if path.startswith("/api/desktop/files/") and method == "POST":
            parts = path.split("/")
            ref = parts[4] if len(parts) > 4 else ""
            action = parts[5] if len(parts) > 5 else ""
            if action in {"open", "open-folder"}:
                runtime.open_ref(ref, folder=action == "open-folder")
                return 200, "application/json; charset=utf-8", _json_bytes({"ok": True})
        if path == "/api/desktop/sync/coredata" and method == "POST":
            body = _read_json_body(handler)
            job = runtime.enqueue_upload(
                ref=body.get("localRef") or "",
                upstream_root=upstream_root,
                upstream_path="/api/coredata/files/raw",
                filename=body.get("filename") or "",
                headers=headers,
                label="Kärnfil",
            )
            return 202, "application/json; charset=utf-8", _json_bytes({"job": job})
        if (
            path == "/api/productivity"
            or path.startswith("/api/productivity/persons/")
            or path == "/api/schedule/productivity-summary"
        ) and method == "GET":
            started = time.perf_counter()
            file_types: list[str] = []
            upstream_path = path
            if parsed.query:
                upstream_path = f"{upstream_path}?{parsed.query}"
            report = _upstream_json(upstream_root, upstream_path, headers)
            if report is not None:
                runtime.enqueue_local_audit(
                    upstream_root=upstream_root,
                    headers=headers,
                    payload=_productivity_audit_payload(
                        report,
                        status="ok",
                        duration_ms=int((time.perf_counter() - started) * 1000),
                        file_types=file_types,
                    ),
                )
                return 200, "application/json; charset=utf-8", _json_bytes(report)
            error = ProductivitySourceError("Produktivitetsrapporten kräver central serverdata för schema och KPI-snapshot.")
            runtime.enqueue_local_audit(
                upstream_root=upstream_root,
                headers=headers,
                payload=_productivity_audit_payload(
                    None,
                    status="error",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    file_types=file_types,
                    error=error,
                ),
            )
            return 503, "application/json; charset=utf-8", _json_bytes({"detail": str(error)})
        if path.startswith("/api/allokering/flow/") and method == "POST":
            flow_id = path.rsplit("/", 1)[-1]
            fields, uploads, temp_paths = parse_multipart(handler)
            started = time.perf_counter()
            try:
                result = runtime.run_allocation_flow(flow_id, fields, uploads, upstream_root=upstream_root, headers=headers)
                runtime.enqueue_local_audit(
                    upstream_root=upstream_root,
                    headers=headers,
                    payload=_allocation_audit_payload(
                        flow_id,
                        status="ok",
                        duration_ms=int(result.get("duration_ms") or (time.perf_counter() - started) * 1000),
                        fields=fields,
                        uploads=uploads,
                        result=result,
                    ),
                )
                return 200, "application/json; charset=utf-8", _json_bytes(result)
            except Exception as exc:
                runtime.enqueue_local_audit(
                    upstream_root=upstream_root,
                    headers=headers,
                    payload=_allocation_audit_payload(
                        flow_id,
                        status="error",
                        duration_ms=int((time.perf_counter() - started) * 1000),
                        fields=fields,
                        uploads=uploads,
                        error=exc,
                    ),
                )
                raise
            finally:
                for temp_path in temp_paths:
                    temp_path.unlink(missing_ok=True)
        if path.startswith("/api/allokering/table-column/") and method == "GET":
            parts = path.split("/")
            session_id, key, column_index = parts[4], parts[5], int(parts[6])
            if session_id in allocation.SESSIONS:
                return 200, "application/json; charset=utf-8", _json_bytes(allocation.table_column_text(session_id, key, column_index))
        if path.startswith("/api/allokering/download/") and method == "GET":
            parts = path.split("/")
            session_id, key = parts[4], parts[5]
            if session_id in allocation.SESSIONS:
                payload = _download_payload(session_id, key)
                return 200, payload["content_type"], payload["body"]
    except Exception as exc:  # noqa: BLE001
        return 400, "application/json; charset=utf-8", _json_bytes({"detail": str(exc)})
    return None


def _read_json_body(handler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    raw = handler.rfile.read(length) if length else b"{}"
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _download_payload(session_id: str, key: str) -> dict[str, Any]:
    session = allocation.SESSIONS.get(session_id)
    if session is None:
        raise FileNotFoundError("Resultatet hittades inte.")
    download_file = (session.get("download_files") or {}).get(key)
    if download_file is not None:
        content = download_file.get("content", "")
        if isinstance(content, bytes):
            body = content
        else:
            body = str(content).encode(download_file.get("encoding") or "utf-8-sig")
        return {"content_type": "text/csv; charset=utf-8", "body": body}
    table = (session.get("tables") or {}).get(key)
    if table is None:
        raise FileNotFoundError("Resultatfilen hittades inte.")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    path = Path(tmp.name)
    tmp.close()
    try:
        if hasattr(table, "to_csv"):
            table.to_csv(path, index=False, encoding="utf-8-sig")
            body = path.read_bytes()
        else:
            body = str(table).encode("utf-8-sig")
    finally:
        path.unlink(missing_ok=True)
    return {"content_type": "text/csv; charset=utf-8", "body": body}

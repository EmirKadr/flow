from __future__ import annotations

import os
import platform
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import settings


ERROR_WORDS = ("error", "exception", "traceback", "failed", "panic", "out of memory", "oom", "killed")
WARNING_WORDS = ("warn", "warning", "timeout", "retry", "slow", "memory", "cpu", "connection")
SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|secret|password)=([^&\s]+)"),
    re.compile(r"(?i)(bearer\s+)[a-z0-9._~+/=-]+"),
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: Any, *, limit: int = 900) -> str:
    text_value = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    for pattern in SECRET_PATTERNS:
        text_value = pattern.sub(lambda match: f"{match.group(1)}[redacted]", text_value)
    return text_value[: limit - 3] + "..." if len(text_value) > limit else text_value


def status_rank(status: str) -> int:
    return {"ok": 0, "info": 0, "unknown": 1, "warn": 2, "error": 3}.get(status, 1)


def worst_status(items: list[dict[str, Any]]) -> str:
    if not items:
        return "unknown"
    return max((str(item.get("status") or "unknown") for item in items), key=status_rank)


def check(name: str, status: str, message: str, **details: Any) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "message": clean_text(message, limit=500),
        "details": details,
    }


def recommendation(severity: str, message: str, **details: Any) -> dict[str, Any]:
    return {
        "severity": severity,
        "message": clean_text(message, limit=700),
        "details": details,
    }


def service_id() -> str:
    return settings.RENDER_WEB_SERVICE_ID or settings.RENDER_SERVICE_ID or os.getenv("RENDER_SERVICE_ID", "")


def postgres_id() -> str:
    return settings.RENDER_POSTGRES_ID or settings.RENDER_DATABASE_ID or os.getenv("RENDER_POSTGRES_ID", "")


def owner_id() -> str:
    return (
        settings.RENDER_OWNER_ID
        or settings.RENDER_WORKSPACE_ID
        or os.getenv("RENDER_OWNER_ID", "")
        or os.getenv("RENDER_WORKSPACE_ID", "")
    )


def bytes_to_mb(value: int | float | None) -> float | None:
    if value is None:
        return None
    return round(float(value) / 1024 / 1024, 2)


def safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


class RenderClient:
    def __init__(self, *, api_key: str, base_url: str | None = None, timeout: float = 10.0) -> None:
        self.api_key = api_key.strip()
        self.base_url = (base_url or settings.RENDER_API_BASE_URL or "https://api.render.com/v1").rstrip("/")
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def get(self, path: str, params: dict[str, Any] | None = None) -> tuple[dict[str, Any] | list[Any] | None, str | None]:
        if not self.configured:
            return None, "RENDER_API_KEY saknas"
        target = f"{self.base_url}/{path.lstrip('/')}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    target,
                    params=params,
                    headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"},
                )
            if response.status_code == 404:
                return None, f"404 fran Render API for {path}"
            response.raise_for_status()
            return response.json(), None
        except Exception as exc:
            return None, clean_text(exc, limit=300)


def unwrap_items(payload: Any, keys: tuple[str, ...]) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
        for value in payload.values():
            if isinstance(value, list):
                return value
    return []


def unwrap_named(item: Any, *names: str) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    for name in names:
        nested = item.get(name)
        if isinstance(nested, dict):
            return nested
    return item


def collect_render_deploys(client: RenderClient, sid: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    if not sid:
        checks.append(check("Render deploy", "warn", "RENDER_SERVICE_ID eller RENDER_WEB_SERVICE_ID saknas."))
        return {"items": [], "error": "service_id_missing"}
    payload, error = client.get(f"/services/{sid}/deploys", {"limit": 5})
    if error:
        checks.append(check("Render deploy", "warn", f"Kunde inte hamta deploys: {error}"))
        return {"items": [], "error": error}
    deploys = [unwrap_named(item, "deploy") for item in unwrap_items(payload, ("deploys", "items", "results"))]
    simplified: list[dict[str, Any]] = []
    for deploy in deploys[:5]:
        simplified.append({
            "id": deploy.get("id"),
            "status": deploy.get("status") or deploy.get("state"),
            "trigger": deploy.get("trigger"),
            "commit": (deploy.get("commit") or {}).get("id") if isinstance(deploy.get("commit"), dict) else deploy.get("commit"),
            "created_at": deploy.get("createdAt") or deploy.get("created_at"),
            "finished_at": deploy.get("finishedAt") or deploy.get("finished_at"),
        })
    latest_status = str(simplified[0].get("status") or "").lower() if simplified else ""
    if latest_status and latest_status not in {"live", "succeeded", "success", "deployed", "available"}:
        checks.append(check("Render deploy", "warn", f"Senaste deploy har status {latest_status}."))
    else:
        checks.append(check("Render deploy", "ok" if simplified else "unknown", "Senaste deploy ser frisk ut." if simplified else "Inga deploys hittades."))
    return {"items": simplified, "error": None}


def collect_render_resource(client: RenderClient, kind: str, rid: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    if not rid:
        checks.append(check(f"Render {kind}", "warn", f"Render-id saknas for {kind}."))
        return {"resource": None, "error": "id_missing"}
    path = f"/services/{rid}" if kind == "service" else f"/postgres/{rid}"
    payload, error = client.get(path)
    if error:
        checks.append(check(f"Render {kind}", "warn", f"Kunde inte hamta {kind}: {error}"))
        return {"resource": None, "error": error}
    resource = unwrap_named(payload, kind)
    status = str(resource.get("status") or resource.get("suspended") or "ok").lower()
    ok_statuses = {"ok", "available", "running", "false", "not_suspended"}
    checks.append(check(f"Render {kind}", "ok" if status in ok_statuses else "warn", f"Render {kind} status: {status}"))
    return {"resource": resource, "error": None}


def extract_log_lines(payload: Any) -> list[str]:
    lines: list[str] = []
    for item in unwrap_items(payload, ("logs", "events", "items", "results")):
        if isinstance(item, str):
            lines.append(clean_text(item, limit=800))
            continue
        if isinstance(item, dict):
            line = item.get("message") or item.get("text") or item.get("log") or item.get("event") or item.get("summary")
            if line:
                timestamp = item.get("timestamp") or item.get("time") or item.get("createdAt") or ""
                lines.append(clean_text(f"{timestamp} {line}".strip(), limit=800))
    return [line for line in lines if line]


def service_owner_id(service: dict[str, Any] | None, fallback: str = "") -> str:
    if not isinstance(service, dict):
        return fallback
    owner = service.get("owner")
    nested_owner = owner.get("id") if isinstance(owner, dict) else ""
    return str(service.get("ownerId") or service.get("owner_id") or nested_owner or fallback or "")


def collect_render_logs(client: RenderClient, sid: str, oid: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    if not sid:
        return {"lines": [], "error": "service_id_missing"}
    if not oid:
        checks.append(check(
            "Render loggar",
            "warn",
            "Render ownerId saknas. Satt RENDER_OWNER_ID eller lat verktyget hamta service med RENDER_SERVICE_ID.",
        ))
        return {"lines": [], "error": "owner_id_missing"}
    start_time = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    attempts = (
        ("/logs", {"ownerId": oid, "resource": [sid], "type": ["build"], "direction": "backward", "startTime": start_time, "limit": 100}),
        ("/logs", {"ownerId": oid, "resource": [sid], "type": ["app"], "direction": "backward", "startTime": start_time, "limit": 100}),
        (f"/services/{sid}/events", {"limit": 100}),
    )
    errors: list[str] = []
    for path, params in attempts:
        payload, error = client.get(path, params)
        if error:
            errors.append(f"{path}: {error}")
            continue
        lines = extract_log_lines(payload)
        if lines:
            lower_lines = [line.lower() for line in lines]
            error_count = sum(any(word in line for word in ERROR_WORDS) for line in lower_lines)
            warning_count = sum(any(word in line for word in WARNING_WORDS) for line in lower_lines)
            checks.append(check(
                "Render loggar",
                "warn" if error_count else "ok",
                f"Hittade {len(lines)} loggrader, {error_count} feltraffar och {warning_count} varningar.",
                error_count=error_count,
                warning_count=warning_count,
            ))
            return {
                "lines": lines[:50],
                "error_count": error_count,
                "warning_count": warning_count,
                "source": path,
                "error": None,
            }
    checks.append(check("Render loggar", "warn", "Kunde inte hamta Render-loggar via API. Kontrollera Render API-atkomst eller komplettera med log stream.", attempts=errors[:3]))
    return {"lines": [], "error": "; ".join(errors[:3])}


def collect_render_metrics(client: RenderClient, sid: str, pid: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    metric_results: dict[str, Any] = {"service": None, "database": None, "errors": []}
    attempts = []
    if sid:
        attempts.extend((("service", f"/services/{sid}/metrics"), ("service", f"/metrics/services/{sid}")))
    if pid:
        attempts.extend((("database", f"/postgres/{pid}/metrics"), ("database", f"/metrics/postgres/{pid}")))
    for target, path in attempts:
        payload, error = client.get(path)
        if error:
            metric_results["errors"].append(f"{path}: {error}")
            continue
        metric_results[target] = payload
    if metric_results["service"] or metric_results["database"]:
        checks.append(check("Render metrics", "ok", "Render metrics kunde hamtas."))
    elif attempts:
        checks.append(check("Render metrics", "info", "Render metrics kunde inte hamtas via API. Anvand Render dashboard om API:t inte exponerar metrics for planen."))
    return metric_results


def collect_render(include_render: bool, checks: list[dict[str, Any]]) -> dict[str, Any]:
    if not include_render:
        checks.append(check("Render", "info", "Render-kontroll hoppades over."))
        return {"enabled": False}
    client = RenderClient(api_key=settings.RENDER_API_KEY)
    sid = service_id()
    pid = postgres_id()
    oid = owner_id()
    configured = {
        "api_key": bool(settings.RENDER_API_KEY),
        "service_id": bool(sid),
        "owner_id": bool(oid),
        "postgres_id": bool(pid),
    }
    if not client.configured:
        checks.append(check("Render API", "warn", "RENDER_API_KEY saknas, sa deploy/logg/metrics kan inte hamtas."))
        return {"enabled": True, "configured": configured}
    render_checks: list[dict[str, Any]] = []
    service = collect_render_resource(client, "service", sid, render_checks)
    resolved_owner_id = service_owner_id(service.get("resource") if isinstance(service, dict) else None, oid)
    configured["owner_id"] = bool(resolved_owner_id)
    database = collect_render_resource(client, "postgres", pid, render_checks) if pid else {"resource": None, "error": "postgres_id_missing"}
    deploys = collect_render_deploys(client, sid, render_checks)
    logs = collect_render_logs(client, sid, resolved_owner_id, render_checks)
    metrics = collect_render_metrics(client, sid, pid, render_checks)
    checks.extend(render_checks)
    return {
        "enabled": True,
        "configured": configured,
        "service_id": sid or None,
        "owner_id": resolved_owner_id or None,
        "postgres_id": pid or None,
        "service": service,
        "database": database,
        "deploys": deploys,
        "logs": logs,
        "metrics": metrics,
    }


def collect_database(db: Session | None, checks: list[dict[str, Any]]) -> dict[str, Any]:
    if db is None:
        checks.append(check("Databas", "info", "Databaskontroll hoppades over."))
        return {"connected": None, "skipped": True}
    started = time.perf_counter()
    try:
        db.execute(text("select 1")).scalar()
    except Exception as exc:
        checks.append(check("Databas", "error", f"Databasen svarar inte: {exc}"))
        return {"connected": False, "error": clean_text(exc)}
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    bind = db.get_bind()
    dialect = bind.dialect.name if bind is not None else "unknown"
    result: dict[str, Any] = {"connected": True, "dialect": dialect, "latency_ms": latency_ms}
    checks.append(check("Databas", "ok" if latency_ms < 500 else "warn", f"Databasen svarade pa {latency_ms} ms."))
    if dialect.startswith("postgres"):
        result.update(collect_postgres_database(db, checks))
    elif dialect == "sqlite":
        result.update(collect_sqlite_database(db, checks))
    else:
        checks.append(check("Databasstatistik", "unknown", f"Saknar detaljerad statistik for dialect {dialect}."))
    return result


def scalar(db: Session, sql: str) -> Any:
    return db.execute(text(sql)).scalar()


def collect_postgres_database(db: Session, checks: list[dict[str, Any]]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    try:
        size_bytes = int(scalar(db, "select pg_database_size(current_database())") or 0)
        data["size_mb"] = bytes_to_mb(size_bytes)
    except Exception as exc:
        data["size_error"] = clean_text(exc)
    try:
        data["max_connections"] = int(scalar(db, "show max_connections") or 0)
        conn = db.execute(text("""
            select
              count(*) as total,
              count(*) filter (where state = 'active') as active,
              count(*) filter (where wait_event is not null) as waiting
            from pg_stat_activity
            where datname = current_database()
        """)).mappings().one()
        data["connections"] = dict(conn)
        total = int(conn.get("total") or 0)
        max_conn = int(data.get("max_connections") or 0)
        if max_conn and total / max_conn >= 0.8:
            checks.append(check("Databasanslutningar", "warn", f"{total}/{max_conn} anslutningar anvands."))
        else:
            checks.append(check("Databasanslutningar", "ok", f"{total}/{max_conn or '?'} anslutningar anvands."))
    except Exception as exc:
        data["connections_error"] = clean_text(exc)
    try:
        stat = db.execute(text("""
            select tup_inserted, tup_updated, tup_deleted, blks_hit, blks_read
            from pg_stat_database
            where datname = current_database()
        """)).mappings().first()
        data["activity"] = dict(stat or {})
    except Exception as exc:
        data["activity_error"] = clean_text(exc)
    try:
        tables = db.execute(text("""
            select relname, n_live_tup, n_dead_tup, last_vacuum, last_autovacuum
            from pg_stat_user_tables
            order by n_dead_tup desc nulls last
            limit 8
        """)).mappings().all()
        data["largest_dead_tuple_tables"] = [dict(row) for row in tables]
        if tables and int(tables[0].get("n_dead_tup") or 0) > 100000:
            checks.append(check("Databas vacuum", "warn", "En tabell har manga dead tuples. Kontrollera autovacuum eller tabellstorlek."))
    except Exception as exc:
        data["tables_error"] = clean_text(exc)
    return data


def collect_sqlite_database(db: Session, checks: list[dict[str, Any]]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    try:
        page_count = int(scalar(db, "pragma page_count") or 0)
        page_size = int(scalar(db, "pragma page_size") or 0)
        freelist_count = int(scalar(db, "pragma freelist_count") or 0)
        data.update({
            "size_mb": bytes_to_mb(page_count * page_size),
            "free_mb": bytes_to_mb(freelist_count * page_size),
            "page_count": page_count,
            "page_size": page_size,
        })
        checks.append(check("SQLite", "ok", f"SQLite-filen ar {data['size_mb']} MB."))
    except Exception as exc:
        data["sqlite_error"] = clean_text(exc)
    return data


def collect_app(base_url: str | None, checks: list[dict[str, Any]]) -> dict[str, Any]:
    data: dict[str, Any] = {
        "environment": settings.ENVIRONMENT,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "public_url": base_url or settings.HEALTHCHECK_PUBLIC_URL or "",
    }
    process: dict[str, Any] = {}
    try:
        if hasattr(os, "getloadavg"):
            process["loadavg"] = [round(value, 2) for value in os.getloadavg()]
    except Exception:
        pass
    try:
        import resource

        rss_kb = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss or 0)
        # Linux reports KB, macOS bytes. Render runs Linux, but keep a guard for local tooling.
        rss_mb = rss_kb / 1024 if rss_kb < 10_000_000 else rss_kb / 1024 / 1024
        process["max_rss_mb"] = round(rss_mb, 2)
        if rss_mb >= 450:
            checks.append(check("Serverminne", "warn", f"Processen har toppat {round(rss_mb, 1)} MB RSS."))
        else:
            checks.append(check("Serverminne", "ok", f"Processen har toppat {round(rss_mb, 1)} MB RSS."))
    except Exception as exc:
        process["memory_error"] = clean_text(exc)
    data["process"] = process
    target = data["public_url"]
    if target:
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=8) as client:
                response = client.get(f"{str(target).rstrip('/')}/api/health")
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            data["public_health"] = {"status_code": response.status_code, "latency_ms": latency_ms}
            checks.append(check("Publik health", "ok" if response.status_code == 200 and latency_ms < 2000 else "warn", f"/api/health svarade {response.status_code} pa {latency_ms} ms."))
        except Exception as exc:
            data["public_health"] = {"error": clean_text(exc)}
            checks.append(check("Publik health", "warn", f"Kunde inte na publik /api/health: {exc}"))
    else:
        checks.append(check("Publik health", "info", "HEALTHCHECK_PUBLIC_URL saknas, hoppar over extern ping."))
    return data


def build_recommendations(checks: list[dict[str, Any]], report: dict[str, Any]) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []
    config = report.get("render", {}).get("configured", {}) if isinstance(report.get("render"), dict) else {}
    if config and not config.get("api_key"):
        recs.append(recommendation("warn", "Lagg RENDER_API_KEY i Render secrets for att kunna lasa deploys, loggar och metrics i Halsa."))
    if config and not config.get("service_id"):
        recs.append(recommendation("warn", "Lagg RENDER_SERVICE_ID eller RENDER_WEB_SERVICE_ID for webbservicen."))
    if config and not config.get("postgres_id"):
        recs.append(recommendation("info", "Lagg RENDER_POSTGRES_ID eller RENDER_DATABASE_ID for att kunna hamta Render-databasstatus."))
    if report.get("database", {}).get("connected") is False:
        recs.append(recommendation("error", "Databasen svarar inte. Kontrollera DATABASE_URL, Render-databasen och senaste deploy-logg."))
    render_logs = report.get("render", {}).get("logs", {}) if isinstance(report.get("render"), dict) else {}
    if int(render_logs.get("error_count") or 0) > 0:
        recs.append(recommendation("error", "Render-loggarna innehaller feltraffar. Kontrollera senaste deploy och stacktrace innan ny release."))
    deploy_items = report.get("render", {}).get("deploys", {}).get("items", []) if isinstance(report.get("render"), dict) else []
    if deploy_items:
        latest_status = str(deploy_items[0].get("status") or "").lower()
        if latest_status and latest_status not in {"live", "succeeded", "success", "deployed", "available"}:
            recs.append(recommendation("error", f"Senaste deploy ar inte frisk ({latest_status}). Oppna deploy-loggen i Render."))
    rss_mb = safe_float(report.get("app", {}).get("process", {}).get("max_rss_mb"))
    if rss_mb is not None and rss_mb >= 450:
        recs.append(recommendation("warn", "Serverprocessen ligger hogt i minne. Jamfor med Render-planens grans och undersok cache/prefetch-volym."))
    db = report.get("database", {})
    conn = db.get("connections") or {}
    max_conn = int(db.get("max_connections") or 0)
    total_conn = int(conn.get("total") or 0)
    if max_conn and total_conn / max_conn >= 0.8:
        recs.append(recommendation("warn", "Databasen ligger nara max anslutningar. Undersok connection pooling eller storre databasplan."))
    if not recs:
        recs.append(recommendation("ok", "Inga akuta atgarder hittades i de kontroller som kunde koras."))
    return recs


def run_healthcheck(
    *,
    db: Session | None = None,
    include_render: bool = True,
    base_url: str | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "generated_at": utc_now_iso(),
        "app": collect_app(base_url, checks),
        "database": collect_database(db, checks),
        "render": collect_render(include_render, checks),
    }
    report["checks"] = checks
    report["status"] = worst_status(checks)
    report["recommendations"] = build_recommendations(checks, report)
    return report

from __future__ import annotations

import os
import platform
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from .background import background_job_status
from .config import settings


PROCESS_MEMORY_WARN_MB = 1536
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

        current_rss_mb = None
        statm_path = "/proc/self/statm"
        if os.path.exists(statm_path):
            try:
                with open(statm_path, encoding="utf-8") as handle:
                    parts = handle.read().split()
                rss_pages = int(parts[1]) if len(parts) > 1 else 0
                current_rss_mb = rss_pages * os.sysconf("SC_PAGE_SIZE") / 1024 / 1024
            except (OSError, ValueError, IndexError):
                current_rss_mb = None
        rss_kb = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss or 0)
        # Linux reports KB, macOS bytes. Servern kor Linux, but keep a guard for local tooling.
        rss_mb = rss_kb / 1024 if rss_kb < 10_000_000 else rss_kb / 1024 / 1024
        process["max_rss_mb"] = round(rss_mb, 2)
        if current_rss_mb is not None:
            process["current_rss_mb"] = round(current_rss_mb, 2)
        if rss_mb >= PROCESS_MEMORY_WARN_MB:
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
    if report.get("database", {}).get("connected") is False:
        recs.append(recommendation("error", "Databasen svarar inte. Kontrollera DATABASE_URL, databaspodden och senaste deploy-logg."))
    rss_mb = safe_float(report.get("app", {}).get("process", {}).get("max_rss_mb"))
    if rss_mb is not None and rss_mb >= PROCESS_MEMORY_WARN_MB:
        recs.append(recommendation("warn", "Serverprocessen ligger hogt i minne. Jamfor med poddens memory-limit och undersok cache/prefetch-volym."))
    db = report.get("database", {})
    conn = db.get("connections") or {}
    max_conn = int(db.get("max_connections") or 0)
    total_conn = int(conn.get("total") or 0)
    if max_conn and total_conn / max_conn >= 0.8:
        recs.append(recommendation("warn", "Databasen ligger nara max anslutningar. Undersok connection pooling eller storre databasplan."))
    if not recs:
        recs.append(recommendation("ok", "Inga akuta atgarder hittades i de kontroller som kunde koras."))
    return recs


def collect_schedule_freeze(db: Session | None, checks: list[dict[str, Any]]) -> dict[str, Any]:
    """Frysgransens efterslapning - guardrail mot att historiken tyst blir mutabel igen.

    Bakgrundsjobbet fangar sina egna fel och fortsatter loopa, sa ett trasigt
    frysjobb skulle annars aldrig synas: `state` forblir "running" medan
    veckomallen ater borjar rita om gardagen. Halkar `frozen_until` efter
    gardagen ar frysningen i praktiken ur funktion.
    """
    if db is None:
        checks.append(check("Schemafrysning", "info", "Frysningskontroll hoppades over."))
        return {"skipped": True}
    try:
        from .models import ScheduleCell, ScheduleFreezeState

        row = db.get(ScheduleFreezeState, 1)
        has_schedule_data = db.query(ScheduleCell.id).limit(1).first() is not None
    except Exception as exc:
        checks.append(check("Schemafrysning", "unknown", f"Kunde inte lasa frysgransen: {clean_text(exc)}"))
        return {"error": clean_text(exc)}

    frozen_until = row.frozen_until if row is not None else None
    yesterday = datetime.now(ZoneInfo("Europe/Stockholm")).date() - timedelta(days=1)
    result: dict[str, Any] = {
        "frozen_until": frozen_until.isoformat() if frozen_until else None,
        "expected_until": yesterday.isoformat(),
    }
    if frozen_until is None:
        # Tom databas (lokal dev, nyuppsatt miljo): det finns ingen historik att
        # skydda an, sa avsaknaden av frysgrans ar information - inte ett fel.
        if not has_schedule_data:
            checks.append(
                check("Schemafrysning", "info", "Ingen schemahistorik att frysa an.", **result)
            )
            return result
        checks.append(
            check(
                "Schemafrysning",
                "warn",
                "Schemahistoriken ar inte fryst an. Tills jobbet kort om ritar veckomallen om forflutna dagar.",
                **result,
            )
        )
        return result
    lag_days = (yesterday - frozen_until).days
    result["lag_days"] = lag_days
    if lag_days > 0:
        checks.append(
            check(
                "Schemafrysning",
                "warn",
                f"Frysgransen ligger {lag_days} dag(ar) efter. Ofrysta dagar kan fortfarande ritas om av registerandringar.",
                **result,
            )
        )
    else:
        checks.append(
            check("Schemafrysning", "ok", f"Schemahistoriken ar fryst till {frozen_until.isoformat()}.", **result)
        )
    return result


def collect_background_jobs(checks: list[dict[str, Any]]) -> dict[str, Any]:
    jobs = background_job_status()
    failed = sorted(name for name, entry in jobs.items() if entry.get("state") == "error")
    if failed:
        checks.append(check("Bakgrundsjobb", "warn", "Bakgrundsjobb med fel: " + ", ".join(failed) + "."))
    elif jobs:
        checks.append(check("Bakgrundsjobb", "ok", f"{len(jobs)} bakgrundsjobb registrerade utan fel."))
    else:
        checks.append(check("Bakgrundsjobb", "info", "Inga bakgrundsjobb registrerade i den här processen."))
    return jobs


DUCKDB_CHECK_NAME = "DuckDB (arkivcache)"
# Mätpunkten för #08 är INFORMATION, inte ett hälsoutslag - därför är den här statusen
# hårdkodad och får aldrig härledas ur verdicts. status_rank("info") == status_rank("ok")
# == 0, så en info-check kan aldrig lyfta worst_status(checks) och alltså aldrig ändra
# rapportens globala status. Det är avsiktligt och skyddat av
# tests/services/test_duckdb_diagnostics.py::test_pod_shaped_measurement_never_changes_the_global_status:
# i podden läser DuckDB värdens defaults (många trådar, jättelik memory_limit) och
# verdicts blir "warn". Skrevs den warnen in i checks skulle GET /api/healthcheck flippa
# permanent från ok till warn för Super User i Historik/Hälsa - en mätning som ändrar vad
# användaren ser, och en permanent warn som desensibiliserar hela hälsovyn (AGENTS.md
# hälsoregel). Bedömningarna finns kvar i topplevel-fältet report["duckdb"] (verdicts +
# verdict_status) och läses med `python -m tools.healthcheck duckdb`.
DUCKDB_CHECK_STATUS = "info"


def duckdb_information_check(message: str, **details: Any) -> dict[str, Any]:
    """Enda vägen in i ``checks`` för DuckDB-mätpunkten - statusen kan inte eskalera."""
    return check(DUCKDB_CHECK_NAME, DUCKDB_CHECK_STATUS, f"Mätpunkt (#08, påverkar inte hälsostatus): {message}", **details)


def collect_duckdb(checks: list[dict[str, Any]]) -> dict[str, Any]:
    """Mätpunkt för optimeringskandidat #08: vilka defaults valde DuckDB i den här podden?

    Läser bara ``current_setting(...)`` mot arkivcachens egen anslutningsväg
    (``local_archive_store._connect``, in-memory) plus cgroup-/värdfakta - inga rader,
    inga tenant-filer, inga lås. Se ``app/backend/duckdb_diagnostics.py``. Ligger här
    därför att Emir saknar kubectl-åtkomst: det enda sättet att läsa poddens
    DuckDB-defaults är via den befintliga Super User-endpointen ``GET /api/healthcheck``.

    Två gränser: (1) den skriver bara en icke-eskalerande info-check (se
    ``DUCKDB_CHECK_STATUS``), och (2) den är gate:ad på ``local_archive_store.is_enabled()``
    - är arkivcachen av öppnar appen aldrig DuckDB, och då ska healthchecken inte uttala
    sig om en anslutning som inte finns.
    """
    try:
        from .local_archive_store import is_enabled as archive_cache_enabled

        enabled = archive_cache_enabled()
    except Exception as exc:  # noqa: BLE001 - diagnostiken får aldrig fälla healthchecken
        return {"available": False, "error": clean_text(exc)}

    if not enabled:
        return {
            "available": False,
            "archive_cache_enabled": False,
            "reason": (
                "Arkivcachen är avstängd (ARCHIVE_CACHE_ENABLED=0) - appen öppnar aldrig "
                "DuckDB i den här processen, så det finns ingen anslutning att mäta."
            ),
        }

    try:
        from .duckdb_diagnostics import duckdb_diagnostics

        report = duckdb_diagnostics()
    except Exception as exc:  # noqa: BLE001 - diagnostiken får aldrig fälla healthchecken
        checks.append(duckdb_information_check(f"DuckDB-diagnostiken kunde inte köras: {exc}"))
        return {"available": False, "archive_cache_enabled": True, "error": clean_text(exc)}

    report["archive_cache_enabled"] = True
    verdicts = report.get("verdicts") or []
    verdict_status = worst_status(verdicts)
    report["verdict_status"] = verdict_status

    if not report.get("available"):
        checks.append(
            duckdb_information_check(
                f"DuckDB kunde inte läsas i den här processen: {report.get('error') or 'okänd orsak'}",
                verdict_status=verdict_status,
            )
        )
        return report

    settings_map = report.get("settings") or {}
    summary = (
        f"DuckDB {report.get('version') or '?'}: threads={settings_map.get('threads', '?')}, "
        f"memory_limit={settings_map.get('memory_limit', '?')}. "
        + " ".join(str(item.get("message") or "") for item in verdicts)
    )
    checks.append(
        duckdb_information_check(
            summary,
            version=report.get("version"),
            threads=settings_map.get("threads"),
            memory_limit=settings_map.get("memory_limit"),
            verdict_status=verdict_status,
            verdicts=verdicts,
            cgroup=report.get("cgroup"),
            host=report.get("host"),
        )
    )
    return report


def run_healthcheck(
    *,
    db: Session | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "generated_at": utc_now_iso(),
        "app": collect_app(base_url, checks),
        "database": collect_database(db, checks),
        "background_jobs": collect_background_jobs(checks),
        "schedule_freeze": collect_schedule_freeze(db, checks),
        "duckdb": collect_duckdb(checks),
    }
    report["checks"] = checks
    report["status"] = worst_status(checks)
    report["recommendations"] = build_recommendations(checks, report)
    return report

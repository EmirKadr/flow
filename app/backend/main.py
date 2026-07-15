from contextlib import asynccontextmanager
from pathlib import Path
import hashlib
import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response

from . import allocation_bridge, background, demo_session, leader_lock
from .business_scope import DEFAULT_BUSINESS_CODE, normalize_business_code
from .config import settings
from .database import SessionLocal, engine
from .models import Business
from .observability import (
    add_span_attributes,
    begin_request_trace,
    configure_observability,
    current_operation_id,
    current_trace_id,
    emit_flow_event,
    end_request_trace,
    start_span,
)
from .archive_cache_sync import start_archive_cache_scheduler
from .productivity_sync import start_productivity_sync_scheduler
from .routers import (
    activities,
    allocation,
    areas,
    assistant,
    audit_logs,
    auth,
    bug_reports,
    bulk,
    businesses,
    coredata,
    data_fetch,
    data_fetch_diagnostics,
    healthcheck,
    meta_uploads,
    mcp,
    overview,
    person_schedules,
    persons,
    personal,
    productivity,
    public,
    rfid,
    sankey,
    schedule,
    settings as app_settings,
    users,
    workflow_data,
)

def _run_startup_migrations() -> None:
    """Kör alembic upgrade head vid appstart mot delade databaser.

    SQLite (lokal dev) äger sitt schema via bootstrap_local och hoppas över.
    Utan detta steg driftar deployade databaser ifrån modellerna så fort en
    migration landar utan att någon kör alembic manuellt (jfr schedule_cells.remark
    som saknades i MSSQL och gav 'Invalid column name'-krascher i produktion).
    Stängs av med RUN_DB_MIGRATIONS_ON_START=0.
    """
    import os

    if engine.dialect.name == "sqlite":
        return
    if os.getenv("RUN_DB_MIGRATIONS_ON_START", "1").lower() in {"0", "false", "no"}:
        return
    try:
        from alembic import command
        from alembic.config import Config

        app_dir = Path(__file__).resolve().parents[1]
        config = Config(str(app_dir / "alembic.ini"))
        # script_location i ini:n ar relativ cwd; peka absolut sa det funkar i containern.
        config.set_main_option("script_location", str(app_dir / "alembic"))
        command.upgrade(config, "head")
        logging.getLogger(__name__).info("Alembic-migrationer uppgraderade till head.")
    except Exception:
        logging.getLogger(__name__).error(
            "Alembic-migrering vid start misslyckades - schemat kan drifta.", exc_info=True
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Kör migrationer och startar alla registrerade bakgrundsjobb vid appstart."""
    import os

    _run_startup_migrations()
    # Testsviter sätter FLOW_DISABLE_BACKGROUND_JOBS=1 så att in-process-servrar
    # (browser-/desktop-tester) inte startar schemaläggare som gör riktiga
    # nätverksanrop och håller produktivitetssyncens lås över andra tester.
    if os.getenv("FLOW_DISABLE_BACKGROUND_JOBS", "").lower() not in {"1", "true", "yes"}:
        if os.getenv("FLOW_DISABLE_LEADER_LOCK", "").lower() in {"1", "true", "yes"}:
            background.start_background_jobs(BACKGROUND_JOBS)
        else:
            # Endast ledaren startar jobben. Med en worker (dagens deploy) blir
            # processen ledare direkt; med flera workers skyddar laset mot
            # dubbelkorning av schedulers och sync-jobb.
            leader_lock.start_leader_gated(
                lambda: background.start_background_jobs(BACKGROUND_JOBS)
            )
    yield


app = FastAPI(title="flow", version="0.1.5", lifespan=lifespan)
logger = logging.getLogger(__name__)
configure_observability(app, engine=engine)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="flow_session",
    https_only=settings.is_production,
    same_site="lax",
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Grundläggande säkerhetsheaders på alla svar.

    HSTS sätts bara när requesten bevisligen gick över https (direkt eller via
    ingressens X-Forwarded-Proto) — dev och desktop kör http och ska inte få
    webbläsare att tvinga https mot localhost. CSP är medvetet INTE med här:
    frontendens inline-scripts kräver en genomtänkt policy (se NIGHTLY_NOTES).
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    if request.url.scheme == "https" or forwarded_proto == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return response


@app.middleware("http")
async def trace_context_middleware(request: Request, call_next):
    token = begin_request_trace(request.headers)
    started = time.perf_counter()
    try:
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000
            _log_request_observability(request, 500, duration_ms, failed=True)
            raise
        duration_ms = (time.perf_counter() - started) * 1000
        route = _request_route(request)
        add_span_attributes(
            {
                "flow.http_route": route,
                "flow.http_status_code": response.status_code,
                "flow.http_duration_ms": round(duration_ms, 2),
                "flow.endpoint_group": _endpoint_group(route),
            }
        )
        trace_id = current_trace_id()
        if trace_id:
            response.headers["X-Flow-Trace-Id"] = trace_id
        operation_id = current_operation_id()
        if operation_id:
            response.headers["X-Flow-Operation-Id"] = operation_id
        _log_request_observability(request, response.status_code, duration_ms, route=route)
        return response
    finally:
        end_request_trace(token)


def _request_route(request: Request) -> str:
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    if template:
        return str(template)
    return str(request.url.path)


def _endpoint_group(route: str) -> str:
    parts = [part for part in str(route or "").split("/") if part]
    if len(parts) >= 2 and parts[0] == "api":
        return parts[1]
    return parts[0] if parts else "root"


def _should_log_request(request: Request, status_code: int) -> bool:
    if not settings.OTEL_REQUEST_LOG_ENABLED:
        return False
    path = request.url.path
    if path == "/api/health" or path.startswith("/api/healthcheck/wait-metrics"):
        return status_code >= 400
    return path.startswith("/api/") or status_code >= 500


def _log_request_observability(
    request: Request,
    status_code: int,
    duration_ms: float,
    *,
    route: str | None = None,
    failed: bool = False,
) -> None:
    if not _should_log_request(request, status_code):
        return
    route = route or _request_route(request)
    level = logging.ERROR if failed or status_code >= 500 else logging.WARNING if status_code >= 400 else logging.INFO
    emit_flow_event(
        "flow.http.request",
        feature=_endpoint_group(route),
        outcome="failed" if failed or status_code >= 500 else "blocked" if status_code >= 400 else "ok",
        level=level,
        event_alias="http_request",
        logger_=logger,
        attributes={
            "http_method": request.method,
            "http_route": route,
            "http_status_code": status_code,
            "duration_ms": round(duration_ms, 2),
            "endpoint_group": _endpoint_group(route),
        },
        exc_info=failed,
        message=f"Flow API {request.method} {route} -> {status_code} in {duration_ms:.0f} ms",
    )


# Statiska filer: HTML revalideras alltid (billiga 304 via StaticFiles ETag);
# JS/CSS m.fl. med ?v=<innehålls-hash> (stämplas i Docker-bygget av
# tools/stamp_asset_versions.py) cachas i ett år — URL:en byter när innehållet
# byter, så ingen kan köra gammal frontend mot nytt API.
_IMMUTABLE_STATIC_SUFFIXES = (".js", ".css", ".svg", ".png", ".ico", ".woff", ".woff2")


@app.middleware("http")
async def static_cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/api/"):
        return response
    if not settings.is_production:
        if path.endswith((".html", ".js", ".css")):
            response.headers["Cache-Control"] = "no-store"
        return response
    if path.endswith(".html") or path == "/":
        response.headers["Cache-Control"] = "no-cache"
    elif path.endswith(_IMMUTABLE_STATIC_SUFFIXES):
        if request.query_params.get("v"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
    return response


@app.middleware("http")
async def demo_session_context_middleware(request: Request, call_next):
    """Sätt demo_data_root_var per request så filsystem-IO routas till sandbox."""
    try:
        demo_id = request.session.get("demo_session_id")
    except Exception:
        demo_id = None
    if demo_id and demo_session.session_exists(demo_id):
        token = demo_session.demo_data_root_var.set(demo_session.demo_data_root(demo_id))
    else:
        token = demo_session.demo_data_root_var.set(None)
    try:
        return await call_next(request)
    finally:
        demo_session.demo_data_root_var.reset(token)


@app.middleware("http")
async def api_get_etag(request: Request, call_next):
    """Svag ETag på API-GET-JSON: oförändrat innehåll ger 304 utan payload.

    Webbläsaren revalideras (private, no-cache) i stället för att ladda om hela
    svaret — kombinerat med frontendens GET-cache kostar ett oförändrat svar en
    RTT i stället för hela överföringen. Strömmande svar (SSE, filer) och
    no-store-svar lämnas orörda.
    """
    response = await call_next(request)
    if (
        request.method != "GET"
        or not request.url.path.startswith("/api/")
        or response.status_code != 200
        or not response.headers.get("content-type", "").startswith("application/json")
        or "no-store" in response.headers.get("cache-control", "")
    ):
        return response

    body = b"".join([chunk async for chunk in response.body_iterator])
    etag = f'W/"{hashlib.sha256(body).hexdigest()[:32]}"'
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=304,
            headers={"ETag": etag, "Cache-Control": "private, no-cache"},
            background=response.background,
        )
    headers = dict(response.headers)
    headers["ETag"] = etag
    headers.setdefault("cache-control", "private, no-cache")
    return Response(
        content=body,
        status_code=response.status_code,
        headers=headers,
        background=response.background,
    )


# Läggs till sist = ytterst i middleware-kedjan: komprimerar både API-JSON och
# statiska JS/CSS-svar (60-80 % mindre payload). Starlette undantar
# text/event-stream automatiskt, så SSE-progressströmmarna påverkas inte.
#
# compresslevel=6 sätts EXPLICIT: Starlettes default är 9, den dyraste
# zlib-nivån, och GZipResponder komprimerar synkront i ASGI-send-vägen — alltså
# på event-loopen i vår enda uvicorn-worker. Nivå 9 kostar 3-4x CPU mot nivå 6
# för nästan identisk storlek. Nivån är ren transportkodning: gzip-strömmen är
# självbeskrivande och ETag hashas på den OKOMPRIMERADE bodyn (api_get_etag
# ligger innanför denna middleware), så bytet är beteendebevarande.
# Kontraktstest: tests/services/test_http_delivery.py.
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=6)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "environment": settings.ENVIRONMENT}


@app.get("/stallen.html", include_in_schema=False)
@app.get("/stallen", include_in_schema=False)
def legacy_activities_page_redirect() -> RedirectResponse:
    return RedirectResponse(
        url="/aktiviteter.html",
        status_code=308,
        headers={"Cache-Control": "no-store"},
    )


@app.get("/meta", include_in_schema=False)
@app.get("/meta-upload", include_in_schema=False)
def public_meta_upload_page_redirect() -> RedirectResponse:
    return RedirectResponse(
        url="/meta-upload.html",
        status_code=308,
        headers={"Cache-Control": "no-store"},
    )


def _sync_allocation_observations_background() -> None:
    with start_span("background.allocation_observations_sync"):
        if not settings.ALLOCATION_OBSERVATIONS_STARTUP_SYNC:
            return
        delay_seconds = max(0.0, float(settings.ALLOCATION_OBSERVATIONS_STARTUP_DELAY_SECONDS or 0))
        spacing_seconds = max(0.0, float(settings.ALLOCATION_OBSERVATIONS_STARTUP_SPACING_SECONDS or 0))
        if delay_seconds:
            time.sleep(delay_seconds)
        try:
            engine_module, _flows_module = allocation_bridge.require_available()
        except Exception:
            logger.warning("Allocation observations startup sync could not load warehouse tools.", exc_info=True)
            return

        for index, business_code in enumerate(_allocation_observation_business_codes()):
            if index and spacing_seconds:
                time.sleep(spacing_seconds)
            try:
                engine_module.fetch_observations_from_github(business_code=business_code)
            except Exception:
                logger.warning("Allocation observations startup sync failed for %s.", business_code, exc_info=True)


def _allocation_observation_business_codes() -> list[str]:
    try:
        db = SessionLocal()
    except Exception:
        logger.warning("Could not open database session for allocation observations startup sync.", exc_info=True)
        return [DEFAULT_BUSINESS_CODE]
    try:
        rows = (
            db.query(Business.code)
            .filter(Business.is_active)
            .order_by(Business.sort_order, Business.id)
            .all()
        )
    except Exception:
        logger.warning("Could not load active businesses for allocation observations startup sync.", exc_info=True)
        return [DEFAULT_BUSINESS_CODE]
    finally:
        db.close()

    codes = []
    seen = set()
    for row in rows:
        try:
            raw_code = row[0]
        except Exception:
            raw_code = getattr(row, "code", row)
        code = normalize_business_code(raw_code)
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    return codes or [DEFAULT_BUSINESS_CODE]


def _start_productivity_sync_scheduler_job() -> None:
    with start_span("background.productivity_sync_startup"):
        start_productivity_sync_scheduler()


def _start_archive_cache_scheduler_job() -> None:
    # Lokal DuckDB-arkivcache (endast dev, gate:at i start_archive_cache_scheduler).
    with start_span("background.archive_cache_startup"):
        start_archive_cache_scheduler()


def _cleanup_stale_demo_sessions_job() -> None:
    demo_session.cleanup_stale_demo_sessions(settings.DEMO_SESSION_MAX_AGE_HOURS)


def _purge_expired_bug_reports_background() -> None:
    with start_span("background.bug_reports_retention_purge"):
        try:
            from .routers.bug_reports import purge_expired_bug_reports

            db = SessionLocal()
            try:
                purge_expired_bug_reports(db)
            finally:
                db.close()
        except Exception:
            logger.warning("Bug report retention purge failed at startup.", exc_info=True)


def _purge_expired_meta_media_background() -> None:
    with start_span("background.meta_media_retention_purge"):
        try:
            from .meta_analysis_service import purge_expired_meta_media

            purge_expired_meta_media()
        except Exception:
            logger.warning("Meta media retention purge failed at startup.", exc_info=True)


# Alla uppstartsjobb registreras här och startas av lifespan via background-runnern.
# Nya bakgrundsjobb ska in i den här listan, inte som egna trådar eller startup-hooks.
BACKGROUND_JOBS = [
    background.BackgroundJob(
        name="allocation_observations_sync",
        run=_sync_allocation_observations_background,
        description="Hämtar allokeringsobservationer från GitHub efter uppstart.",
    ),
    background.BackgroundJob(
        name="productivity_snapshot_scheduler",
        run=_start_productivity_sync_scheduler_job,
        description="Startar Produktivitetens snapshot-scheduler (hel-/halvtimme + backfill).",
        in_thread=False,
    ),
    background.BackgroundJob(
        name="archive_cache_scheduler",
        run=_start_archive_cache_scheduler_job,
        description="Startar lokala DuckDB-arkivcachens scheduler (endast dev).",
        in_thread=False,
    ),
    background.BackgroundJob(
        name="demo_session_cleanup",
        run=_cleanup_stale_demo_sessions_job,
        description="Rensar gamla demo-sandboxar vid uppstart.",
        in_thread=False,
    ),
    background.BackgroundJob(
        name="meta_media_retention_purge",
        run=_purge_expired_meta_media_background,
        description="Rensar utgången meta-media vid uppstart.",
    ),
    background.BackgroundJob(
        name="bug_reports_retention_purge",
        run=_purge_expired_bug_reports_background,
        description="Rensar buggrapporter äldre än retentionen vid uppstart.",
    ),
]


app.include_router(auth.router)
app.include_router(allocation.router)
app.include_router(bug_reports.router)
app.include_router(assistant.router)
app.include_router(businesses.router)
app.include_router(areas.router)
app.include_router(activities.router)
app.include_router(audit_logs.router)
app.include_router(persons.router)
app.include_router(person_schedules.router)
app.include_router(personal.router)
app.include_router(schedule.router)
app.include_router(bulk.router)
app.include_router(coredata.router)
app.include_router(data_fetch.router)
app.include_router(data_fetch_diagnostics.router)
app.include_router(healthcheck.router)
app.include_router(meta_uploads.router)
app.include_router(mcp.router)
app.include_router(overview.router)
app.include_router(productivity.router)
app.include_router(sankey.router)
app.include_router(app_settings.router)
app.include_router(users.router)
app.include_router(workflow_data.router)
app.include_router(public.router)
app.include_router(rfid.router)


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

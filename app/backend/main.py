from contextlib import asynccontextmanager
from pathlib import Path
import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import allocation_bridge, background, demo_session
from .business_scope import DEFAULT_BUSINESS_CODE, normalize_business_code
from .config import settings
from .database import SessionLocal, engine
from .models import Business
from .observability import begin_request_trace, configure_observability, current_trace_id, end_request_trace, start_span
from .archive_cache_sync import start_archive_cache_scheduler
from .productivity_sync import start_productivity_sync_scheduler
from .routers import (
    activities,
    allocation,
    areas,
    assistant,
    audit_logs,
    auth,
    bulk,
    businesses,
    coredata,
    data_fetch,
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
        background.start_background_jobs(BACKGROUND_JOBS)
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
async def trace_context_middleware(request: Request, call_next):
    token = begin_request_trace(request.headers)
    try:
        response = await call_next(request)
        trace_id = current_trace_id()
        if trace_id:
            response.headers["X-Flow-Trace-Id"] = trace_id
        return response
    finally:
        end_request_trace(token)


@app.middleware("http")
async def prevent_stale_static_cache_in_development(request: Request, call_next):
    response = await call_next(request)
    if not settings.is_production and request.url.path.endswith((".html", ".js", ".css")):
        response.headers["Cache-Control"] = "no-store"
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
]


app.include_router(auth.router)
app.include_router(allocation.router)
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

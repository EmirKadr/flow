from pathlib import Path
import threading

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import allocation_bridge, demo_session
from .business_scope import DEFAULT_BUSINESS_CODE, R3_BUSINESS_CODE
from .config import settings
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
    overview,
    person_schedules,
    persons,
    productivity,
    public,
    schedule,
    settings as app_settings,
    users,
)

app = FastAPI(title="flow", version="0.1.2")

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="flow_session",
    https_only=settings.is_production,
    same_site="lax",
)


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


def _sync_allocation_observations_background() -> None:
    try:
        engine_module, _flows_module = allocation_bridge.require_available()
        for business_code in (DEFAULT_BUSINESS_CODE, R3_BUSINESS_CODE):
            engine_module.fetch_observations_from_github(business_code=business_code)
    except Exception:
        return


@app.on_event("startup")
def sync_allocation_observations_on_startup() -> None:
    threading.Thread(
        target=_sync_allocation_observations_background,
        name="AllocationObservationsSync",
        daemon=True,
    ).start()


@app.on_event("startup")
def cleanup_stale_demo_sessions_on_startup() -> None:
    try:
        demo_session.cleanup_stale_demo_sessions(settings.DEMO_SESSION_MAX_AGE_HOURS)
    except Exception:
        pass


app.include_router(auth.router)
app.include_router(allocation.router)
app.include_router(assistant.router)
app.include_router(businesses.router)
app.include_router(areas.router)
app.include_router(activities.router)
app.include_router(audit_logs.router)
app.include_router(persons.router)
app.include_router(person_schedules.router)
app.include_router(schedule.router)
app.include_router(bulk.router)
app.include_router(coredata.router)
app.include_router(data_fetch.router)
app.include_router(healthcheck.router)
app.include_router(overview.router)
app.include_router(productivity.router)
app.include_router(app_settings.router)
app.include_router(users.router)
app.include_router(public.router)


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

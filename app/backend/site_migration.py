"""Retire the old public origin while keeping the standalone D-pak chat usable."""
from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse


LEGACY_HOSTS = frozenset({"stigamo.nu", "www.stigamo.nu"})
TARGET_ORIGIN = "https://flow.nowastelogistics.com"
MOVED_MESSAGE = f"flow har flyttat. Öppna {TARGET_ORIGIN} för att fortsätta."

DPAK_PAGES = frozenset({"/d-pak", "/d-pak/", "/dpak-fraga.html"})
DPAK_ASSETS = frozenset({
    "/css/styles.css",
    "/js/public_dpak_chat.js",
    "/assets/nowaste-logo.png",
    "/assets/mestergruppen-logo.png",
    "/favicon.svg",
    "/favicon.ico",
    "/app-icon-192.png",
    "/app-icon-512.png",
    "/manifest.webmanifest",
})


def migration_status(hostname: str | None) -> dict:
    applies = (hostname or "").lower().rstrip(".") in LEGACY_HOSTS
    return {
        "active": applies,
        "target_origin": TARGET_ORIGIN,
    }


def is_exempt(path: str, method: str) -> bool:
    if method in {"GET", "HEAD"}:
        return path in DPAK_PAGES | DPAK_ASSETS | {
            "/api/health",
            "/api/site-migration",
            "/api/public/dpak-chat/status",
            "/js/site_migration.js",
        }
    return method == "POST" and path == "/api/public/dpak-chat/message"


async def enforce_site_migration(request: Request, call_next):
    state = migration_status(request.url.hostname)
    path = request.url.path
    if not state["active"] or is_exempt(path, request.method):
        response = await call_next(request)
        if state["active"]:
            response.headers["Cache-Control"] = "no-store"
        return response

    headers = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
    if request.method in {"GET", "HEAD"} and not (path == "/api" or path.startswith("/api/")):
        raw_path = request.scope.get("raw_path", b"/").decode("ascii")
        target = TARGET_ORIGIN + "/" + raw_path.lstrip("/")
        if request.url.query:
            target += "?" + request.url.query
        return RedirectResponse(target, status_code=302, headers=headers)

    # Never replay writes, credentials or uploads automatically across origins.
    return JSONResponse(
        {"detail": MOVED_MESSAGE, "code": "site_moved", "target_origin": TARGET_ORIGIN},
        status_code=410,
        headers=headers,
    )

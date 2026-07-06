"""Behörighetssvep: varje /api-rutt måste avvisa oautentiserade anrop.

Skyddet per endpoint vilar på att någon kom ihåg require_view_access/
require_super_user-dependencyn — en bortglömd dependency är osynlig tills
någon hittar den. Det här testet gör den till ett rött test: alla rutter
utom den granskade vitlistan ska svara 401/403 utan session.

Vitlistan är exakta (metod, path)-par. En ny publik endpoint kräver alltså
ett aktivt beslut här — och en vitlistepost vars rutt försvunnit failar
(staleness-guard), så listan kan inte växa igen obemärkt.
"""
import re

from fastapi.testclient import TestClient

from app.backend.main import app
from tests.tools.test_api_route_contracts import _iter_flat_routes

# Medvetet publika endpoints (verifierade 2026-07-06). "Publik" betyder inte
# oskyddad: de bär eget skydd (tokenparametrar, rate limiting) eller är
# definitionsmässigt öppna (login). Kommentera varje post.
PUBLIC_ALLOWLIST: dict[tuple[str, str], str] = {
    ("GET", "/api/health"): "k8s-probes och post_deploy_check, ingen data",
    ("POST", "/api/auth/login"): "inloggning är per definition oautentiserad",
    ("POST", "/api/auth/logout"): "no-op utan session (204), röjer inget",
    ("POST", "/api/auth/set-password"): None,  # kräver session -> ska INTE vitlistas
    ("GET", "/api/public/hours"): "publikt export-API, skyddat av EXCEL_API_TOKEN-param",
    ("GET", "/api/public/hours/week"): "publikt export-API, skyddat av EXCEL_API_TOKEN-param",
    ("GET", "/api/public/persons"): "publikt export-API, skyddat av EXCEL_API_TOKEN-param",
    ("GET", "/api/public/persons/week"): "publikt export-API, skyddat av EXCEL_API_TOKEN-param",
    ("GET", "/api/public/summary"): "publikt export-API, skyddat av EXCEL_API_TOKEN-param",
    ("GET", "/api/public/summary/week"): "publikt export-API, skyddat av EXCEL_API_TOKEN-param",
    ("POST", "/api/audit/interactions/public"): "telemetri från publika sidor (meta-upload)",
    ("POST", "/api/meta/uploads"): "publik mobiluppladdning, egen rate limiting",
    ("POST", "/api/rfid/scans"): "ESP32-enheter postar utan session (LAN + enhetsfält)",
}
# Poster med värdet None är dokumenterade avslag: de får ALDRIG bli publika.
FORBIDDEN_IN_ALLOWLIST = {key for key, why in PUBLIC_ALLOWLIST.items() if why is None}
ALLOWLIST = {key for key, why in PUBLIC_ALLOWLIST.items() if why is not None}


def _fill_path_params(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


def _api_routes() -> list[tuple[str, str]]:
    routes: list[tuple[str, str]] = []
    for prefix, route in _iter_flat_routes(app.routes):
        path = prefix + getattr(route, "path", "")
        if not path.startswith("/api/"):
            continue
        methods = set(getattr(route, "methods", set()) or set()) - {"HEAD", "OPTIONS"}
        routes.extend((method, path) for method in sorted(methods))
    return sorted(set(routes))


def test_all_api_routes_reject_unauthenticated_requests():
    client = TestClient(app, raise_server_exceptions=False)
    leaks: list[str] = []

    for method, path in _api_routes():
        if (method, path) in ALLOWLIST:
            continue
        response = client.request(method, _fill_path_params(path))
        if response.status_code not in (401, 403):
            leaks.append(f"{method} {path} -> {response.status_code}")

    assert leaks == [], (
        "Rutter som inte avvisar oautentiserade anrop (401/403). Är endpointen "
        "avsiktligt publik: vitlista den med motivering i PUBLIC_ALLOWLIST. "
        f"Annars saknas en auth-dependency: {leaks}"
    )


def test_allowlist_entries_still_exist():
    """Staleness-guard: vitlisteposter för borttagna rutter ska städas bort."""
    existing = set(_api_routes())
    stale = sorted(f"{m} {p}" for m, p in (ALLOWLIST | FORBIDDEN_IN_ALLOWLIST) - existing)
    assert stale == [], f"Vitlisteposter utan motsvarande rutt: {stale}"


def test_forbidden_entries_actually_require_auth():
    """Dokumenterade avslag (None-poster) måste förbli skyddade."""
    client = TestClient(app, raise_server_exceptions=False)
    broken = []
    for method, path in sorted(FORBIDDEN_IN_ALLOWLIST):
        response = client.request(method, _fill_path_params(path))
        if response.status_code not in (401, 403):
            broken.append(f"{method} {path} -> {response.status_code}")
    assert broken == []

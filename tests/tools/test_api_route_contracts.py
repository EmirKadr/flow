import re
from pathlib import Path

from app.backend.main import app


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_JS = ROOT / "app" / "frontend" / "js"

API_METHODS = {
    "get": "GET",
    "download": "GET",
    "post": "POST",
    "postForm": "POST",
    "postFile": "POST",
    "put": "PUT",
    "del": "DELETE",
}
DESKTOP_LOCAL_API_PREFIXES = ("/api/desktop/",)


def frontend_literal_api_calls() -> list[tuple[str, str, str]]:
    calls: list[tuple[str, str, str]] = []
    pattern = re.compile(
        r"\bapi\.(get|download|post|postForm|postFile|put|del)\(\s*([\"'])(/api/[^\"']+)\2"
    )
    for path in sorted(FRONTEND_JS.glob("*.js")):
        source = path.read_text(encoding="utf-8")
        for match in pattern.finditer(source):
            method = API_METHODS[match.group(1)]
            api_path = match.group(3).split("?", 1)[0]
            if api_path.startswith(DESKTOP_LOCAL_API_PREFIXES):
                continue
            calls.append((path.relative_to(ROOT).as_posix(), method, api_path))
    return calls


def _iter_flat_routes(routes, prefix: str = ""):
    """FastAPI >=0.139 lagger inkluderade routrar som _IncludedRouter-poster
    i stallet for att platta ut dem. Ga in i original_router rekursivt och
    ackumulera include-prefixet (nastlade include_router(prefix=...) bar
    prefixet i include_context, inte i ruttvagarna)."""
    for route in routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            context = getattr(route, "include_context", None)
            inner_prefix = prefix + (getattr(context, "prefix", "") or "")
            yield from _iter_flat_routes(original.routes, inner_prefix)
            continue
        yield prefix, route


def backend_route_methods() -> dict[str, set[str]]:
    routes: dict[str, set[str]] = {}
    for route_prefix, route in _iter_flat_routes(app.routes):
        path = route_prefix + getattr(route, "path", "")
        if not path.startswith("/api/"):
            continue
        methods = set(getattr(route, "methods", set()) or set())
        methods.discard("HEAD")
        methods.discard("OPTIONS")
        routes.setdefault(path, set()).update(methods)
    return routes


def test_frontend_literal_api_calls_exist_in_backend_with_matching_method():
    calls = frontend_literal_api_calls()
    routes = backend_route_methods()
    missing = []

    for source, method, api_path in calls:
        if method not in routes.get(api_path, set()):
            missing.append(f"{source}: {method} {api_path}")

    assert calls, "No literal frontend API calls found"
    assert missing == []


def test_backend_routes_do_not_expose_legacy_stallen_api():
    legacy_routes = [path for path in backend_route_methods() if "stallen" in path.lower()]

    assert legacy_routes == []

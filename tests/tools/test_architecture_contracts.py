"""Arkitektur-kontrakt: filstorlek, single-worker-antagandet och domängränser.

Tre invariants som skyddar mot smygande strukturförfall:

1. Filstorlek: ingen backendfil eller frontend-JS-fil får växa förbi taket.
   Befintliga för stora filer ligger i en undantagslista med sina nuvarande
   storlekar som tak - de får krympa men inte växa. När en fil splittas ska
   dess undantag tas bort.

2. Single-worker: bakgrundsjobben (app/backend/background.py och schedulers)
   antar exakt en uvicorn-worker. Fler workers => varje jobb körs en gång per
   worker. --workers får inte läggas till i render.yaml utan ledarlås.

3. Domängränser: servicemoduler får importera delad grund (config, models,
   settings_service m.fl.) och sin egen domän. Nya beroenden mellan domäner
   ska vara medvetna beslut - lägg till kanten i ALLOWED_DOMAIN_EDGES i samma
   PR och motivera i commit-meddelandet.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "app" / "backend"
FRONTEND_JS = ROOT / "app" / "frontend" / "js"
WAREHOUSE = ROOT / "warehouse_tools"

BACKEND_LINE_LIMIT = 1000
FRONTEND_LINE_LIMIT = 1000
WAREHOUSE_LINE_LIMIT = 1000

# Fil -> tak (nuvarande storlek vid införandet). Får krympa, aldrig växa.
BACKEND_LINE_EXCEPTIONS = {
    "schemas.py": 1013,
}
FRONTEND_LINE_EXCEPTIONS = {
    "allocation/results.js": 1810,
    "allocation/settings_view.js": 1760,
    "productivity_overview.js": 1780,
    "overview.js": 1780,
    "allocation/map_settings.js": 1440,
    "sankey_inbound.js": 1370,
    "allocation/state.js": 1250,
    "persons.js": 1100,
}
# Krympnings-ratchet for warehouse_tools: vendor-filen far bara minska tills
# den ar sanerad fran dod GUI-kod och till slut uppdelad. Ingen frizon.
WAREHOUSE_LINE_EXCEPTIONS = {
    "vendor/allokering12.1.py": 4250,
    "flows.py": 1410,
}


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8", errors="replace").splitlines())


def _rel(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def test_backend_files_stay_under_line_limit():
    violations = []
    for path in sorted(BACKEND.rglob("*.py")):
        rel = _rel(path, BACKEND)
        if rel.startswith("alembic/"):
            continue
        lines = _line_count(path)
        limit = BACKEND_LINE_EXCEPTIONS.get(rel, BACKEND_LINE_LIMIT)
        if lines > limit:
            violations.append(f"{rel}: {lines} rader (tak {limit})")
    assert not violations, (
        "Backendfiler över radtaket - splitta filen (se app/backend/data_fetch/, mcp/, "
        "sankey_inbound/ för mönstret) i stället för att höja taket:\n  "
        + "\n  ".join(violations)
    )


def test_frontend_js_files_stay_under_line_limit():
    violations = []
    for path in sorted(FRONTEND_JS.rglob("*.js")):
        rel = _rel(path, FRONTEND_JS)
        lines = _line_count(path)
        limit = FRONTEND_LINE_EXCEPTIONS.get(rel, FRONTEND_LINE_LIMIT)
        if lines > limit:
            violations.append(f"{rel}: {lines} rader (tak {limit})")
    assert not violations, (
        "Frontend-JS över radtaket - splitta i moduler (se js/allocation/ och js/schedule/ "
        "för mönstret) i stället för att höja taket:\n  " + "\n  ".join(violations)
    )


def test_warehouse_tools_files_stay_under_line_limit():
    violations = []
    for path in sorted(WAREHOUSE.rglob("*.py")):
        rel = _rel(path, WAREHOUSE)
        lines = _line_count(path)
        limit = WAREHOUSE_LINE_EXCEPTIONS.get(rel, WAREHOUSE_LINE_LIMIT)
        if lines > limit:
            violations.append(f"{rel}: {lines} rader (tak {limit})")
    assert not violations, (
        "warehouse_tools-filer över radtaket - vendor-filen ska bara krympa "
        "(sänk dess tak i WAREHOUSE_LINE_EXCEPTIONS i samma commit), övriga "
        "filer ska splittas i stället för att höja taket:\n  "
        + "\n  ".join(violations)
    )


def test_line_limit_exceptions_are_not_stale():
    """En undantagsrad för en fil som inte längre finns eller redan är under
    grundtaket ska tas bort, så listan inte blir en permanent frizon."""
    stale = []
    for rel, _limit in BACKEND_LINE_EXCEPTIONS.items():
        path = BACKEND / rel
        if not path.is_file() or _line_count(path) <= BACKEND_LINE_LIMIT:
            stale.append(f"app/backend/{rel}")
    for rel, _limit in FRONTEND_LINE_EXCEPTIONS.items():
        path = FRONTEND_JS / rel
        if not path.is_file() or _line_count(path) <= FRONTEND_LINE_LIMIT:
            stale.append(f"app/frontend/js/{rel}")
    for rel, _limit in WAREHOUSE_LINE_EXCEPTIONS.items():
        path = WAREHOUSE / rel
        if not path.is_file() or _line_count(path) <= WAREHOUSE_LINE_LIMIT:
            stale.append(f"warehouse_tools/{rel}")
    assert not stale, "Ta bort inaktuella undantag: " + ", ".join(stale)


def test_render_start_command_keeps_single_worker():
    text = (ROOT / "render.yaml").read_text(encoding="utf-8")
    start_lines = [line for line in text.splitlines() if "startCommand" in line]
    assert start_lines, "render.yaml saknar startCommand"
    for line in start_lines:
        assert "--workers" not in line and "gunicorn" not in line, (
            "startCommand får inte köra flera workers: bakgrundsjobben i "
            "app/backend/background.py och schedulerna i productivity_sync/"
            "archive_cache_sync antar exakt en process. Inför ledarlås "
            "(t.ex. Postgres advisory lock) innan --workers läggs till. Rad: " + line.strip()
        )


# --- Domängränser -----------------------------------------------------------

# Delad grund som alla domäner får importera.
SHARED_MODULES = {
    "audit", "background", "bootstrap_local", "business_scope", "code_utils",
    "compiled_data_paths", "config", "database", "demo_session", "deps",
    "external_data_client", "healthcheck_service", "home_activity", "main",
    "media_store", "migrate_pg_to_mssql", "models", "observability",
    "prepare_local_database", "prestart", "schedule_locks", "schemas",
    "security", "seed", "settings_service", "sync_live_to_local",
    "template_service", "user_access", "workflow_data",
}

# Modulprefix -> domän. Fasaderna räknas till samma domän som paketet.
DOMAIN_PREFIXES = {
    "data_fetch": "data_fetch",
    "data_fetch_service": "data_fetch",
    "sankey_inbound": "sankey",
    "sankey_inbound_service": "sankey",
    "mcp": "mcp",
    "mcp_service": "mcp",
    "productivity_service": "productivity",
    "productivity_sync": "productivity",
    "productivity_sync_paths": "productivity",
    "productivity_kpi_rules": "productivity",
    "productivity_finance_process_check": "productivity",
    "person_productivity_cache": "productivity",
    "meta_analysis_service": "meta",
    "staffing_calculator_service": "staffing",
    "local_archive_store": "archive",
    "archive_cache_sync": "archive",
    "archive_cache_cli": "archive",
    "coredata_service": "coredata",
    "allocation_bridge": "allocation",
}

# Medvetna, tillåtna beroenden mellan domäner (från -> till).
ALLOWED_DOMAIN_EDGES = {
    ("sankey", "data_fetch"),
    ("sankey", "productivity"),
    ("sankey", "archive"),
    ("archive", "data_fetch"),
    ("archive", "productivity"),
    ("productivity", "data_fetch"),
    ("productivity", "coredata"),
    ("staffing", "productivity"),
}


def _module_domain(module_name: str) -> str | None:
    head = module_name.split(".", 1)[0]
    return DOMAIN_PREFIXES.get(head)


def _backend_relative_import(node: ast.ImportFrom, current_pkg_depth: int) -> str | None:
    """Returnera backend-relativ modulväg för en relativ import, annars None."""
    if node.level == 0:
        return None
    # level 1 i en toppmodul eller level 2 i ett paket pekar på app.backend.
    if node.level - current_pkg_depth != 1:
        return None
    return node.module or ""


def test_service_modules_respect_domain_boundaries():
    violations = []
    for path in sorted(BACKEND.rglob("*.py")):
        rel = _rel(path, BACKEND)
        if rel.startswith(("alembic/", "routers/")):
            continue  # routrar och migrationer får korsa domäner
        head = rel.split("/", 1)[0].removesuffix(".py")
        source_domain = DOMAIN_PREFIXES.get(head)
        if source_domain is None:
            continue  # delade moduler kontrolleras inte som källa
        pkg_depth = rel.count("/")
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            target = _backend_relative_import(node, pkg_depth)
            if target is None:
                continue
            names = [target] if target else [alias.name for alias in node.names]
            for name in names:
                top = name.split(".", 1)[0]
                if not top or top in SHARED_MODULES:
                    continue
                target_domain = _module_domain(top)
                if target_domain is None or target_domain == source_domain:
                    continue
                if (source_domain, target_domain) not in ALLOWED_DOMAIN_EDGES:
                    violations.append(
                        f"{rel}: {source_domain} -> {target_domain} (import {name})"
                    )
    assert not violations, (
        "Ny domänkorsning i backend. Är beroendet medvetet? Lägg då till kanten i "
        "ALLOWED_DOMAIN_EDGES i samma ändring. Annars: gå via delad grund eller "
        "flytta logiken.\n  " + "\n  ".join(sorted(set(violations)))
    )

"""Arkitektur-kontrakt: filstorlek, single-worker-antagandet och domängränser.

Tre invariants som skyddar mot smygande strukturförfall:

1. Filstorlek: ingen backendfil eller frontend-JS-fil får växa förbi taket.
   Befintliga för stora filer ligger i en undantagslista med sina nuvarande
   storlekar som tak - de får krympa men inte växa. När en fil splittas ska
   dess undantag tas bort.

2. Single-worker: bakgrundsjobben (app/backend/background.py och schedulers)
   antar exakt en uvicorn-worker. Fler workers => varje jobb körs en gång per
   worker. --workers får inte läggas till i Dockerfile-CMD utan ledarlås.

3. Domängränser: servicemoduler får importera delad grund (config, models,
   settings_service m.fl.) och sin egen domän. Nya beroenden mellan domäner
   ska vara medvetna beslut - lägg till kanten i ALLOWED_DOMAIN_EDGES i samma
   PR och motivera i commit-meddelandet.
"""
from __future__ import annotations

import ast
import re
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
    "allocation/map_settings.js": 1060,
}
# Vendor-monoliten (allokering12.1.py) ar uppdelad i engine_core/ (2026-07)
# och krympnings-ratcheten ar avslutad. Kvarvarande undantag ska bara minska.
WAREHOUSE_LINE_EXCEPTIONS: dict[str, int] = {}


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


def test_container_start_command_keeps_single_worker():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    start_lines = [line for line in text.splitlines() if "uvicorn" in line]
    assert start_lines, "Dockerfile saknar uvicorn-startkommando"
    for line in start_lines:
        assert "--workers" not in line and "gunicorn" not in line, (
            "Startkommandot får inte köra flera workers: bakgrundsjobben i "
            "app/backend/background.py och schedulerna startas via ledarlåset i "
            "app/backend/leader_lock.py. --workers är ändå ett medvetet beslut: "
            "verifiera ledarlåset i drift och uppdatera detta kontrakt i samma "
            "ändring. Rad: " + line.strip()
        )


# --- DEPLOY.md: runbooken man läser precis innan man rör --workers -----------
#
# Den gamla varianten av det här kontraktet var guardrail-teater: den klippte
# sektionen med split("## Leveransoptimering")[1] (= allt till filslutet, inte
# bara worker-avsnittet) och asserterade bara på TOKENNÄRVARO. Ett DEPLOY.md som
# påstod raka motsatsen passerade, så länge orden fanns någonstans. Testerna
# nedan binder i stället dokumentets PÅSTÅENDEN mot koden de beskriver.


def _deploy_text() -> str:
    return (ROOT / "DEPLOY.md").read_text(encoding="utf-8")


def _deploy_section(heading: str) -> str:
    """Sektionen från `heading` fram till NÄSTA '## '-rubrik (inte filslutet)."""
    deploy = _deploy_text()
    assert heading in deploy, f"DEPLOY.md saknar rubriken {heading!r}"
    after = deploy.split(heading, 1)[1]
    end = after.find("\n## ")
    return after if end == -1 else after[:end]


def _worker_section() -> str:
    return _deploy_section("## Leveransoptimering")


def _call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def _covered_range_calls_are_all_guarded() -> bool:
    """Ligger VARJE covered_range()-anrop i sankey_inbound/fetch.py inuti ett
    try-block? Med >1 worker kastar anropet duckdb.IOException medan ledaren
    skriver; ett oskyddat anrop = hård 500 på hela Sankey-rapporten."""
    tree = ast.parse(
        (BACKEND / "sankey_inbound" / "fetch.py").read_text(encoding="utf-8"),
        filename="fetch.py",
    )
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for stmt in node.body:
            for inner in ast.walk(stmt):
                if isinstance(inner, ast.Call) and _call_name(inner) == "covered_range":
                    guarded.add(id(inner))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _call_name(node) == "covered_range"
    ]
    assert calls, (
        "covered_range() anropas inte längre i sankey_inbound/fetch.py. Koden har "
        "ändrats - uppdatera det här kontraktet OCH worker-avsnittet i DEPLOY.md."
    )
    return all(id(call) in guarded for call in calls)


# Processlokalt tillstånd som var för sig blockerar `uvicorn --workers > 1`.
# (doc-token som måste stå i DEPLOY.md, källfil, symbol som bevisar att den lever)
WORKER_BLOCKERS = (
    ("local_archive_store", BACKEND / "local_archive_store.py", "_LOCKS"),
    ("_RATE_HITS", BACKEND / "routers" / "meta_uploads_helpers.py", "_RATE_HITS"),
    ("_STATUS", BACKEND / "background.py", "_STATUS"),
)


def test_deploy_worker_section_lists_every_process_local_blocker():
    """Varje processlokalt tillstånd som hindrar --workers ska stå i runbooken.
    Symbolkollen mot koden gör listan självstädande: försvinner blockeraren ur
    koden failar testet och tvingar fram en uppdatering av BÅDE listan och
    DEPLOY.md - i stället för att tyst skydda ett inaktuellt påstående."""
    section = _worker_section()
    for token, source, symbol in WORKER_BLOCKERS:
        assert symbol in source.read_text(encoding="utf-8"), (
            f"{source.name}: symbolen {symbol} finns inte längre. Är blockeraren "
            "åtgärdad? Ta då bort den ur WORKER_BLOCKERS och ur DEPLOY.md:s "
            "worker-avsnitt i samma ändring."
        )
        assert token in section, (
            "DEPLOY.md:s worker-avsnitt måste namnge ALLA processlokala blockerare "
            f"innan någon höjer --workers. Saknar: {token} (från {source.name})."
        )
    for token in ("ARCHIVE_CACHE_ENABLED", "test_container_start_command_keeps_single_worker"):
        assert token in section, f"Worker-avsnittet saknar {token}."


def test_deploy_worker_section_does_not_claim_a_single_blocker():
    """Exklusivitetspåståenden ("den kvarvarande blockeraren") är precis felet:
    de får läsaren att tro att en fix räcker. Det finns minst tre."""
    section = _worker_section()
    for phrase in (
        "enda blockeraren",
        "den enda blockeraren",
        "kvarvarande blockeraren",
        "enda kvarvarande",
    ):
        assert phrase not in section, (
            f"DEPLOY.md utnämner igen EN blockerare för --workers ({phrase!r}). "
            "Minst tre processlokala tillstånd blockerar: "
            + ", ".join(token for token, _s, _y in WORKER_BLOCKERS)
        )


def test_deploy_worker_section_matches_the_guarding_of_covered_range():
    """Tvåvägsbind mot koden. Så länge fetch.py anropar covered_range() UTAN
    try/except måste runbooken säga att en icke-ledar-worker får en hård 500 på
    Sankey - inte att felet sväljs och faller tillbaka. Skyddas anropet någon
    gång ska dokumentet uppdateras i samma ändring; då failar testet åt andra
    hållet i stället."""
    section = _worker_section()
    if _covered_range_calls_are_all_guarded():
        assert "utan `try/except`" not in section, (
            "covered_range() är numera skyddat i fetch.py, men DEPLOY.md påstår "
            "fortfarande att det är oskyddat. Uppdatera worker-avsnittet."
        )
        return
    assert "covered_range" in section, (
        "fetch.py anropar covered_range() utan try/except - det ger en hård 500 på "
        "Sankey-rapporten med >1 worker. Runbooken MÅSTE namnge anropet."
    )
    assert "utan `try/except`" in section, (
        "Worker-avsnittet måste säga att covered_range() anropas UTAN try/except."
    )
    assert "500" in section, (
        "Worker-avsnittet måste säga att följden är en hård 500, inte en fallback."
    )
    for lie in ("sväljer felet", "svaljer felet"):
        assert lie not in section, (
            f"DEPLOY.md påstår igen att läsvägarna {lie!r} och faller tillbaka. "
            "Det oskyddade covered_range()-anropet i sankey_inbound/fetch.py gör att "
            "Sankey-rapporten svarar 500 - det är en högljudd failning på huvudvägen."
        )


def test_deploy_worker_section_does_not_prescribe_the_disproven_read_only_fix():
    """"En skrivare - ledaren - och read_only för alla andra" är motbevisat av
    tests/services/test_local_archive_store.py::test_duckdb_file_lock_blocks_a_second_process:
    medan ledaren skriver kan en annan process inte ens ÖPPNA filen read_only.
    Dessutom öppnar alla läsvägar i local_archive_store redan read_only=True, så
    "fixen" är redan gjord. Nämner runbooken read_only måste den säga att det
    inte räcker, och peka ut den åtgärd som faktiskt håller."""
    section = _worker_section()
    if "read_only" in section:
        assert "INTE fixen" in section, (
            "DEPLOY.md föreskriver read_only som åtgärd för DuckDB-blockeraren. "
            "Läsvägarna är redan read_only=True, och "
            "test_duckdb_file_lock_blocks_a_second_process visar att en read_only-"
            "öppning ändå kastar IOException medan ledaren skriver."
        )
        assert "test_duckdb_file_lock_blocks_a_second_process" in section, (
            "Nämner runbooken read_only ska den citera testet som motbevisar det."
        )
    assert "os.replace" in section, (
        "Worker-avsnittet måste namnge den åtgärd som faktiskt håller (atomisk "
        "os.replace()-snapshot eller processöverskridande lagring)."
    )


def _deploy_probe_config() -> dict:
    """Probe-blocket som DEPLOY.md ber läsaren kopiera."""
    import yaml

    section = _deploy_section("## 7. Healthcheck och probes")
    blocks = re.findall(r"```yaml\n(.*?)```", section, re.DOTALL)
    assert blocks, "Avsnitt 7 i DEPLOY.md saknar ett yaml-block med probes."
    return yaml.safe_load(blocks[0])


def test_deploy_doc_prescribes_the_probe_config_that_prepush_accepts():
    """DEPLOY.md är filen man kopierar probe-konfigen ur. Föreskriver den ett
    initialDelaySeconds-golv på readiness ber runbooken läsaren göra exakt det
    som tests/tools/test_gap_k8s_contracts.py::test_readiness_has_no_initial_delay_floor
    underkänner i pre-push."""
    probes = _deploy_probe_config()
    assert "startupProbe" in probes, (
        "DEPLOY.md måste föreskriva en startupProbe - utan den är readinessProbens "
        "initialDelaySeconds enda startgrinden (test_startup_probe_exists_and_is_patient)."
    )
    readiness = probes.get("readinessProbe") or {}
    assert "initialDelaySeconds" not in readiness, (
        "DEPLOY.md föreskriver readinessProbe.initialDelaySeconds="
        f"{readiness.get('initialDelaySeconds')!r}. startupProbe är startgrinden; "
        "ett golv här är ren nedtid vid varje deploy och underkänns av "
        "test_readiness_has_no_initial_delay_floor."
    )
    startup = probes["startupProbe"]
    budget = startup.get("periodSeconds", 10) * startup.get("failureThreshold", 3)
    assert budget >= 180, (
        f"DEPLOY.md:s startupProbe-budget är {budget}s < 180s - snålare än "
        "manifesten och test_startup_probe_exists_and_is_patient."
    )
    for name in ("startupProbe", "livenessProbe", "readinessProbe"):
        assert (probes.get(name) or {}).get("timeoutSeconds") == 5, (
            f"DEPLOY.md:s {name} saknar timeoutSeconds: 5. Default 1s räcker inte "
            "vid CFS-strypning (test_all_probes_keep_generous_timeout)."
        )
    assert "initialDelaySeconds: 15" not in _deploy_text(), (
        "DEPLOY.md föreskriver fortfarande det gamla readiness-golvet på 15s."
    )


# --- Domängränser -----------------------------------------------------------

# Delad grund som alla domäner får importera.
SHARED_MODULES = {
    "audit", "background", "bootstrap_local", "business_scope", "code_utils",
    "compiled_data_paths", "config", "database", "demo_session", "deps",
    "external_data_client", "healthcheck_service", "home_activity", "leader_lock", "main",
    "media_store", "models", "observability",
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


# --- Frontend-domangranser ---------------------------------------------------

FRONTEND_DIR = ROOT / "app" / "frontend"

# Sida -> domankatalog under js/ (utover common/ som alla sidor far ladda).
# Kontrakt: en sida laddar script fran js/common/ plus hogst EN domankatalog.
# Ett nytt korsberoende ar ett medvetet beslut - uppdatera mappningen i samma
# andring och motivera i commit-meddelandet, precis som ALLOWED_DOMAIN_EDGES.
ALLOWED_PAGE_DOMAINS = {
    "bearbeta.html": {"allocation"},
    # Vendrad rrweb-bundle för uppspelning — inte en appdomän, medvetet undantag.
    "bug-rapporter.html": {"vendor"},
    "dela.html": {"allocation"},
    "installningar.html": {"allocation"},
    "uppladdningar.html": {"allocation"},
    "index.html": {"schedule"},
    "label-editor.html": {"label_editor"},
}


def test_frontend_pages_only_load_their_own_domain_scripts():
    violations = []
    for html in sorted(FRONTEND_DIR.glob("*.html")):
        text = html.read_text(encoding="utf-8")
        srcs = re.findall(r'<script[^>]+src="([^"]+)"', text)
        domains = set()
        for src in srcs:
            match = re.match(r"/?js/([^/]+)/", src)
            if match and match.group(1) != "common":
                domains.add(match.group(1))
        allowed = ALLOWED_PAGE_DOMAINS.get(html.name, set())
        extra = domains - allowed
        if extra:
            allowed_label = ", ".join(sorted(allowed)) if allowed else "bara common/"
            violations.append(f"{html.name}: laddar {sorted(extra)} (tillatet: {allowed_label})")
    assert not violations, (
        "Ny domankorsning i frontend. Ar beroendet medvetet? Lagg da till "
        "domanen i ALLOWED_PAGE_DOMAINS i samma andring. Annars: flytta delad "
        "logik till js/common/ i stallet for att ladda en annan domans script:\n  "
        + "\n  ".join(violations)
    )


def test_frontend_page_domain_allowlist_is_not_stale():
    stale = []
    for name, domains in ALLOWED_PAGE_DOMAINS.items():
        page = FRONTEND_DIR / name
        if not page.is_file():
            stale.append(f"{name} (sidan finns inte)")
            continue
        text = page.read_text(encoding="utf-8")
        srcs = re.findall(r'<script[^>]+src="([^"]+)"', text)
        loaded = set()
        for src in srcs:
            match = re.match(r"/?js/([^/]+)/", src)
            if match and match.group(1) != "common":
                loaded.add(match.group(1))
        unused = domains - loaded
        if unused:
            stale.append(f"{name}: {sorted(unused)} laddas inte langre")
    assert not stale, "Ta bort inaktuella poster ur ALLOWED_PAGE_DOMAINS: " + ", ".join(stale)


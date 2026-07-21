"""Statiska kontrakt for verktyget Dubbletter (Ta bort dubbletter).

Verktyget ar helt klientsidigt: text in, unika rader ut. Testerna nedan
skyddar tre saker som ar latta att missa nar en ny vy laggs till:

1. Vy-id:t ar registrerat pa alla stallen som behorighetsmatrisen laser
   (frontendens ROLE_VIEW_IDS/VIEW_ACCESS_OPTIONS + backendens
   ROLE_VIEW_ORDER/ROLE_VIEW_LABELS). Den inbordes ordningen halls redan av
   test_access_contracts.py - har sakras narvaro och etikett.
2. Verktygsfliken finns pa *alla* sidor som renderar tools-tabs, inte bara
   pa den nya sidan.
3. Det avsiktliga audit-undantaget: sidan gor inga API-anrop och skapar
   darfor ingen auditrad. Bryts det ska testet falla sa att
   Historik/Analys-planen tas fram i samma andring (AGENTS.md, Loggregel).
"""
from __future__ import annotations

import re
from pathlib import Path

from app.backend import user_access

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "app" / "frontend"
DEDUPE_HTML = FRONTEND / "dubbletter.html"
DEDUPE_JS = FRONTEND / "js" / "dubbletter.js"
FOUNDATION_JS = FRONTEND / "js" / "common" / "foundation.js"
ROLE_ACCESS_JS = FRONTEND / "js" / "common" / "role_access.js"
ACCESS_JS = FRONTEND / "js" / "common" / "access.js"

VIEW_ID = "removeDuplicates"
VIEW_LABEL = "Dubbletter"
TAB_MARKUP = '<a class="tools-tab" href="/dubbletter.html" data-tools-tab-view="removeDuplicates">Dubbletter</a>'


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_page_and_script_exist():
    assert DEDUPE_HTML.is_file(), "dubbletter.html saknas"
    assert DEDUPE_JS.is_file(), "js/dubbletter.js saknas"
    assert _read(DEDUPE_JS).startswith("// @ts-check"), "ny JS-fil ska vara typkontrollerad"


def test_view_id_is_registered_in_backend_and_frontend():
    assert VIEW_ID in user_access.ROLE_VIEW_ORDER
    assert user_access.ROLE_VIEW_LABELS[VIEW_ID] == VIEW_LABEL

    foundation = _read(FOUNDATION_JS)
    assert f'"{VIEW_ID}"' in foundation, "vy-id saknas i ROLE_VIEW_IDS"

    role_access = _read(ROLE_ACCESS_JS)
    assert f'{{ id: "{VIEW_ID}", label: "{VIEW_LABEL}" }}' in role_access

    access = _read(ACCESS_JS)
    assert f'{VIEW_ID}: "/dubbletter.html"' in access, "href saknas i SIDEBAR_VIEW_HREFS"
    assert f'"{VIEW_ID}"' in access, "vy-id saknas i SIDEBAR_TOOLS_TAB_VIEW_IDS"


def test_default_access_matches_between_clients():
    """Backend och frontend ska ge samma roller tillgang till verktyget."""
    backend_roles = {
        role for role, views in user_access.ROLE_VIEW_DEFAULT_ACCESS.items() if VIEW_ID in views
    }
    foundation = _read(FOUNDATION_JS)
    frontend_blocks = re.findall(r"^  (\w+): \{(.*?)^  \},", foundation, re.M | re.S)
    frontend_roles = {role for role, body in frontend_blocks if f"{VIEW_ID}:" in body}
    assert backend_roles, "ingen roll har default-tillgang till verktyget"
    assert backend_roles == frontend_roles, (
        "default-access ur synk mellan user_access.py och foundation.js: "
        f"backend={sorted(backend_roles)} frontend={sorted(frontend_roles)}"
    )


def test_tools_tab_is_present_on_every_tools_page():
    pages = sorted(path for path in FRONTEND.glob("*.html") if "data-tools-tab-view" in _read(path))
    assert len(pages) >= 7, "farre verktygssidor an vantat - har navet flyttats?"
    missing = [path.name for path in pages if 'data-tools-tab-view="removeDuplicates"' not in _read(path)]
    assert missing == [], f"Dubbletter-fliken saknas pa: {missing}"

    others = [path for path in pages if path.name != "dubbletter.html"]
    not_linked = [path.name for path in others if TAB_MARKUP not in _read(path)]
    assert not_linked == [], f"fliken ar inte en vanlig lank pa: {not_linked}"


def test_active_tab_on_own_page():
    html = _read(DEDUPE_HTML)
    assert (
        '<a class="tools-tab active" href="/dubbletter.html" aria-current="page" '
        'data-tools-tab-view="removeDuplicates">Dubbletter</a>' in html
    )
    assert html.count('class="tools-tab active"') == 1


def test_page_gates_on_the_view_id():
    assert f'initPage("{VIEW_ID}")' in _read(DEDUPE_JS)


def test_tool_is_client_only_and_has_no_audit_trail():
    """Avsiktligt read-only-undantag: verktyget ror aldrig backend.

    Ingen data lamnar webblasaren, alltsa finns ingen auditrad och ingen
    Historik-label att halla begriplig. Laggs ett API-anrop till har ska
    audit + Historik/Analys planeras i samma andring.
    """
    source = _read(DEDUPE_JS)
    for forbidden in ("fetch(", "api.get", "api.post", "api.put", "api.del", "XMLHttpRequest"):
        assert forbidden not in source, (
            f"{forbidden} i dubbletter.js - verktyget ar dokumenterat klientsidigt. "
            "Lagg audit och Historik/Analys-label i samma andring om det ska andras."
        )


def test_copy_has_a_desktop_safe_fallback():
    """QtWebEngine (Windows-appen) kan sakna navigator.clipboard."""
    source = _read(DEDUPE_JS)
    assert "navigator.clipboard" in source
    assert 'document.execCommand("copy")' in source

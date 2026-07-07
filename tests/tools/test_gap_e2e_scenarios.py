"""Non-browser-kontrakt för de NYA e2e-scenarierna (W25).

Startar ingen webbläsare. Verifierar bara att de tre nya scenarierna
(`sweep-all`, `history-health`, `theme-mobile`) är korrekt registrerade i
SCENARIOS och att sidlistorna (ALL_PAGES / DEFAULT_PAGES) är välformade:
alla paths absoluta (börjar med "/"), unika, och att ALL_PAGES verkligen
utökar DEFAULT_PAGES med de riktiga sidorna som specen kräver.

Rör inga befintliga testfiler. Läser bara `tools.e2e.scenarios`.
"""
from __future__ import annotations

import inspect

import pytest

from tools.e2e import scenarios as scen_mod
from tools.e2e.scenarios import ALL_PAGES, DEFAULT_PAGES, SCENARIOS, Scenario, _slug

NEW_SCENARIOS = ("sweep-all", "history-health", "theme-mobile")


def test_new_scenarios_are_registered():
    for name in NEW_SCENARIOS:
        assert name in SCENARIOS, f"scenario {name!r} saknas i SCENARIOS"


def test_existing_scenarios_still_present():
    # De nya får inte råka skugga/ta bort de gamla.
    expected = {"smoke", "inspect", "sweep", "bug-reports", "role-access", "business-filter"}
    assert expected <= set(SCENARIOS)


@pytest.mark.parametrize("name", NEW_SCENARIOS)
def test_new_scenario_shape(name):
    scenario = SCENARIOS[name]
    assert isinstance(scenario, Scenario)
    assert callable(scenario.func)
    assert isinstance(scenario.description, str) and scenario.description.strip()
    # Signaturen måste vara (session, report, args) precis som övriga scenarier.
    params = list(inspect.signature(scenario.func).parameters)
    assert params == ["session", "report", "args"], f"{name} har fel signatur: {params}"


def test_scenario_names_unique():
    # dict-nycklar är per definition unika; men beskrivningarna ska inte vara tomma.
    assert len(SCENARIOS) == len(set(SCENARIOS))
    for name, scenario in SCENARIOS.items():
        assert scenario.description.strip(), f"{name} saknar beskrivning"


# --- sidlistor välformade ---
def test_all_pages_paths_are_absolute():
    assert ALL_PAGES, "ALL_PAGES får inte vara tom"
    for path in ALL_PAGES:
        assert path.startswith("/"), f"path {path!r} börjar inte med /"


def test_all_pages_names_nonempty_and_slugsafe():
    for path, name in ALL_PAGES.items():
        assert name and name.strip(), f"{path} har tomt namn"
        # Namnet ska vara filsystemssäkert (används som skärmbildsfilnamn via _slug).
        assert _slug(name) == name, f"namnet {name!r} är inte redan slug-säkert"


def test_all_pages_paths_unique():
    assert len(ALL_PAGES) == len(set(ALL_PAGES))
    # Även de läsbara namnen ska vara unika så skärmbilder inte skriver över varandra.
    names = list(ALL_PAGES.values())
    assert len(names) == len(set(names)), "dubbla sidnamn i ALL_PAGES"


def test_all_pages_extends_default_pages():
    # Specen: sweep-all ska täcka standarduppsättningen PLUS de nya sidorna.
    for path, name in DEFAULT_PAGES.items():
        assert ALL_PAGES.get(path) == name, f"DEFAULT_PAGES-post {path} saknas/ändrad i ALL_PAGES"
    assert len(ALL_PAGES) > len(DEFAULT_PAGES)


def test_all_pages_covers_required_real_pages():
    # De sidor specen uttryckligen nämner utöver standarduppsättningen.
    required = {
        "/historik.html",
        "/arkiv-status.html",
        "/meta.html",
        "/mcp.html",
        "/dela.html",
        "/hamta-data.html",
        "/mitt-schema.html",
        "/min-produktivitet.html",
        "/sankey-inbound.html",
        "/uppladdningar.html",
        "/bearbeta.html",
    }
    missing = required - set(ALL_PAGES)
    assert not missing, f"sweep-all saknar riktiga sidor: {sorted(missing)}"


def test_sweep_all_is_broad():
    # "~25 riktiga sidor" — kräv en rejält bred täckning.
    assert len(ALL_PAGES) >= 20, f"ALL_PAGES täcker bara {len(ALL_PAGES)} sidor"


def test_all_pages_html_extension():
    # Alla riktiga vyer är statiska .html-sidor (ev. med ?query).
    for path in ALL_PAGES:
        assert ".html" in path, f"{path} ser inte ut som en sid-path"


def test_all_pages_excludes_auth_flows():
    # Login/set-password är autentiseringsflöden, inte appvyer, och ska inte svepas.
    for path in ALL_PAGES:
        low = path.lower()
        assert "login" not in low, f"{path}: login ska inte ingå i svepet"
        assert "set-password" not in low, f"{path}: set-password ska inte ingå i svepet"

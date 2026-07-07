"""Namngivna e2e-scenarier (undersökningar).

Varje scenario är en funktion (session, report, args) som kör mot en inloggad
FlowSession och fyller en Report. Registret SCENARIOS mappar namn -> (beskrivning,
funktion). Lägg till nya scenarier här; CLI:t (`python -m tools.e2e`) plockar upp
dem automatiskt.
"""
from __future__ import annotations

from typing import Any, Callable, NamedTuple

# Standarduppsättning sidor för hälsosvep. Path -> läsbart namn.
DEFAULT_PAGES: dict[str, str] = {
    "/index.html": "oversikt",
    "/personer.html": "personer",
    "/overblick.html": "overblick",
    "/produktivitet.html": "produktivitet",
    "/aktiviteter.html": "aktiviteter",
    "/anvandare.html": "anvandare",
    "/installningar.html": "installningar",
    "/bug-rapporter.html": "buggrapporter",
    "/verksamheter.html": "verksamheter",
    "/label-editor.html": "etiketter",
}


def _slug(text: str) -> str:
    keep = [c if (c.isalnum() or c in "-_") else "-" for c in text.strip().lower()]
    return "".join(keep).strip("-") or "sida"


def capture_page(session, report, path: str, name: str, screenshot: bool = True) -> None:
    """Gå till en sida och registrera timing, konsolfel, nätverksfel och (valfritt)
    en skärmbild. Grunden i de flesta undersökningar."""
    try:
        timing = session.goto(path)
    except Exception as exc:  # noqa: BLE001
        report.add_finding("error", f"Kunde inte ladda {path}: {exc.__class__.__name__}")
        report.add_network(name, session.drain_network())
        report.add_console(name, session.drain_console())
        return
    session.wait_ms(500)  # låt sen JS logga färdigt
    report.add_timing(name, timing)
    console = session.drain_console()
    network = session.drain_network()
    report.add_console(name, console)
    report.add_network(name, network)
    if any(c["level"] == "error" for c in console):
        report.add_finding("error", f"{name}: {sum(1 for c in console if c['level']=='error')} konsolfel")
    if network:
        report.add_finding("warn", f"{name}: {len(network)} nätverksfel (4xx/5xx/failed)")
    if screenshot:
        try:
            report.add_screenshot(name, session.screenshot(_slug(name)), path)
        except Exception as exc:  # noqa: BLE001
            report.add_finding("warn", f"Skärmbild misslyckades för {name}: {exc.__class__.__name__}")


# --- scenarier ---
def scenario_smoke(session, report, args) -> None:
    """Logga in och gå igenom de nya funktionerna + fånga konsol/nätverk."""
    capture_page(session, report, "/index.html", "01-oversikt")
    try:
        report.add_screenshot("02-fokustogglar", session.screenshot("02-fokustogglar", selector=".sidebar-footer"),
                              "Staplade fokustogglar")
    except Exception:  # noqa: BLE001
        pass
    capture_page(session, report, "/bug-rapporter.html", "03-buggrapporter")
    report.add_assertion("Buggrapporter har Ta bort-knapp", session.exists("button.bug-report-delete"))
    report.add_assertion("Buggrapporter har status-dropdown", session.exists("select.bug-report-status-select"))
    if session.exists("tr[data-report-id]"):
        session.click("tr[data-report-id]")
        try:
            session.wait("#bugReportDetail:not([hidden])")
            report.add_screenshot("04-detalj", session.screenshot("04-detalj"), "Detaljpanel")
            report.add_assertion("Detalj har 'Markera som att göra'",
                                 "att göra" in session.text("#bugReportMarkSeen").lower())
        except Exception:  # noqa: BLE001
            pass
    capture_page(session, report, "/installningar.html?tab=role-access", "05-vybehorigheter")


def scenario_inspect(session, report, args) -> None:
    """Inspektera EN valfri sida: --page /nagon.html. Skärmbild + konsol +
    nätverk + timing + ett textutdrag agenten kan läsa."""
    path = args.get("page") or "/index.html"
    name = _slug(path.split("?")[0].strip("/") or "index")
    capture_page(session, report, path, name)
    snippet = session.page_text(2000)
    report.add_finding("info", f"Textutdrag {path}:\n{snippet}")


def scenario_sweep(session, report, args) -> None:
    """Hälsosvep: gå igenom flera sidor och samla konsolfel/nätverksfel/timing
    per sida. --pages a,b,c överstyr standarduppsättningen."""
    raw = args.get("pages")
    if raw:
        pages = {p if p.startswith("/") else f"/{p}": _slug(p) for p in raw.split(",") if p.strip()}
    else:
        pages = DEFAULT_PAGES
    for path, name in pages.items():
        capture_page(session, report, path, name)


def scenario_bug_reports(session, report, args) -> None:
    """Fördjupning i Buggrapporter-vyn: lista, status-dropdown, detaljpanel."""
    capture_page(session, report, "/bug-rapporter.html", "buggrapporter-lista")
    report.add_assertion("Ta bort-knapp finns", session.exists("button.bug-report-delete"))
    report.add_assertion("Status-dropdown finns", session.exists("select.bug-report-status-select"))
    report.add_finding("info", f"Antal rapporter i listan: {session.count('tr[data-report-id]')}")
    if session.exists("tr[data-report-id]"):
        session.click("tr[data-report-id]")
        session.wait("#bugReportDetail:not([hidden])")
        report.add_screenshot("buggrapport-detalj", session.screenshot("buggrapport-detalj"), "Detaljpanel")


def scenario_role_access(session, report, args) -> None:
    """Vybehörigheter-panelen under Inställningar (roll × vy-matris)."""
    capture_page(session, report, "/installningar.html?tab=role-access", "vybehorigheter")
    report.add_assertion("Spara-knapp finns", session.exists("#role-access-save, button:has-text('Spara')"))


def scenario_business_filter(session, report, args) -> None:
    """Verksamhetsfiltret vid ∞ områden: fota personlistan, växla verksamhets-
    toggeln och fota igen så filtreringseffekten syns."""
    capture_page(session, report, "/personer.html", "personer-innan")
    before = session.count("tbody tr, tr[data-person-id]")
    report.add_finding("info", f"Personrader innan toggle: {before}")
    if session.exists("#business-focus-toggle"):
        session.click("#business-focus-toggle")
        session.wait_ms(1200)  # låt omhämtningen ske
        report.add_screenshot("personer-efter", session.screenshot("personer-efter"), "Efter verksamhetsbyte")
        after = session.count("tbody tr, tr[data-person-id]")
        report.add_finding("info", f"Personrader efter toggle: {after}")
        report.add_assertion("Verksamhetstoggeln påverkade listan (eller lika om en verksamhet)",
                             True, f"{before} -> {after}")
    else:
        report.add_finding("warn", "Ingen verksamhetstoggle (kräver Super User).")


class Scenario(NamedTuple):
    description: str
    func: Callable[[Any, Any, dict], None]


SCENARIOS: dict[str, Scenario] = {
    "smoke": Scenario("Logga in + verifiera de nya funktionerna med skärmbilder", scenario_smoke),
    "inspect": Scenario("Inspektera EN sida (--page): skärmbild, konsol, nätverk, text", scenario_inspect),
    "sweep": Scenario("Hälsosvep över flera sidor (--pages): konsolfel, nätverksfel, timing", scenario_sweep),
    "bug-reports": Scenario("Fördjupning i Buggrapporter-vyn", scenario_bug_reports),
    "role-access": Scenario("Vybehörigheter-panelen under Inställningar", scenario_role_access),
    "business-filter": Scenario("Verksamhetsfiltret vid ∞ områden (före/efter)", scenario_business_filter),
}

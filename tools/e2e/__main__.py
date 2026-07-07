"""CLI för e2e-undersökningsverktyget.

Loggar in mot en körande Flow-miljö (FLOW_E2E_* i app/.env) och kör ett
namngivet scenario, sparar skärmbilder + en agent-läsbar rapport under
artifacts/e2e/<scenario>/ (gitignorerad).

Exempel:
  python -m tools.e2e --list
  python -m tools.e2e smoke
  python -m tools.e2e inspect --page /overblick.html
  python -m tools.e2e sweep --pages index.html,personer.html,overblick.html
  python -m tools.e2e business-filter --headed
  python -m tools.e2e sweep --base-url https://flow.nowastelogistics.com

All konsolutskrift är ren ASCII (Windows-konsol). Lösenordet loggas aldrig.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools.e2e.env import MISSING_CREDENTIALS_HELP, ROOT, resolve_credentials
from tools.e2e.report import Report
from tools.e2e.scenarios import SCENARIOS
from tools.e2e.session import FlowSession

OUTPUT_ROOT = ROOT / "artifacts" / "e2e"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.e2e", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenario", nargs="?", default="smoke", help="Scenario att köra (default: smoke).")
    parser.add_argument("--list", action="store_true", help="Lista tillgängliga scenarier och avsluta.")
    parser.add_argument("--base-url", default=None, help="Miljö (default: FLOW_E2E_BASE_URL eller development).")
    parser.add_argument("--page", default=None, help="Sida för 'inspect' (t.ex. /overblick.html).")
    parser.add_argument("--pages", default=None, help="Kommaseparerade sidor för 'sweep'.")
    parser.add_argument("--headed", action="store_true", help="Visa webbläsaren (default headless).")
    parser.add_argument("--out", default=None, help="Utmapp (default: artifacts/e2e/<scenario>).")
    return parser


def print_scenarios() -> None:
    print("Tillgangliga scenarier:")
    for name, scenario in SCENARIOS.items():
        print(f"  {name:16} {scenario.description}")


def _force_utf8_stdout() -> None:
    """Windows-konsolen är cp1252 och kraschar på åäö/∞. Sätt strömmarna till
    UTF-8 (errors=replace) så utskrift aldrig fäller verktyget."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - äldre Python/omdirigerad ström
            pass


def main(argv=None) -> int:
    _force_utf8_stdout()
    args = build_parser().parse_args(argv)

    if args.list:
        print_scenarios()
        return 0

    if args.scenario not in SCENARIOS:
        print(f"Okant scenario: {args.scenario}. Kor --list for tillgangliga.")
        return 2

    creds = resolve_credentials(args.base_url)
    if creds is None:
        print(MISSING_CREDENTIALS_HELP)
        return 2

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright saknas. Kor: pip install -r requirements-dev.txt && playwright install chromium")
        return 3

    out_dir = Path(args.out) if args.out else OUTPUT_ROOT / args.scenario
    report = Report(out_dir=out_dir, title=f"E2E: {args.scenario}", base_url=creds.base_url)
    scenario = SCENARIOS[args.scenario]
    scenario_args = {"page": args.page, "pages": args.pages}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        context = browser.new_context(locale="sv-SE", viewport={"width": 1440, "height": 900})
        page = context.new_page()
        session = FlowSession(page, out_dir)
        try:
            session.login(creds.base_url, creds.username, creds.password)
            print(f"Inloggad: {creds.redacted()}")
        except Exception as exc:  # noqa: BLE001 - rapportera tydligt, lack aldrig losenord
            print(f"Inloggning misslyckades: {exc.__class__.__name__}. Kontrollera FLOW_E2E_* i app/.env.")
            context.close()
            browser.close()
            return 1
        try:
            scenario.func(session, report, scenario_args)
        except Exception as exc:  # noqa: BLE001
            report.add_finding("error", f"Scenariot avbrots: {exc.__class__.__name__}: {exc}")
        context.close()
        browser.close()

    md_path, json_path = report.write()
    counts = report.counts()
    print(f"Scenario '{args.scenario}' klart mot {creds.base_url}")
    print(f"  skarmbilder: {counts['screenshots']}  konsolfel: {counts['console_errors']}  "
          f"natverksfel: {counts['network_failures']}  "
          f"assertions: {counts['assertions_total']-counts['assertions_failed']}/{counts['assertions_total']} OK")
    print(f"  status: {'OK' if report.ok() else 'PROBLEM'}")
    print(f"  rapport: {md_path}")
    return 0 if report.ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())

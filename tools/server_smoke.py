"""Läs-bara smoke mot en körande flow-server (t.ex. flow-development).

Loggar in med riktiga uppgifter, öppnar varje vy i sidregistret, väntar på
sidans ready-selector och samlar JS-fel, misslyckade API-svar (>=400) och
skärmdumpar. Klickar ingenting och skriver ingen data — säker mot delade
miljöer, till skillnad från tools.interactive_e2e som skapar poster.

Exempel:
    python -m tools.server_smoke --base-url https://flow-development.nowastelogistics.com \
        --username emikad --password ***
    python -m tools.server_smoke --base-url http://127.0.0.1:8000 --username admin --password admin123
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from tools.visual_smoke import PAGES, VisualPage

# Sidor som saknas i visual_smoke-registret men ska ingå i serversmoken.
EXTRA_PAGES: tuple[VisualPage, ...] = (
    VisualPage("sankey-inbound", "/sankey-inbound.html", "#sankeyInboundDate", ("admin",)),
)

READY_TIMEOUT_MS = 20_000
# Anrop som förväntas kunna svara 4xx utan att sidan är trasig.
IGNORED_STATUS_PATHS = ("/api/auth/me",)


@dataclass
class PageResult:
    page_id: str
    path: str
    status: str  # ok | fel
    ready_ms: int | None = None
    console_errors: list[str] = field(default_factory=list)
    failed_responses: list[str] = field(default_factory=list)
    error: str | None = None


def _login(page, base_url: str, username: str, password: str) -> None:
    page.goto(f"{base_url}/login.html", wait_until="domcontentloaded")
    page.wait_for_selector("#login-form", timeout=READY_TIMEOUT_MS)
    page.fill("#username", username)
    page.fill("#password", password)
    page.click("#login-form button[type=submit], #login-form button")
    page.wait_for_url(lambda url: "login.html" not in url, timeout=READY_TIMEOUT_MS)


def run_server_smoke(
    *,
    base_url: str,
    username: str,
    password: str,
    output_dir: Path,
    headful: bool = False,
    only: set[str] | None = None,
) -> list[PageResult]:
    from playwright.sync_api import sync_playwright

    base_url = base_url.rstrip("/")
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[PageResult] = []

    pages = [p for p in (*PAGES, *EXTRA_PAGES) if p.name != "login"]
    if only:
        pages = [p for p in pages if p.name in only]

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headful)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()

        console_errors: list[str] = []
        failed_responses: list[str] = []
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
        )
        page.on("pageerror", lambda err: console_errors.append(str(err)))
        page.on(
            "response",
            lambda resp: failed_responses.append(f"{resp.status} {resp.url}")
            if resp.status >= 400 and not any(part in resp.url for part in IGNORED_STATUS_PATHS)
            else None,
        )

        _login(page, base_url, username, password)

        for visual in pages:
            console_errors.clear()
            failed_responses.clear()
            result = PageResult(page_id=visual.name, path=visual.path, status="ok")
            started = datetime.now()
            try:
                page.goto(f"{base_url}{visual.path}", wait_until="domcontentloaded")
                page.wait_for_selector(visual.wait_for, timeout=READY_TIMEOUT_MS)
                page.wait_for_load_state("networkidle", timeout=READY_TIMEOUT_MS)
                result.ready_ms = int((datetime.now() - started).total_seconds() * 1000)
            except Exception as exc:  # noqa: BLE001 - en trasig sida ska inte stoppa svepet
                result.status = "fel"
                result.error = str(exc).splitlines()[0][:300]
            result.console_errors = list(console_errors)
            result.failed_responses = list(failed_responses)
            if result.console_errors or result.failed_responses:
                result.status = "fel"
            try:
                page.screenshot(path=str(output_dir / f"{visual.name}.png"), full_page=False)
            except Exception:  # noqa: BLE001
                pass
            results.append(result)
            marker = "OK " if result.status == "ok" else "FEL"
            print(f"  {marker} {visual.name:20s} {result.path}" + (f"  ({result.error})" if result.error else ""))
            for line in result.console_errors[:3]:
                print(f"        js: {line[:160]}")
            for line in result.failed_responses[:5]:
                print(f"        http: {line[:160]}")

        browser.close()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--output", default="artifacts/server_smoke")
    parser.add_argument("--pages", help="Kommaseparerade page_id att begränsa till.")
    parser.add_argument("--headful", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output) / datetime.now().strftime("%Y%m%d-%H%M%S")
    only = {item.strip() for item in args.pages.split(",")} if args.pages else None

    print(f"Serversmoke mot {args.base_url} som {args.username} (läs-bara)")
    results = run_server_smoke(
        base_url=args.base_url,
        username=args.username,
        password=args.password,
        output_dir=output_dir,
        headful=args.headful,
        only=only,
    )

    report = {
        "base_url": args.base_url,
        "username": args.username,
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "pages": [result.__dict__ for result in results],
    }
    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    failed = [result for result in results if result.status != "ok"]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} sidor OK. Rapport: {report_path}")
    if failed:
        print("Trasiga sidor: " + ", ".join(result.page_id for result in failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

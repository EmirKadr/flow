"""Öppna buggrapporter: snabb räkning för agenters arbetsstart-påminnelse.

Skriver en rad om hur många buggrapporter som väntar (status new/seen) så att
agenter kan påminna Emir i början av en arbetsinsats (se AGENTS.md).

Exempel:
  python -m tools.bug_reports_status
  python -m tools.bug_reports_status --base-url https://flow-development.nowastelogistics.com
  python -m tools.bug_reports_status --username admin --password ***

Auth återanvänder healthcheck-verktygets cookie jar (.flow-cli-cookies.txt).
Saknas inloggning avslutar verktyget mjukt (exit 0) med en förklarande rad —
påminnelsen är best effort och får aldrig blockera arbetet.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.healthcheck import DEFAULT_COOKIE_JAR, session_for  # noqa: E402

DEFAULT_BASE_URL = "https://flow-development.nowastelogistics.com"
OPEN_STATUSES = ("new", "seen")
STATUS_LABELS = {"new": "nya", "seen": "att göra"}


def fetch_reports(args: argparse.Namespace) -> list[dict]:
    session = session_for(args)
    response = session.get(f"{args.base_url.rstrip('/')}/api/bug-reports", timeout=args.timeout)
    response.raise_for_status()
    return response.json().get("reports", [])


def summarize(reports: list[dict]) -> str:
    # Ren ASCII + åäö: Windows-konsolen kör cp1252 och kraschar på t.ex. "→".
    open_reports = [r for r in reports if r.get("status") in OPEN_STATUSES]
    if not open_reports:
        return "Inga öppna buggrapporter."
    parts = []
    for status in OPEN_STATUSES:
        count = sum(1 for r in open_reports if r.get("status") == status)
        if count:
            parts.append(f"{count} {STATUS_LABELS[status]}")
    return (
        f"PÅMINNELSE: {len(open_reports)} öppna buggrapporter ({', '.join(parts)}) "
        "- öppna Verktyg / Buggrapporter."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--cookie-jar", type=Path, default=DEFAULT_COOKIE_JAR)
    parser.add_argument("--username", help="Logga in innan anropet (annars cookie jar).")
    parser.add_argument("--password", help="Lösenord för --username.")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--strict", action="store_true", help="Exit 1 vid auth-/nätverksfel i stället för mjuk exit 0.")
    args = parser.parse_args(argv)

    try:
        reports = fetch_reports(args)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        if status in (401, 403):
            print(
                "Buggrapport-påminnelse hoppades över: ingen giltig inloggning "
                f"(HTTP {status}). Logga in en gång med t.ex. "
                "python -m tools.healthcheck report --base-url <url> --username <namn> --password <lösen>."
            )
        else:
            print(f"Buggrapport-påminnelse hoppades över: HTTP {status} från {args.base_url}.")
        return 1 if args.strict else 0
    except requests.RequestException as exc:
        print(f"Buggrapport-påminnelse hoppades över: kunde inte nå {args.base_url} ({exc.__class__.__name__}).")
        return 1 if args.strict else 0

    print(summarize(reports))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

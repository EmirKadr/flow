"""tools.e2e — browser-baserat undersökningsverktyg för Flow.

Loggar in mot en körande miljö och kör namngivna scenarier (skärmbilder,
konsol-/nätverksfångst, DOM-inspektion, assertions) med en agent-läsbar
rapport. Se wiki/e2e-investigation.md. Kör: `python -m tools.e2e --list`.

Publika ytor för att bygga egna scenarier i kod:
"""
from tools.e2e.env import Credentials, resolve_credentials
from tools.e2e.report import Report
from tools.e2e.scenarios import SCENARIOS, Scenario, capture_page
from tools.e2e.session import FlowSession

__all__ = [
    "Credentials",
    "resolve_credentials",
    "Report",
    "FlowSession",
    "SCENARIOS",
    "Scenario",
    "capture_page",
]

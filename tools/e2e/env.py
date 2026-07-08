"""Miljö- och inloggningshantering för e2e-verktyget.

Läser FLOW_E2E_*-variabler ur .env / app/.env (båda gitignorerade, samma
ordning som backendens config.py). Lösenordet returneras men loggas aldrig.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[2]
ENV_FILES = (ROOT / ".env", ROOT / "app" / ".env")
DEFAULT_BASE_URL = "https://flow-development.nowastelogistics.com"


def load_env_files(paths=ENV_FILES) -> None:
    """Minimal .env-inläsning (KEY=VALUE) utan externa beroenden. Skriver bara
    nycklar som inte redan är satta och hoppar över TOMMA värden, så en tom
    placeholder aldrig skuggar ett ifyllt värde. Riktiga miljövariabler vinner."""
    for path in paths:
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value and key not in os.environ:
                os.environ[key] = value


class Credentials(NamedTuple):
    base_url: str
    username: str
    password: str  # returneras för Playwright-inloggning; logga aldrig detta

    def redacted(self) -> str:
        return f"{self.username}@{self.base_url}"


def resolve_credentials(base_url: str | None = None) -> Credentials | None:
    """Returnerar Credentials eller None om användarnamn/lösenord saknas.
    Anroparen ansvarar för att skriva ett hjälpsamt meddelande vid None."""
    load_env_files()
    resolved_base = base_url or os.environ.get("FLOW_E2E_BASE_URL") or DEFAULT_BASE_URL
    username = os.environ.get("FLOW_E2E_USERNAME", "").strip()
    password = os.environ.get("FLOW_E2E_PASSWORD", "")
    if not username or not password:
        return None
    return Credentials(base_url=resolved_base.rstrip("/"), username=username, password=password)


MISSING_CREDENTIALS_HELP = (
    "Inga E2E-uppgifter satta. Lagg till FLOW_E2E_USERNAME och FLOW_E2E_PASSWORD "
    "i app/.env (gitignorerad) och kor igen. FLOW_E2E_BASE_URL ar valfri "
    f"(standard: {DEFAULT_BASE_URL})."
)

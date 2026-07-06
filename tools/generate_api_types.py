"""Generera frontend-typer från backendens OpenAPI-schema.

Kör:  python -m tools.generate_api_types

Dumpar FastAPI:s openapi.json och kör openapi-typescript →
app/frontend/js/types/api-schema.d.ts (incheckad). CI regenererar och failar
på diff, så typerna KAN inte drifta från app/backend/schemas.py: ändras ett
Pydantic-schema måste den här genereringen köras om i samma commit.

Frontendfiler använder typerna via JSDoc:
    /** @type {import("./types/api-schema").components["schemas"]["PersonOut"]} */
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "app" / "frontend" / "js" / "types" / "api-schema.d.ts"

HEADER = (
    "// GENERERAD FIL - redigera inte for hand.\n"
    "// Kalla: app/backend (FastAPI openapi.json) via tools/generate_api_types.py.\n"
    "// Regenerera med: python -m tools.generate_api_types\n"
)


def build_openapi() -> dict:
    os.environ.setdefault("SECRET_KEY", "typegen-only")
    os.environ.setdefault("DATABASE_URL", "sqlite:///./typegen-tmp.db")
    os.environ.setdefault("ENVIRONMENT", "development")
    os.environ.setdefault("SUPER_USER_USERNAMES", "admin")
    os.environ.setdefault("EXCEL_API_TOKEN", "typegen-only")
    os.environ.setdefault("FLOW_DISABLE_BACKGROUND_JOBS", "1")
    sys.path.insert(0, str(ROOT / "app"))
    from backend.main import app  # noqa: PLC0415

    return app.openapi()


def main() -> int:
    spec = build_openapi()
    with tempfile.TemporaryDirectory() as tmp:
        spec_path = Path(tmp) / "openapi.json"
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        npx = "npx.cmd" if os.name == "nt" else "npx"
        result = subprocess.run(
            [npx, "openapi-typescript", str(spec_path), "-o", str(OUTPUT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        return result.returncode
    body = OUTPUT.read_text(encoding="utf-8")
    OUTPUT.write_text(HEADER + body, encoding="utf-8", newline="\n")
    print(f"Skrev {OUTPUT.relative_to(ROOT)} ({len(body.splitlines())} rader).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

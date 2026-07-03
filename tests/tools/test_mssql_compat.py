"""MSSQL-portabilitetskontrakt for SQLAlchemy-fragorna i backend.

Produktionsdatabasen ar MSSQL/Azure SQL (`mssql+pyodbc`). Ett par SQL-monster
som SQLite och PostgreSQL accepterar ar ogiltiga pa SQL Server och maste vaktas:

1. `col.is_(True)` / `col.is_(False)` renderas som `col IS 1` pa MSSQL (SQL Server
   tillater bara `IS NULL`/`IS NOT NULL`) och ger `Incorrect syntax near '1'`.
   Anvand truthy-formen `col` respektive `~col`/`col == False`, som renderas
   `col = 1` / `col = 0` pa alla tre dialekter.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "app" / "backend"

_IS_BOOL_LITERAL = re.compile(r"\.is_\((?:True|False)\)|\.isnot\((?:True|False)\)")


def test_no_is_boolean_literal_in_backend_queries():
    """`.is_(True)`/`.is_(False)` bryter mot SQL Server (`col IS 1`). Anvand
    truthy-kolumnen (`col`) eller `~col` i stallet."""
    offenders = []
    for path in sorted(BACKEND.rglob("*.py")):
        if "alembic/" in path.relative_to(BACKEND).as_posix():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if _IS_BOOL_LITERAL.search(line):
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Boolean-`.is_()` renderas som `col IS 1` och kraschar mot MSSQL. "
        "Byt till truthy-kolumn (`Model.col`) eller `~Model.col`:\n  "
        + "\n  ".join(offenders)
    )


def test_active_filter_compiles_valid_mssql():
    """En representativ is_active-fraga ska rendera `= 1`, inte `IS 1`, mot MSSQL."""
    import sys

    if str(ROOT / "app") not in sys.path:
        sys.path.insert(0, str(ROOT / "app"))
    from sqlalchemy import select
    from sqlalchemy.dialects import mssql

    from backend.models import Person

    compiled = str(select(Person.id).where(Person.is_active).compile(dialect=mssql.dialect()))
    assert "is_active = 1" in compiled
    assert "IS 1" not in compiled

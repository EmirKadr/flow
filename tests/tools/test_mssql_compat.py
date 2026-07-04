"""MSSQL-portabilitetskontrakt for SQLAlchemy-fragorna i backend.

Produktionsdatabasen ar MSSQL/Azure SQL (`mssql+pyodbc`). Ett par SQL-monster
som SQLite och PostgreSQL accepterar ar ogiltiga pa SQL Server och maste vaktas:

1. `col.is_(True)` / `col.is_(False)` renderas som `col IS 1` pa MSSQL (SQL Server
   tillater bara `IS NULL`/`IS NOT NULL`) och ger `Incorrect syntax near '1'`.
   Anvand truthy-formen `col` respektive `~col`/`col == False`, som renderas
   `col = 1` / `col = 0` pa alla tre dialekter.
2. `tuple_(a, b).in_([...])` renderas som `(a, b) IN ((1, 2), ...)` vilket
   SQL Server inte stodjer alls (`An expression of non-boolean type specified
   in a context where a condition is expected`). Anvand en OR-kedja av
   AND-uttryck i stallet (se `routers/overview._ywd_filter`).
3. `GROUP BY` pa uttryck som innehaller Python-strangliteraler (t.ex.
   `coalesce(col1, col2, "fallback")`) parametriseras av pyodbc och SQL Server
   tillater inte bindparametrar i GROUP BY. pymssql interpolerar klientside
   och doljer felet lokalt. Gor NULL-fallbacken i Python i stallet.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "app" / "backend"

_IS_BOOL_LITERAL = re.compile(r"\.is_\((?:True|False)\)|\.isnot\((?:True|False)\)")
_TUPLE_IN = re.compile(r"\btuple_\(")


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


def test_no_tuple_in_in_backend_queries():
    """`tuple_(...).in_(...)` ger `(a, b) IN ((...))` som SQL Server inte stodjer.
    Anvand en OR-kedja av AND-uttryck (jfr `routers/overview._ywd_filter`)."""
    offenders = []
    for path in sorted(BACKEND.rglob("*.py")):
        if "alembic/" in path.relative_to(BACKEND).as_posix():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if _TUPLE_IN.search(line):
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{lineno}: {line.strip()}")
    assert not offenders, (
        "SQLAlchemy tuple-IN kraschar mot MSSQL (icke-boolskt uttryck i villkor). "
        "Skriv om till or_(and_(...), ...):\n  "
        + "\n  ".join(offenders)
    )


def test_personal_productivity_group_by_has_no_bind_params():
    """GROUP BY med bindparameter kraschar pa MSSQL+pyodbc (pymssql doljer det).
    Aktivitetsaggregatets grupputtryck ska rendera utan parametrar."""
    import re
    import sys

    if str(ROOT / "app") not in sys.path:
        sys.path.insert(0, str(ROOT / "app"))
    from sqlalchemy import func, select
    from sqlalchemy.dialects import mssql

    from backend.models import PersonProductivityDaily

    # Samma uttryck som person_productivity_period_stats_if_current grupperar pa.
    activity_label = func.coalesce(
        PersonProductivityDaily.activity_label,
        PersonProductivityDaily.process_label,
    )
    query = select(activity_label, func.count()).group_by(activity_label)
    compiled = str(query.compile(dialect=mssql.dialect()))
    group_by_clause = compiled.split("GROUP BY", 1)[1]
    assert not re.search(r"[:?]", group_by_clause), (
        "Bindparameter i GROUP BY - SQL Server avvisar detta under pyodbc:\n" + compiled
    )


def test_ywd_filter_compiles_valid_mssql():
    """Oversiktens (ar, vecka, veckodag)-filter ska rendera OR/AND, inte tuple-IN."""
    import sys

    if str(ROOT / "app") not in sys.path:
        sys.path.insert(0, str(ROOT / "app"))
    from sqlalchemy import select
    from sqlalchemy.dialects import mssql

    from backend.models import ScheduleCell
    from backend.routers.overview import _ywd_filter

    query = select(ScheduleCell.id).where(_ywd_filter([(2026, 27, 1), (2026, 27, 2)]))
    compiled = str(query.compile(dialect=mssql.dialect()))
    assert ") IN ((" not in compiled
    assert " OR " in compiled and " AND " in compiled

    # Tom lista ska ge ett giltigt alltid-falskt villkor, inte krascha.
    empty = select(ScheduleCell.id).where(_ywd_filter([]))
    str(empty.compile(dialect=mssql.dialect()))

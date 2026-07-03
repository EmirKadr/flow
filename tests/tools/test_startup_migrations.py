"""Kontrakt: appstarten kor alembic upgrade head mot delade databaser.

Rotorsaken till remark-incidenten (Invalid column name mot MSSQL) var att
ingen korde migrationerna vid deploy. `main._run_startup_migrations` ska
kora alembic for icke-SQLite-dialekter och kunna stangas av med env-flaggan.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT / "app") not in sys.path:
    sys.path.insert(0, str(ROOT / "app"))


def _run_with_dialect(monkeypatch, dialect_name: str) -> list[str]:
    from alembic import command
    from backend import main

    calls: list[str] = []
    monkeypatch.setattr(main, "engine", SimpleNamespace(dialect=SimpleNamespace(name=dialect_name)))
    monkeypatch.setattr(command, "upgrade", lambda config, revision: calls.append(revision))
    main._run_startup_migrations()
    return calls


def test_startup_runs_migrations_for_mssql(monkeypatch):
    monkeypatch.delenv("RUN_DB_MIGRATIONS_ON_START", raising=False)
    assert _run_with_dialect(monkeypatch, "mssql") == ["head"]


def test_startup_skips_migrations_for_sqlite(monkeypatch):
    monkeypatch.delenv("RUN_DB_MIGRATIONS_ON_START", raising=False)
    assert _run_with_dialect(monkeypatch, "sqlite") == []


def test_startup_migrations_can_be_disabled(monkeypatch):
    monkeypatch.setenv("RUN_DB_MIGRATIONS_ON_START", "0")
    assert _run_with_dialect(monkeypatch, "mssql") == []


def test_startup_migration_failure_does_not_crash_app(monkeypatch):
    from alembic import command
    from backend import main

    monkeypatch.delenv("RUN_DB_MIGRATIONS_ON_START", raising=False)
    monkeypatch.setattr(main, "engine", SimpleNamespace(dialect=SimpleNamespace(name="mssql")))

    def boom(config, revision):
        raise RuntimeError("migration failed")

    monkeypatch.setattr(command, "upgrade", boom)
    main._run_startup_migrations()  # ska logga, inte kasta

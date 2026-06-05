"""Idempotent schema-setup vid container-start.

Körs av container-entrypoint före uvicorn (se Dockerfile CMD).

- PostgreSQL: kör `alembic upgrade head` (den historiska Render-vägen).
- Azure SQL / övriga dialekter: migrationerna är skrivna för PostgreSQL
  (JSONB, jsonb_build_array, m.m.) och spelar inte upp rent. Skapa därför
  schemat direkt från ORM-modellernas metadata — som använder portabla
  typvarianter (JsonField, Boolean, ...) — och `alembic stamp head` så att
  framtida migration-spårning fungerar.

Operationen är idempotent: finns schemat redan (alembic_version-tabellen
existerar) görs ingenting.
"""
from __future__ import annotations

import subprocess

from sqlalchemy import inspect

from . import models  # noqa: F401  -- registrerar modellerna på Base.metadata
from .database import Base, engine


def _run_alembic(*args: str) -> None:
    subprocess.run(["alembic", *args], check=True)


def ensure_schema() -> None:
    dialect = engine.dialect.name

    if dialect == "postgresql":
        print("PostgreSQL: kör alembic upgrade head ...")
        _run_alembic("upgrade", "head")
        return

    inspector = inspect(engine)
    if inspector.has_table("alembic_version"):
        print(f"Schema finns redan ({dialect}); hoppar over skapande.")
        return

    print(f"Skapar schema fran modeller for {dialect} ...")
    Base.metadata.create_all(engine)
    _run_alembic("stamp", "head")
    print("Schema skapat och alembic stamplad till head.")


def main() -> None:
    ensure_schema()


if __name__ == "__main__":
    main()

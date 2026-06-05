"""Engångskopiering av all data från live-PostgreSQL till Azure SQL.

`pg_dump`/`pg_restore` fungerar inte mot SQL Server, så datan kopieras radvis
via SQLAlchemy istället. Schemat på målet måste finnas FÖRE detta körs
(skapas av `python -m backend.prestart` mot en tom Azure SQL-databas).

Flöde:
    1. Peka DATABASE_URL på en TOM Azure SQL-databas och kör:
           python -m backend.prestart
       (skapar schemat från modellerna och stämplar alembic till head).
    2. Kör denna kopiering:
           SOURCE_DATABASE_URL='postgresql+psycopg://USER:PASS@HOST:5432/flow' \
           DATABASE_URL='mssql+pyodbc://...azure...' \
           python -m backend.migrate_pg_to_mssql

Egenskaper:
    - Kopierar alla tabeller i FK-beroendeordning (target_meta.sorted_tables).
    - Stänger av FK-kontroller under inläsningen (självrefererande FK + ordning).
    - Sätter IDENTITY_INSERT så ursprungliga id:n bevaras.
    - Serialiserar JSONB-värden (dict/list) till JSON-text för NVARCHAR(max).
    - Kör i en transaktion: allt eller inget.

Skriptet är avsiktligt en ren kopiering (läser bara från källan).
"""
from __future__ import annotations

import json
import os
import sys

from sqlalchemy import MetaData, create_engine, insert, inspect, select, text
from sqlalchemy.engine import make_url

from . import models  # noqa: F401  -- registrerar modellerna på Base.metadata
from .database import _normalize_url

SOURCE_ENV_NAMES = ("SOURCE_DATABASE_URL", "LIVE_DATABASE_URL", "FLOW_LIVE_DATABASE_URL")
SKIP_TABLES = {"alembic_version"}


def _coerce(value):
    # JSONB kommer tillbaka som dict/list från psycopg → serialisera till JSON-text
    # så pyodbc kan skriva den till en NVARCHAR(max)-kolumn i Azure SQL.
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _is_identity(conn, table: str, column: str) -> bool:
    result = conn.execute(
        text("SELECT COLUMNPROPERTY(OBJECT_ID(:t), :c, 'IsIdentity')"),
        {"t": table, "c": column},
    ).scalar()
    return bool(result)


def copy_all(source_url: str, target_url: str) -> dict[str, int]:
    target = make_url(target_url)
    if not target.drivername.startswith("mssql"):
        raise ValueError(f"DATABASE_URL måste peka på Azure SQL (mssql+pyodbc), inte {target.drivername}.")

    source_engine = create_engine(_normalize_url(source_url), pool_pre_ping=True)
    target_engine = create_engine(target_url, pool_pre_ping=True)

    target_meta = MetaData()
    target_meta.reflect(bind=target_engine)
    source_inspector = inspect(source_engine)

    stats: dict[str, int] = {}
    try:
        with source_engine.connect() as src, target_engine.begin() as dst:
            if source_engine.dialect.name == "postgresql":
                src.exec_driver_sql("SET TRANSACTION READ ONLY")

            # Stäng av alla FK-kontroller under inläsningen.
            dst.exec_driver_sql("EXEC sp_msforeachtable 'ALTER TABLE ? NOCHECK CONSTRAINT ALL'")

            for table in target_meta.sorted_tables:
                if table.name in SKIP_TABLES:
                    continue
                if not source_inspector.has_table(table.name):
                    stats[table.name] = 0
                    continue

                source_columns = {col["name"] for col in source_inspector.get_columns(table.name)}
                column_names = [col.name for col in table.columns if col.name in source_columns]
                if not column_names:
                    stats[table.name] = 0
                    continue

                statement = select(*[table.c[name] for name in column_names])
                rows = [
                    {key: _coerce(value) for key, value in mapping.items()}
                    for mapping in src.execute(statement).mappings()
                ]
                if not rows:
                    stats[table.name] = 0
                    continue

                pk_columns = [c.name for c in table.primary_key.columns if c.name in column_names]
                identity_column = next((c for c in pk_columns if _is_identity(dst, table.name, c)), None)

                if identity_column:
                    dst.exec_driver_sql(f"SET IDENTITY_INSERT [{table.name}] ON")
                dst.execute(insert(table), rows)
                if identity_column:
                    dst.exec_driver_sql(f"SET IDENTITY_INSERT [{table.name}] OFF")

                stats[table.name] = len(rows)

            # Slå på FK-kontroller igen och validera att datan är konsistent.
            dst.exec_driver_sql("EXEC sp_msforeachtable 'ALTER TABLE ? WITH CHECK CHECK CONSTRAINT ALL'")
    finally:
        source_engine.dispose()
        target_engine.dispose()

    return stats


def main() -> None:
    source_url = next((os.getenv(name) for name in SOURCE_ENV_NAMES if os.getenv(name)), "")
    if not source_url:
        print(f"Sätt källan via en av: {', '.join(SOURCE_ENV_NAMES)}")
        sys.exit(1)

    target_url = os.getenv("DATABASE_URL", "")
    if not target_url:
        print("Sätt DATABASE_URL till Azure SQL-målet.")
        sys.exit(1)

    stats = copy_all(source_url, target_url)
    total = sum(stats.values())
    print(f"Kopierade {total} rader till Azure SQL.")
    for table, count in stats.items():
        print(f"  {table}: {count}")


if __name__ == "__main__":
    main()

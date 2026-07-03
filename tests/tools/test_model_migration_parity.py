"""Paritetskontrakt: varje ORM-tabell/kolumn ska ha en alembic-migration.

Bakgrund: `schedule_cells.remark` fanns i modellen och i migration 0045, men
den deployade MSSQL-databasen hade aldrig fatt migrationen kord och kraschade
med `Invalid column name 'remark'`. Sjalva korningen loses av
`main._run_startup_migrations`; det har kontraktet vaktar den angransande
luckan - att en modellandring landar utan nagon migration alls (lokal SQLite
patchas av bootstrap_local, sa felet syns forst i deployade miljoer).

Kontrollen ar textuell: kolumnnamnet maste namnas i minst en migrationsfil
som ocksa namner tabellen. Det fangar bortglomda migrationer utan att krava
att hela (delvis PG-specifika) kedjan gar att kora pa SQLite.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "app" / "alembic" / "versions"

if str(ROOT / "app") not in sys.path:
    sys.path.insert(0, str(ROOT / "app"))


def _migration_texts() -> list[str]:
    return [path.read_text(encoding="utf-8") for path in sorted(VERSIONS.glob("*.py"))]


def test_every_model_column_has_a_migration():
    from backend.database import Base
    import backend.models  # noqa: F401 - registrerar alla modeller pa Base

    texts = _migration_texts()
    missing = []
    for table in Base.metadata.sorted_tables:
        table_texts = [text for text in texts if f'"{table.name}"' in text or f"'{table.name}'" in text]
        if not table_texts:
            missing.append(f"{table.name}: tabellen namns inte i nagon migration")
            continue
        for column in table.columns:
            if not any(
                f'"{column.name}"' in text or f"'{column.name}'" in text
                for text in table_texts
            ):
                missing.append(f"{table.name}.{column.name}: kolumnen saknar migration")
    assert not missing, (
        "Modellandringar utan alembic-migration driftar deployade databaser "
        "(SQLite doljer det via bootstrap_local). Skriv en migration:\n  "
        + "\n  ".join(missing)
    )

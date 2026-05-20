"""Create schema + seed for local SQLite dev without running alembic.

Migrations target PostgreSQL (JSONB, USING-clauses, etc.) and don't all replay
cleanly on SQLite. For the local preview stack we instead create tables
straight from the model metadata (which uses portable type variants) and run
the idempotent seed.

Production deploys (Render) still go through `alembic upgrade head` from
render.yaml — this module is local-dev only.
"""
from __future__ import annotations

from sqlalchemy import inspect

from .database import Base, engine
from . import models  # noqa: F401  -- register models on Base.metadata
from .seed import run as seed_run


def _sync_lightweight_sqlite_columns() -> None:
    inspector = inspect(engine)

    def columns_for(table: str) -> set[str]:
        if not inspector.has_table(table):
            return set()
        return {column["name"] for column in inspector.get_columns(table)}

    user_columns = columns_for("users")
    person_columns = columns_for("persons")
    activity_columns = columns_for("activities")
    with engine.begin() as connection:
        if user_columns and "area_id" not in user_columns:
            connection.exec_driver_sql("ALTER TABLE users ADD COLUMN area_id INTEGER REFERENCES areas(id)")
        if user_columns and "roles" not in user_columns:
            connection.exec_driver_sql("ALTER TABLE users ADD COLUMN roles JSON")
            connection.exec_driver_sql("UPDATE users SET roles = json_array(role) WHERE roles IS NULL")
        if person_columns and "has_fixed_schedule" not in person_columns:
            connection.exec_driver_sql(
                "ALTER TABLE persons ADD COLUMN has_fixed_schedule BOOLEAN NOT NULL DEFAULT 1"
            )
        if activity_columns and "is_active" in activity_columns:
            connection.exec_driver_sql("UPDATE activities SET is_active = 1 WHERE is_active IS NOT 1")


def main() -> None:
    Base.metadata.create_all(engine)
    _sync_lightweight_sqlite_columns()
    seed_run()


if __name__ == "__main__":
    main()

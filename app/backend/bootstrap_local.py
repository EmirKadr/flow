"""Create schema + seed for local SQLite dev without running alembic.

Migrations target PostgreSQL (JSONB, USING-clauses, etc.) and don't all replay
cleanly on SQLite. For the local preview stack we instead create tables
straight from the model metadata (which uses portable type variants) and run
the idempotent seed.

Production deploys (Render) still go through `alembic upgrade head` from
render.yaml — this module is local-dev only.
"""
from __future__ import annotations

from sqlalchemy import inspect, text

from .database import Base, engine
from . import models  # noqa: F401  -- register models on Base.metadata
from .business_scope import DEFAULT_BUSINESS_CODE, DEFAULT_BUSINESS_NAME, R3_BUSINESS_CODE, R3_BUSINESS_NAME
from .seed import run as seed_run


def _sync_lightweight_sqlite_columns(target_engine=engine) -> None:
    inspector = inspect(target_engine)

    def columns_for(table: str) -> set[str]:
        if not inspector.has_table(table):
            return set()
        return {column["name"] for column in inspector.get_columns(table)}

    user_columns = columns_for("users")
    area_columns = columns_for("areas")
    person_columns = columns_for("persons")
    activity_columns = columns_for("activities")
    audit_columns = columns_for("audit_log")
    settings_columns = columns_for("app_settings")
    with target_engine.begin() as connection:
        if user_columns and "business_id" not in user_columns:
            connection.exec_driver_sql("ALTER TABLE users ADD COLUMN business_id INTEGER REFERENCES businesses(id)")
        if area_columns and "business_id" not in area_columns:
            connection.exec_driver_sql("ALTER TABLE areas ADD COLUMN business_id INTEGER REFERENCES businesses(id)")
        if person_columns and "business_id" not in person_columns:
            connection.exec_driver_sql("ALTER TABLE persons ADD COLUMN business_id INTEGER REFERENCES businesses(id)")
        if activity_columns and "business_id" not in activity_columns:
            connection.exec_driver_sql("ALTER TABLE activities ADD COLUMN business_id INTEGER REFERENCES businesses(id)")
        if audit_columns and "business_id" not in audit_columns:
            connection.exec_driver_sql("ALTER TABLE audit_log ADD COLUMN business_id INTEGER REFERENCES businesses(id)")
        if settings_columns and "business_id" not in settings_columns:
            connection.exec_driver_sql("ALTER TABLE app_settings ADD COLUMN business_id INTEGER REFERENCES businesses(id)")
        if user_columns and "area_id" not in user_columns:
            connection.exec_driver_sql("ALTER TABLE users ADD COLUMN area_id INTEGER REFERENCES areas(id)")
        if user_columns and "roles" not in user_columns:
            connection.exec_driver_sql("ALTER TABLE users ADD COLUMN roles JSON")
            connection.exec_driver_sql("UPDATE users SET roles = json_array(role) WHERE roles IS NULL")
        if person_columns and "has_fixed_schedule" not in person_columns:
            connection.exec_driver_sql(
                "ALTER TABLE persons ADD COLUMN has_fixed_schedule BOOLEAN NOT NULL DEFAULT 1"
            )
        if person_columns and "is_active" in person_columns:
            connection.exec_driver_sql("UPDATE persons SET is_active = 1 WHERE is_active IS NOT 1")
        if activity_columns and "is_active" in activity_columns:
            connection.exec_driver_sql("UPDATE activities SET is_active = 1 WHERE is_active IS NOT 1")


def _table_sql(connection, table_name: str) -> str:
    row = connection.execute(
        text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :name"),
        {"name": table_name},
    ).first()
    return str(row.sql or "") if row is not None else ""


def _rebuild_table(connection, table_name: str, create_sql: str, columns: list[str]) -> None:
    temp_name = f"{table_name}__business_migrate"
    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{temp_name}"')
    connection.exec_driver_sql(create_sql.format(table=temp_name))
    connection.exec_driver_sql(
        f'INSERT INTO "{temp_name}" ({quoted_columns}) SELECT {quoted_columns} FROM "{table_name}"'
    )
    connection.exec_driver_sql(f'DROP TABLE "{table_name}"')
    connection.exec_driver_sql(f'ALTER TABLE "{temp_name}" RENAME TO "{table_name}"')


def _sync_sqlite_business_constraints(target_engine=engine) -> None:
    if target_engine.dialect.name != "sqlite":
        return

    with target_engine.begin() as connection:
        if not inspect(connection).has_table("businesses"):
            return
        connection.exec_driver_sql(
            """
            INSERT OR IGNORE INTO businesses (code, name, sort_order, is_active)
            VALUES (?, ?, ?, ?), (?, ?, ?, ?)
            """,
            (
                DEFAULT_BUSINESS_CODE,
                DEFAULT_BUSINESS_NAME,
                1,
                1,
                R3_BUSINESS_CODE,
                R3_BUSINESS_NAME,
                2,
                1,
            ),
        )
        stigamo_id = connection.execute(
            text("SELECT id FROM businesses WHERE code = :code"),
            {"code": DEFAULT_BUSINESS_CODE},
        ).scalar_one()

        inspector = inspect(connection)
        for table_name in ("users", "areas", "persons", "activities", "audit_log", "app_settings"):
            if not inspector.has_table(table_name):
                continue
            column_names = {column["name"] for column in inspector.get_columns(table_name)}
            if "business_id" in column_names:
                connection.execute(
                    text(f'UPDATE "{table_name}" SET business_id = :business_id WHERE business_id IS NULL'),
                    {"business_id": stigamo_id},
                )

        # Old local SQLite files were created with global UNIQUE(code) and
        # PRIMARY KEY(key). Rebuild only those legacy tables so R3 can have its
        # own area/activity codes and settings without deleting local data.
        areas_sql = _table_sql(connection, "areas")
        if "UNIQUE" in areas_sql and "code" in areas_sql and "UNIQUE (business_id, code)" not in areas_sql:
            _rebuild_table(
                connection,
                "areas",
                """
                CREATE TABLE "{table}" (
                    id INTEGER NOT NULL,
                    business_id INTEGER REFERENCES businesses(id),
                    code VARCHAR(20) NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    sort_order INTEGER NOT NULL,
                    is_active BOOLEAN NOT NULL,
                    PRIMARY KEY (id),
                    UNIQUE (business_id, code)
                )
                """,
                ["id", "business_id", "code", "name", "sort_order", "is_active"],
            )

        activities_sql = _table_sql(connection, "activities")
        if "UNIQUE" in activities_sql and "code" in activities_sql and "UNIQUE (business_id, code)" not in activities_sql:
            _rebuild_table(
                connection,
                "activities",
                """
                CREATE TABLE "{table}" (
                    id INTEGER NOT NULL,
                    business_id INTEGER REFERENCES businesses(id),
                    code VARCHAR(40) NOT NULL,
                    label VARCHAR(60) NOT NULL,
                    area_id INTEGER REFERENCES areas(id),
                    summary_activity_id INTEGER REFERENCES activities(id),
                    color VARCHAR(20) NOT NULL,
                    category VARCHAR(20) NOT NULL,
                    sort_order INTEGER NOT NULL,
                    is_active BOOLEAN NOT NULL,
                    required_competency VARCHAR(40),
                    PRIMARY KEY (id),
                    UNIQUE (business_id, code)
                )
                """,
                [
                    "id",
                    "business_id",
                    "code",
                    "label",
                    "area_id",
                    "summary_activity_id",
                    "color",
                    "category",
                    "sort_order",
                    "is_active",
                    "required_competency",
                ],
            )

        settings_sql = _table_sql(connection, "app_settings")
        if "PRIMARY KEY" in settings_sql and "PRIMARY KEY (business_id" not in settings_sql:
            _rebuild_table(
                connection,
                "app_settings",
                """
                CREATE TABLE "{table}" (
                    business_id INTEGER NOT NULL REFERENCES businesses(id),
                    "key" VARCHAR(80) NOT NULL,
                    value TEXT NOT NULL,
                    updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
                    updated_by INTEGER REFERENCES users(id),
                    PRIMARY KEY (business_id, "key"),
                    UNIQUE (business_id, "key")
                )
                """,
                ["business_id", "key", "value", "updated_at", "updated_by"],
            )


def main() -> None:
    Base.metadata.create_all(engine)
    _sync_lightweight_sqlite_columns()
    _sync_sqlite_business_constraints()
    seed_run()


if __name__ == "__main__":
    main()

from __future__ import annotations

import importlib

import sqlalchemy as sa


def test_activity_kpi_process_backfill_only_fills_empty_values():
    migration = importlib.import_module("app.alembic.versions.0036_backfill_activity_kpi_processes")
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    activities = sa.Table(
        "activities",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String),
        sa.Column("label", sa.String),
        sa.Column("kpi_process_name", sa.String),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            activities.insert(),
            [
                {"id": 1, "code": "GG_PLOCK", "label": "GG Pick", "kpi_process_name": None},
                {"id": 2, "code": "CUSTOM", "label": "AS Utlast GG", "kpi_process_name": ""},
                {"id": 3, "code": "MG_VM", "label": "MG VM", "kpi_process_name": "Manual override"},
            ],
        )
        for codes, labels, processes in migration.ACTIVITY_KPI_PROCESS_MAPPINGS:
            migration._set_activity_processes(connection, codes, labels, processes)

        rows = {
            row.code: row.kpi_process_name
            for row in connection.execute(sa.select(activities.c.code, activities.c.kpi_process_name))
        }

    assert rows["GG_PLOCK"] == "Manual_Pick, Campaign, Order_Split, Flammable"
    assert rows["CUSTOM"] == "Sort_Ecom, Sort_Store"
    assert rows["MG_VM"] == "Manual override"

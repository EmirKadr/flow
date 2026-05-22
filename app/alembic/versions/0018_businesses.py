"""add businesses and scope core data

Revision ID: 0018_businesses
Revises: 0017_rename_activity_view_ids
Create Date: 2026-05-22
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "0018_businesses"
down_revision: Union[str, None] = "0017_rename_activity_view_ids"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


CORE_TABLES = ("users", "areas", "persons", "activities", "audit_log")


def _business_id(code: str) -> int:
    connection = op.get_bind()
    row = connection.execute(sa.text("SELECT id FROM businesses WHERE code = :code"), {"code": code}).first()
    if row is None:
        raise RuntimeError(f"Missing seeded business {code}")
    return int(row.id)


def upgrade() -> None:
    op.create_table(
        "businesses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            INSERT INTO businesses (code, name, sort_order, is_active)
            VALUES
                ('STIGAMO', 'Stigamo', 1, true),
                ('R3', 'R3', 2, true)
            """
        )
    )
    stigamo_id = _business_id("STIGAMO")

    for table_name in CORE_TABLES:
        op.add_column(table_name, sa.Column("business_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_{table_name}_business_id_businesses",
            table_name,
            "businesses",
            ["business_id"],
            ["id"],
        )
        connection.execute(
            sa.text(f"UPDATE {table_name} SET business_id = :business_id WHERE business_id IS NULL"),
            {"business_id": stigamo_id},
        )

    op.add_column("app_settings", sa.Column("business_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_app_settings_business_id_businesses",
        "app_settings",
        "businesses",
        ["business_id"],
        ["id"],
    )
    connection.execute(
        sa.text("UPDATE app_settings SET business_id = :business_id WHERE business_id IS NULL"),
        {"business_id": stigamo_id},
    )
    op.alter_column("app_settings", "business_id", nullable=False)

    op.drop_constraint("areas_code_key", "areas", type_="unique")
    op.drop_constraint("activities_code_key", "activities", type_="unique")
    op.create_unique_constraint("uq_areas_business_code", "areas", ["business_id", "code"])
    op.create_unique_constraint("uq_activities_business_code", "activities", ["business_id", "code"])

    op.drop_constraint("app_settings_pkey", "app_settings", type_="primary")
    op.create_primary_key("app_settings_pkey", "app_settings", ["business_id", "key"])
    op.create_unique_constraint("uq_app_settings_business_key", "app_settings", ["business_id", "key"])


def downgrade() -> None:
    connection = op.get_bind()
    stigamo_id = _business_id("STIGAMO")

    connection.execute(sa.text("DELETE FROM app_settings WHERE business_id <> :business_id"), {"business_id": stigamo_id})
    connection.execute(sa.text("DELETE FROM activities WHERE business_id <> :business_id"), {"business_id": stigamo_id})
    connection.execute(sa.text("DELETE FROM areas WHERE business_id <> :business_id"), {"business_id": stigamo_id})

    op.drop_constraint("uq_app_settings_business_key", "app_settings", type_="unique")
    op.drop_constraint("app_settings_pkey", "app_settings", type_="primary")
    op.create_primary_key("app_settings_pkey", "app_settings", ["key"])
    op.drop_constraint("fk_app_settings_business_id_businesses", "app_settings", type_="foreignkey")
    op.drop_column("app_settings", "business_id")

    op.drop_constraint("uq_activities_business_code", "activities", type_="unique")
    op.drop_constraint("uq_areas_business_code", "areas", type_="unique")
    op.create_unique_constraint("activities_code_key", "activities", ["code"])
    op.create_unique_constraint("areas_code_key", "areas", ["code"])

    for table_name in reversed(CORE_TABLES):
        op.drop_constraint(f"fk_{table_name}_business_id_businesses", table_name, type_="foreignkey")
        op.drop_column(table_name, "business_id")

    op.drop_table("businesses")

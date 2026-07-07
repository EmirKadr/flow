"""staffing calculator profiles

Revision ID: 0037_staffing_calc
Revises: 0036_activity_kpi_backfill
Create Date: 2026-06-09
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "0037_staffing_calc"
down_revision: Union[str, None] = "0036_activity_kpi_backfill"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.create_table(
        "staffing_calculator_profiles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("staffing_calculator_profiles")

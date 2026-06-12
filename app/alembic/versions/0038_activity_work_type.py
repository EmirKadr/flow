"""activity work type

Revision ID: 0038_activity_work_type
Revises: 0037_staffing_calc
Create Date: 2026-06-10
"""
from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0038_activity_work_type"
down_revision: Union[str, None] = "0037_staffing_calc"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.add_column(
        "activities",
        sa.Column("work_type", sa.String(length=20), nullable=False, server_default="normal"),
    )


def downgrade() -> None:
    op.drop_column("activities", "work_type")

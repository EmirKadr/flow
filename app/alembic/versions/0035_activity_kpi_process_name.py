"""add activity kpi process name

Revision ID: 0035_activity_kpi
Revises: 0034_alloc_filter_profiles
Create Date: 2026-06-08
"""
from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0035_activity_kpi"
down_revision: Union[str, None] = "0034_alloc_filter_profiles"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.add_column("activities", sa.Column("kpi_process_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("activities", "kpi_process_name")

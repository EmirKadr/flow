"""add allocation user filter profiles

Revision ID: 0034_allocation_user_filter_profiles
Revises: 0033_schedule_loan_area
Create Date: 2026-06-08
"""
from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0034_allocation_user_filter_profiles"
down_revision: Union[str, None] = "0033_schedule_loan_area"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.create_table(
        "allocation_user_filter_profiles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("allocation_user_filter_profiles")

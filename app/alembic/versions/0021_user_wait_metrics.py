"""add user wait metrics

Revision ID: 0021_user_wait_metrics
Revises: 0020_person_noman
Create Date: 2026-05-26
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0021_user_wait_metrics"
down_revision: Union[str, None] = "0020_person_noman"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.create_table(
        "user_wait_metrics",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("business_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("view_id", sa.String(length=80), nullable=True),
        sa.Column("target", sa.String(length=160), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ok"),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_user_wait_metrics_created_at", "user_wait_metrics", ["created_at"])
    op.create_index("ix_user_wait_metrics_view_target", "user_wait_metrics", ["view_id", "target"])


def downgrade() -> None:
    op.drop_index("ix_user_wait_metrics_view_target", table_name="user_wait_metrics")
    op.drop_index("ix_user_wait_metrics_created_at", table_name="user_wait_metrics")
    op.drop_table("user_wait_metrics")

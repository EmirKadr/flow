"""add user interaction events

Revision ID: 0032_user_interaction_events
Revises: 0031_drop_meta_media_data_column
Create Date: 2026-06-04
"""
from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0032_user_interaction_events"
down_revision: Union[str, None] = "0031_drop_meta_media_data_column"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.create_table(
        "user_interaction_events",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("business_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("view_id", sa.String(length=80), nullable=True),
        sa.Column("page_path", sa.String(length=300), nullable=True),
        sa.Column("control_id", sa.String(length=160), nullable=True),
        sa.Column("control_label", sa.String(length=180), nullable=True),
        sa.Column("control_role", sa.String(length=80), nullable=True),
        sa.Column("feature", sa.String(length=80), nullable=True),
        sa.Column("flow_id", sa.String(length=120), nullable=True),
        sa.Column("table_key", sa.String(length=120), nullable=True),
        sa.Column("table_label", sa.String(length=160), nullable=True),
        sa.Column("column_index", sa.Integer(), nullable=True),
        sa.Column("column_label", sa.String(length=180), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("client_surface", sa.String(length=40), nullable=True),
        sa.Column("interaction_id", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ok"),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_user_interaction_events_created_at", "user_interaction_events", ["created_at"])
    op.create_index(
        "ix_user_interaction_events_business_created",
        "user_interaction_events",
        ["business_id", "created_at"],
    )
    op.create_index(
        "ix_user_interaction_events_user_created",
        "user_interaction_events",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_user_interaction_events_view_control",
        "user_interaction_events",
        ["view_id", "control_id"],
    )
    op.create_index(
        "ix_user_interaction_events_feature_flow",
        "user_interaction_events",
        ["feature", "flow_id"],
    )
    op.create_index(
        "ix_user_interaction_events_table_column",
        "user_interaction_events",
        ["table_key", "column_label"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_interaction_events_table_column", table_name="user_interaction_events")
    op.drop_index("ix_user_interaction_events_feature_flow", table_name="user_interaction_events")
    op.drop_index("ix_user_interaction_events_view_control", table_name="user_interaction_events")
    op.drop_index("ix_user_interaction_events_user_created", table_name="user_interaction_events")
    op.drop_index("ix_user_interaction_events_business_created", table_name="user_interaction_events")
    op.drop_index("ix_user_interaction_events_created_at", table_name="user_interaction_events")
    op.drop_table("user_interaction_events")

"""add wait metric filter indexes

Revision ID: 0040_wait_metric_indexes
Revises: 0039_person_productivity_daily
Create Date: 2026-06-14
"""

from __future__ import annotations

from typing import Union

from alembic import op


revision: str = "0040_wait_metric_indexes"
down_revision: Union[str, None] = "0039_person_productivity_daily"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_index(
        "ix_user_wait_metrics_business_created",
        "user_wait_metrics",
        ["business_id", "created_at"],
    )
    op.create_index(
        "ix_user_wait_metrics_user_created",
        "user_wait_metrics",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_user_wait_metrics_event_created",
        "user_wait_metrics",
        ["event_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_wait_metrics_event_created", table_name="user_wait_metrics")
    op.drop_index("ix_user_wait_metrics_user_created", table_name="user_wait_metrics")
    op.drop_index("ix_user_wait_metrics_business_created", table_name="user_wait_metrics")

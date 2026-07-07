"""person productivity daily cache

Revision ID: 0039_person_productivity_daily
Revises: 0038_activity_work_type
Create Date: 2026-06-10
"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0039_person_productivity_daily"
down_revision: Union[str, None] = "0038_activity_work_type"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "person_productivity_daily",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("business_id", sa.Integer(), nullable=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("row_type", sa.String(length=20), nullable=False),
        sa.Column("item_key", sa.String(length=255), nullable=False),
        sa.Column("metric", sa.String(length=40), nullable=False),
        sa.Column("unit", sa.String(length=40), nullable=True),
        sa.Column("activity_id", sa.Integer(), nullable=True),
        sa.Column("activity_label", sa.String(length=120), nullable=True),
        sa.Column("process_key", sa.String(length=120), nullable=True),
        sa.Column("process_label", sa.String(length=255), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=True),
        sa.Column("start_minute", sa.Integer(), nullable=True),
        sa.Column("end_minute", sa.Integer(), nullable=True),
        sa.Column("kpi_points", sa.Float(), nullable=False),
        sa.Column("planned_kpi_points", sa.Float(), nullable=False),
        sa.Column("kpi_minutes", sa.Integer(), nullable=False),
        sa.Column("support_minutes", sa.Integer(), nullable=False),
        sa.Column("absence_minutes", sa.Integer(), nullable=False),
        sa.Column("units", sa.Float(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("diff_count", sa.Integer(), nullable=False),
        sa.Column("source_snapshot_at", sa.String(length=40), nullable=True),
        sa.Column("schedule_signature", sa.String(length=120), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"]),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_id",
            "snapshot_date",
            "person_id",
            "row_type",
            "item_key",
            "metric",
            name="uq_person_productivity_daily_row",
        ),
    )
    op.create_index(
        "ix_person_productivity_daily_lookup",
        "person_productivity_daily",
        ["business_id", "snapshot_date", "person_id", "row_type"],
    )
    op.create_index(
        "ix_person_productivity_daily_process",
        "person_productivity_daily",
        ["business_id", "process_key", "snapshot_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_person_productivity_daily_process", table_name="person_productivity_daily")
    op.drop_index("ix_person_productivity_daily_lookup", table_name="person_productivity_daily")
    op.drop_table("person_productivity_daily")

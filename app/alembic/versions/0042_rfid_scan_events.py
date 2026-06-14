"""rfid scan events

Revision ID: 0042_rfid_scan_events
Revises: 0041_company_rfid
Create Date: 2026-06-14
"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0042_rfid_scan_events"
down_revision: Union[str, None] = "0041_company_rfid"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.create_table(
        "rfid_devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("business_id", sa.Integer(), nullable=True),
        sa.Column("device_id", sa.String(length=120), nullable=False),
        sa.Column("module_name", sa.String(length=120), nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"]),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id"),
    )
    op.create_index("ix_rfid_devices_business_activity", "rfid_devices", ["business_id", "activity_id"])
    op.create_table(
        "rfid_scan_events",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("business_id", sa.Integer(), nullable=True),
        sa.Column("device_id", sa.Integer(), nullable=True),
        sa.Column("device_identifier", sa.String(length=120), nullable=False),
        sa.Column("module_name", sa.String(length=120), nullable=False),
        sa.Column("tag_code", sa.String(length=120), nullable=False),
        sa.Column("tag_dec", sa.String(length=120), nullable=True),
        sa.Column("scan_count", sa.Integer(), nullable=True),
        sa.Column("person_id", sa.Integer(), nullable=True),
        sa.Column("activity_id", sa.Integer(), nullable=True),
        sa.Column("scan_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_by", sa.Integer(), nullable=True),
        sa.Column("ignored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ignored_by", sa.Integer(), nullable=True),
        sa.Column("schedule_year", sa.SmallInteger(), nullable=True),
        sa.Column("schedule_week", sa.SmallInteger(), nullable=True),
        sa.Column("schedule_weekday", sa.SmallInteger(), nullable=True),
        sa.Column("schedule_hour", sa.SmallInteger(), nullable=True),
        sa.Column("schedule_minute", sa.SmallInteger(), nullable=True),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"]),
        sa.ForeignKeyConstraint(["applied_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["device_id"], ["rfid_devices.id"]),
        sa.ForeignKeyConstraint(["ignored_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rfid_scan_events_scan_time", "rfid_scan_events", ["scan_time"])
    op.create_index("ix_rfid_scan_events_business_scan_time", "rfid_scan_events", ["business_id", "scan_time"])
    op.create_index("ix_rfid_scan_events_person_scan_time", "rfid_scan_events", ["person_id", "scan_time"])
    op.create_index("ix_rfid_scan_events_status", "rfid_scan_events", ["status"])


def downgrade() -> None:
    op.drop_index("ix_rfid_scan_events_status", table_name="rfid_scan_events")
    op.drop_index("ix_rfid_scan_events_person_scan_time", table_name="rfid_scan_events")
    op.drop_index("ix_rfid_scan_events_business_scan_time", table_name="rfid_scan_events")
    op.drop_index("ix_rfid_scan_events_scan_time", table_name="rfid_scan_events")
    op.drop_table("rfid_scan_events")
    op.drop_index("ix_rfid_devices_business_activity", table_name="rfid_devices")
    op.drop_table("rfid_devices")

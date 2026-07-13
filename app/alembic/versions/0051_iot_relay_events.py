"""iot relay events

Revision ID: 0051_iot_relay_events
Revises: 0050_dpak_raw_perf_idx
Create Date: 2026-07-13
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0051_iot_relay_events"
down_revision: Union[str, None] = "0050_dpak_raw_perf_idx"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.create_table(
        "iot_relay_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_iot_relay_events_device_id", "iot_relay_events", ["device_id"])
    op.create_index("ix_iot_relay_events_received_at", "iot_relay_events", ["received_at"])


def downgrade() -> None:
    op.drop_index("ix_iot_relay_events_received_at", table_name="iot_relay_events")
    op.drop_index("ix_iot_relay_events_device_id", table_name="iot_relay_events")
    op.drop_table("iot_relay_events")

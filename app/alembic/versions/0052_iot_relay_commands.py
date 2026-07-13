"""iot relay commands

Revision ID: 0052_iot_relay_commands
Revises: 0051_iot_relay_events
Create Date: 2026-07-13
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0052_iot_relay_commands"
down_revision: Union[str, None] = "0051_iot_relay_events"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.create_table(
        "iot_relay_commands",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.String(length=80), nullable=False),
        sa.Column("command", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_iot_relay_commands_device_id", "iot_relay_commands", ["device_id"])
    op.create_index("ix_iot_relay_commands_created_at", "iot_relay_commands", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_iot_relay_commands_created_at", table_name="iot_relay_commands")
    op.drop_index("ix_iot_relay_commands_device_id", table_name="iot_relay_commands")
    op.drop_table("iot_relay_commands")

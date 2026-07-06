"""leader leases

Revision ID: 0046_leader_leases
Revises: 0045_schedule_cell_remark
Create Date: 2026-07-06
"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0046_leader_leases"
down_revision: Union[str, None] = "0045_schedule_cell_remark"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.create_table(
        "leader_leases",
        sa.Column("name", sa.String(length=100), primary_key=True),
        sa.Column("holder_id", sa.String(length=64), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("leader_leases")

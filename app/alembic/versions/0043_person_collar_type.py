"""person collar type

Revision ID: 0043_person_collar_type
Revises: 0042_rfid_scan_events
Create Date: 2026-06-15
"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0043_person_collar_type"
down_revision: Union[str, None] = "0042_rfid_scan_events"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.add_column(
        "persons",
        sa.Column("collar_type", sa.String(length=20), nullable=False, server_default="blue_collar"),
    )


def downgrade() -> None:
    op.drop_column("persons", "collar_type")

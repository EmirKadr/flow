"""add explicit empty override to schedule cells

Revision ID: 0007_schedule_empty_override
Revises: 0006_activity_summary_mapping
Create Date: 2026-05-13
"""

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_schedule_empty_override"
down_revision: Union[str, None] = "0006_activity_summary_mapping"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schedule_cells",
        sa.Column("empty_override", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("schedule_cells", "empty_override", server_default=None)


def downgrade() -> None:
    op.drop_column("schedule_cells", "empty_override")

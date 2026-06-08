"""add loan area marker to schedule cells

Revision ID: 0033_schedule_loan_area
Revises: 0032_user_interaction_events
Create Date: 2026-06-08
"""

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0033_schedule_loan_area"
down_revision: Union[str, None] = "0032_user_interaction_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schedule_cells",
        sa.Column("loan_area_id", sa.Integer(), sa.ForeignKey("areas.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("schedule_cells", "loan_area_id")

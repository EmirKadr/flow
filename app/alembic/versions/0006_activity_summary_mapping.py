"""add activity summary mapping

Revision ID: 0006_activity_summary_mapping
Revises: 0005_half_hour_schedule_cells
Create Date: 2026-05-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_activity_summary_mapping"
down_revision: Union[str, None] = "0005_half_hour_schedule_cells"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("activities", sa.Column("summary_activity_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_activities_summary_activity_id",
        "activities",
        "activities",
        ["summary_activity_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_activities_summary_activity_id", "activities", type_="foreignkey")
    op.drop_column("activities", "summary_activity_id")

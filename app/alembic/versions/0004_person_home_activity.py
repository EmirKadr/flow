"""add persons.home_activity_id

Revision ID: 0004_person_home_activity
Revises: 0003_widen_audit_action
Create Date: 2026-05-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_person_home_activity"
down_revision: Union[str, None] = "0003_widen_audit_action"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "persons",
        sa.Column("home_activity_id", sa.Integer(), sa.ForeignKey("activities.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("persons", "home_activity_id")

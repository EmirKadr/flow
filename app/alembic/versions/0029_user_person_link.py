"""link users to persons for personal views

Revision ID: 0029_user_person_link
Revises: 0028_coredata_files
Create Date: 2026-06-02
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0029_user_person_link"
down_revision: Union[str, None] = "0028_coredata_files"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("person_id", sa.Integer(), sa.ForeignKey("persons.id"), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "person_id")

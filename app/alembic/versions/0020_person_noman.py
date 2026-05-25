"""add person noman

Revision ID: 0020_person_noman
Revises: 0019_keep_users_active
Create Date: 2026-05-25
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0020_person_noman"
down_revision: Union[str, None] = "0019_keep_users_active"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.add_column("persons", sa.Column("noman", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("persons", "noman")

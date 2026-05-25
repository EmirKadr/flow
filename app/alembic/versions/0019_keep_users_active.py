"""keep users active

Revision ID: 0019_keep_users_active
Revises: 0018_businesses
Create Date: 2026-05-25
"""
from typing import Union

from alembic import op


revision: str = "0019_keep_users_active"
down_revision: Union[str, None] = "0018_businesses"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET is_active = TRUE WHERE is_active IS NOT TRUE")


def downgrade() -> None:
    pass

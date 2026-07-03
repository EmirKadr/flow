"""keep activities active

Revision ID: 0014_keep_activities_active
Revises: 0013_user_roles
Create Date: 2026-05-20
"""
from typing import Union

from alembic import op


revision: str = "0014_keep_activities_active"
down_revision: Union[str, None] = "0013_user_roles"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("UPDATE activities SET is_active = TRUE WHERE is_active IS NOT TRUE")
    else:
        # MSSQL/SQLite: boolean lagras som 0/1 och TRUE-literalen ar ogiltig T-SQL.
        op.execute("UPDATE activities SET is_active = 1 WHERE is_active IS NULL OR is_active = 0")


def downgrade() -> None:
    pass

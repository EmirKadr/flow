"""keep persons active

Revision ID: 0016_keep_persons_active
Revises: 0015_deduplicate_person_names
Create Date: 2026-05-21
"""
from typing import Union

from alembic import op


revision: str = "0016_keep_persons_active"
down_revision: Union[str, None] = "0015_deduplicate_person_names"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("UPDATE persons SET is_active = TRUE WHERE is_active IS NOT TRUE")
    else:
        # MSSQL/SQLite: boolean lagras som 0/1 och TRUE-literalen ar ogiltig T-SQL.
        op.execute("UPDATE persons SET is_active = 1 WHERE is_active IS NULL OR is_active = 0")


def downgrade() -> None:
    pass

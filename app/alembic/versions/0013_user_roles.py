"""add multi-role support to users

Revision ID: 0013_user_roles
Revises: 0012_person_fixed_schedule_flag
Create Date: 2026-05-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0013_user_roles"
down_revision: Union[str, None] = "0012_person_fixed_schedule_flag"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    column_type = postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON()
    op.add_column("users", sa.Column("roles", column_type, nullable=True))
    if is_postgres:
        op.execute("UPDATE users SET roles = jsonb_build_array(role) WHERE roles IS NULL")
    elif bind.dialect.name == "sqlite":
        op.execute("UPDATE users SET roles = json_array(role) WHERE roles IS NULL")


def downgrade() -> None:
    op.drop_column("users", "roles")

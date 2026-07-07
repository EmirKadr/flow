"""business tenant

Revision ID: 0044_business_tenant
Revises: 0043_person_collar_type
Create Date: 2026-06-15
"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0044_business_tenant"
down_revision: Union[str, None] = "0043_person_collar_type"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.add_column("businesses", sa.Column("tenant", sa.String(length=80), nullable=True))
    op.execute("UPDATE businesses SET tenant = 'frey' WHERE upper(code) = 'STIGAMO' AND tenant IS NULL")
    op.execute("UPDATE businesses SET tenant = 'loki' WHERE upper(code) = 'R3' AND tenant IS NULL")
    op.execute("UPDATE businesses SET tenant = 'itworks' WHERE upper(code) = 'T3' AND tenant IS NULL")


def downgrade() -> None:
    op.drop_column("businesses", "tenant")

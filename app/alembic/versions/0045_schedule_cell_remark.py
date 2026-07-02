"""schedule cell remark

Revision ID: 0045_schedule_cell_remark
Revises: 0044_business_tenant
Create Date: 2026-07-02
"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0045_schedule_cell_remark"
down_revision: Union[str, None] = "0044_business_tenant"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.add_column("schedule_cells", sa.Column("remark", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("schedule_cells", "remark")

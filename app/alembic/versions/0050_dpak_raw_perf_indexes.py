"""public dpak raw performance indexes

Revision ID: 0050_dpak_raw_perf_idx
Revises: 0049_dpak_raw_agent
Create Date: 2026-07-08
"""
from __future__ import annotations

from typing import Union

from alembic import op


revision: str = "0050_dpak_raw_perf_idx"
down_revision: Union[str, None] = "0049_dpak_raw_agent"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_public_dpak_raw_pick_business_item_order",
        "public_dpak_raw_picklog",
        ["business_code", "item_num", "order_num"],
    )
    op.create_index(
        "ix_public_dpak_raw_pick_business_location_order_item",
        "public_dpak_raw_picklog",
        ["business_code", "location", "order_num", "item_num"],
    )


def downgrade() -> None:
    op.drop_index("ix_public_dpak_raw_pick_business_location_order_item", table_name="public_dpak_raw_picklog")
    op.drop_index("ix_public_dpak_raw_pick_business_item_order", table_name="public_dpak_raw_picklog")

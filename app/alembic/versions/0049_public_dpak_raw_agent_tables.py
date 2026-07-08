"""public dpak raw agent tables

Revision ID: 0049_dpak_raw_agent
Revises: 0048_public_dpak_chat
Create Date: 2026-07-08
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0049_dpak_raw_agent"
down_revision: Union[str, None] = "0048_public_dpak_chat"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


JSON_TYPE = sa.JSON().with_variant(JSONB(), "postgresql")
BIGINT_ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "public_dpak_raw_picklog",
        sa.Column("id", BIGINT_ID, primary_key=True, autoincrement=True),
        sa.Column("business_code", sa.String(length=50), nullable=False),
        sa.Column("source_view", sa.String(length=80), nullable=True),
        sa.Column("source_file", sa.String(length=255), nullable=True),
        sa.Column("source_rowid", sa.String(length=120), nullable=True),
        sa.Column("chunk_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chunk_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_index", sa.BigInteger(), nullable=True),
        sa.Column("pick_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_int", sa.Integer(), nullable=True),
        sa.Column("company", sa.String(length=30), nullable=True),
        sa.Column("zone", sa.String(length=20), nullable=True),
        sa.Column("order_num", sa.String(length=80), nullable=True),
        sa.Column("customer_num", sa.String(length=80), nullable=True),
        sa.Column("customer_desc", sa.String(length=255), nullable=True),
        sa.Column("line_num", sa.String(length=80), nullable=True),
        sa.Column("item_num", sa.String(length=80), nullable=True),
        sa.Column("item_desc", sa.String(length=255), nullable=True),
        sa.Column("location", sa.String(length=120), nullable=True),
        sa.Column("pick_pall_num", sa.String(length=120), nullable=True),
        sa.Column("qty_pre", sa.Float(), nullable=True),
        sa.Column("qty_suf", sa.Float(), nullable=True),
        sa.Column("data", JSON_TYPE, nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_public_dpak_raw_pick_business_date", "public_dpak_raw_picklog", ["business_code", "pick_date"])
    op.create_index("ix_public_dpak_raw_pick_business_company", "public_dpak_raw_picklog", ["business_code", "company"])
    op.create_index("ix_public_dpak_raw_pick_business_zone", "public_dpak_raw_picklog", ["business_code", "zone"])
    op.create_index("ix_public_dpak_raw_pick_business_order", "public_dpak_raw_picklog", ["business_code", "order_num"])
    op.create_index("ix_public_dpak_raw_pick_business_item", "public_dpak_raw_picklog", ["business_code", "item_num"])
    op.create_index("ix_public_dpak_raw_pick_business_location", "public_dpak_raw_picklog", ["business_code", "location"])
    op.create_index("ix_public_dpak_raw_pick_business_box", "public_dpak_raw_picklog", ["business_code", "pick_pall_num"])
    op.create_index("ix_public_dpak_raw_pick_business_source", "public_dpak_raw_picklog", ["business_code", "source_view"])

    op.create_table(
        "public_dpak_raw_item_alias",
        sa.Column("id", BIGINT_ID, primary_key=True, autoincrement=True),
        sa.Column("business_code", sa.String(length=50), nullable=False),
        sa.Column("source_file", sa.String(length=255), nullable=True),
        sa.Column("row_index", sa.BigInteger(), nullable=True),
        sa.Column("item_num", sa.String(length=80), nullable=True),
        sa.Column("company", sa.String(length=30), nullable=True),
        sa.Column("alias", sa.String(length=120), nullable=True),
        sa.Column("unit", sa.String(length=40), nullable=True),
        sa.Column("factor", sa.Float(), nullable=True),
        sa.Column("data", JSON_TYPE, nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_public_dpak_raw_alias_business_item", "public_dpak_raw_item_alias", ["business_code", "item_num"])
    op.create_index("ix_public_dpak_raw_alias_business_company", "public_dpak_raw_item_alias", ["business_code", "company"])
    op.create_index("ix_public_dpak_raw_alias_business_unit", "public_dpak_raw_item_alias", ["business_code", "unit"])

    op.create_table(
        "public_dpak_raw_item_attribute",
        sa.Column("id", BIGINT_ID, primary_key=True, autoincrement=True),
        sa.Column("business_code", sa.String(length=50), nullable=False),
        sa.Column("source_file", sa.String(length=255), nullable=True),
        sa.Column("row_index", sa.BigInteger(), nullable=True),
        sa.Column("item_num", sa.String(length=80), nullable=True),
        sa.Column("company", sa.String(length=30), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("value", sa.String(length=255), nullable=True),
        sa.Column("data", JSON_TYPE, nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_public_dpak_raw_attr_business_item", "public_dpak_raw_item_attribute", ["business_code", "item_num"])
    op.create_index("ix_public_dpak_raw_attr_business_company", "public_dpak_raw_item_attribute", ["business_code", "company"])
    op.create_index("ix_public_dpak_raw_attr_business_name", "public_dpak_raw_item_attribute", ["business_code", "name"])
    op.create_index("ix_public_dpak_raw_attr_business_value", "public_dpak_raw_item_attribute", ["business_code", "value"])


def downgrade() -> None:
    op.drop_index("ix_public_dpak_raw_attr_business_value", table_name="public_dpak_raw_item_attribute")
    op.drop_index("ix_public_dpak_raw_attr_business_name", table_name="public_dpak_raw_item_attribute")
    op.drop_index("ix_public_dpak_raw_attr_business_company", table_name="public_dpak_raw_item_attribute")
    op.drop_index("ix_public_dpak_raw_attr_business_item", table_name="public_dpak_raw_item_attribute")
    op.drop_table("public_dpak_raw_item_attribute")

    op.drop_index("ix_public_dpak_raw_alias_business_unit", table_name="public_dpak_raw_item_alias")
    op.drop_index("ix_public_dpak_raw_alias_business_company", table_name="public_dpak_raw_item_alias")
    op.drop_index("ix_public_dpak_raw_alias_business_item", table_name="public_dpak_raw_item_alias")
    op.drop_table("public_dpak_raw_item_alias")

    op.drop_index("ix_public_dpak_raw_pick_business_source", table_name="public_dpak_raw_picklog")
    op.drop_index("ix_public_dpak_raw_pick_business_box", table_name="public_dpak_raw_picklog")
    op.drop_index("ix_public_dpak_raw_pick_business_location", table_name="public_dpak_raw_picklog")
    op.drop_index("ix_public_dpak_raw_pick_business_item", table_name="public_dpak_raw_picklog")
    op.drop_index("ix_public_dpak_raw_pick_business_order", table_name="public_dpak_raw_picklog")
    op.drop_index("ix_public_dpak_raw_pick_business_zone", table_name="public_dpak_raw_picklog")
    op.drop_index("ix_public_dpak_raw_pick_business_company", table_name="public_dpak_raw_picklog")
    op.drop_index("ix_public_dpak_raw_pick_business_date", table_name="public_dpak_raw_picklog")
    op.drop_table("public_dpak_raw_picklog")

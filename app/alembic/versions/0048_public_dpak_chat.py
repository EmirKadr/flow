"""public dpak chat data tables

Revision ID: 0048_public_dpak_chat
Revises: 0047_bug_reports
Create Date: 2026-07-07
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0048_public_dpak_chat"
down_revision: Union[str, None] = "0047_bug_reports"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


JSON_TYPE = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "public_dpak_datasets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("business_code", sa.String(length=50), nullable=False),
        sa.Column("coverage_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("coverage_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pick_rows", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("order_article_rows", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("order_supplier_rows", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("alias_rows", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("attribute_rows", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("source_summary", JSON_TYPE, nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="missing"),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("built_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("business_code", name="uq_public_dpak_datasets_business"),
    )

    op.create_table(
        "public_dpak_sync_chunks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("business_code", sa.String(length=50), nullable=False),
        sa.Column("source_view", sa.String(length=80), nullable=False),
        sa.Column("chunk_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("chunk_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("row_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "business_code",
            "source_view",
            "chunk_start",
            "chunk_end",
            name="uq_public_dpak_sync_chunk",
        ),
    )
    op.create_index(
        "ix_public_dpak_sync_business_status",
        "public_dpak_sync_chunks",
        ["business_code", "status"],
    )
    op.create_index(
        "ix_public_dpak_sync_business_view",
        "public_dpak_sync_chunks",
        ["business_code", "source_view"],
    )

    op.create_table(
        "public_dpak_pick_rows",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("business_code", sa.String(length=50), nullable=False),
        sa.Column("source_view", sa.String(length=80), nullable=True),
        sa.Column("source_rowid", sa.String(length=120), nullable=True),
        sa.Column("pick_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_int", sa.Integer(), nullable=True),
        sa.Column("order_num", sa.String(length=80), nullable=True),
        sa.Column("customer_num", sa.String(length=80), nullable=True),
        sa.Column("customer_desc", sa.String(length=255), nullable=True),
        sa.Column("line_num", sa.String(length=80), nullable=True),
        sa.Column("pick_zone", sa.String(length=20), nullable=True),
        sa.Column("location", sa.String(length=120), nullable=True),
        sa.Column("item_num", sa.String(length=80), nullable=True),
        sa.Column("item_desc", sa.String(length=255), nullable=True),
        sa.Column("qty_pre", sa.Float(), nullable=True),
        sa.Column("qty_suf", sa.Float(), nullable=True),
        sa.Column("pick_pall_num", sa.String(length=120), nullable=True),
        sa.Column("responsible", sa.String(length=120), nullable=True),
        sa.Column("company", sa.String(length=30), nullable=True),
        sa.Column("supplier", sa.String(length=255), nullable=True),
    )
    op.create_index("ix_public_dpak_pick_business_date", "public_dpak_pick_rows", ["business_code", "pick_date"])
    op.create_index("ix_public_dpak_pick_business_zone", "public_dpak_pick_rows", ["business_code", "pick_zone"])
    op.create_index("ix_public_dpak_pick_business_location", "public_dpak_pick_rows", ["business_code", "location"])
    op.create_index("ix_public_dpak_pick_business_supplier", "public_dpak_pick_rows", ["business_code", "supplier"])
    op.create_index("ix_public_dpak_pick_business_item", "public_dpak_pick_rows", ["business_code", "item_num"])
    op.create_index("ix_public_dpak_pick_business_order", "public_dpak_pick_rows", ["business_code", "order_num"])

    op.create_table(
        "public_dpak_order_article_facts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("business_code", sa.String(length=50), nullable=False),
        sa.Column("order_num", sa.String(length=80), nullable=False),
        sa.Column("item_num", sa.String(length=80), nullable=False),
        sa.Column("item_desc", sa.String(length=255), nullable=True),
        sa.Column("customer_num", sa.String(length=80), nullable=True),
        sa.Column("customer_desc", sa.String(length=255), nullable=True),
        sa.Column("pick_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_int", sa.Integer(), nullable=True),
        sa.Column("pick_zone", sa.String(length=20), nullable=True),
        sa.Column("company", sa.String(length=30), nullable=True),
        sa.Column("supplier", sa.String(length=255), nullable=True),
        sa.Column("responsible", sa.String(length=120), nullable=True),
        sa.Column("qty_pre", sa.Float(), nullable=False, server_default="0"),
        sa.Column("qty_suf", sa.Float(), nullable=False, server_default="0"),
        sa.Column("factor", sa.Float(), nullable=True),
        sa.Column("whole_dpak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("loose_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dpack_sold", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dpack_broken", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unnecessary_break", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("pick_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locations", JSON_TYPE, nullable=True),
        sa.Column("has_autostore", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_public_dpak_fact_business_date", "public_dpak_order_article_facts", ["business_code", "pick_date"])
    op.create_index("ix_public_dpak_fact_business_zone", "public_dpak_order_article_facts", ["business_code", "pick_zone"])
    op.create_index("ix_public_dpak_fact_business_supplier", "public_dpak_order_article_facts", ["business_code", "supplier"])
    op.create_index("ix_public_dpak_fact_business_item", "public_dpak_order_article_facts", ["business_code", "item_num"])
    op.create_index("ix_public_dpak_fact_business_order", "public_dpak_order_article_facts", ["business_code", "order_num"])

    op.create_table(
        "public_dpak_order_supplier_box_facts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("business_code", sa.String(length=50), nullable=False),
        sa.Column("order_num", sa.String(length=80), nullable=False),
        sa.Column("supplier", sa.String(length=255), nullable=False),
        sa.Column("pick_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_int", sa.Integer(), nullable=True),
        sa.Column("pick_zone", sa.String(length=20), nullable=True),
        sa.Column("pick_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("article_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("box_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("boxes", JSON_TYPE, nullable=True),
        sa.Column("can_spread", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("spread", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("has_autostore", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_public_dpak_box_business_date", "public_dpak_order_supplier_box_facts", ["business_code", "pick_date"])
    op.create_index("ix_public_dpak_box_business_supplier", "public_dpak_order_supplier_box_facts", ["business_code", "supplier"])
    op.create_index("ix_public_dpak_box_business_order", "public_dpak_order_supplier_box_facts", ["business_code", "order_num"])
    op.create_index("ix_public_dpak_box_business_zone", "public_dpak_order_supplier_box_facts", ["business_code", "pick_zone"])


def downgrade() -> None:
    op.drop_index("ix_public_dpak_box_business_zone", table_name="public_dpak_order_supplier_box_facts")
    op.drop_index("ix_public_dpak_box_business_order", table_name="public_dpak_order_supplier_box_facts")
    op.drop_index("ix_public_dpak_box_business_supplier", table_name="public_dpak_order_supplier_box_facts")
    op.drop_index("ix_public_dpak_box_business_date", table_name="public_dpak_order_supplier_box_facts")
    op.drop_table("public_dpak_order_supplier_box_facts")

    op.drop_index("ix_public_dpak_fact_business_order", table_name="public_dpak_order_article_facts")
    op.drop_index("ix_public_dpak_fact_business_item", table_name="public_dpak_order_article_facts")
    op.drop_index("ix_public_dpak_fact_business_supplier", table_name="public_dpak_order_article_facts")
    op.drop_index("ix_public_dpak_fact_business_zone", table_name="public_dpak_order_article_facts")
    op.drop_index("ix_public_dpak_fact_business_date", table_name="public_dpak_order_article_facts")
    op.drop_table("public_dpak_order_article_facts")

    op.drop_index("ix_public_dpak_pick_business_order", table_name="public_dpak_pick_rows")
    op.drop_index("ix_public_dpak_pick_business_item", table_name="public_dpak_pick_rows")
    op.drop_index("ix_public_dpak_pick_business_supplier", table_name="public_dpak_pick_rows")
    op.drop_index("ix_public_dpak_pick_business_location", table_name="public_dpak_pick_rows")
    op.drop_index("ix_public_dpak_pick_business_zone", table_name="public_dpak_pick_rows")
    op.drop_index("ix_public_dpak_pick_business_date", table_name="public_dpak_pick_rows")
    op.drop_table("public_dpak_pick_rows")

    op.drop_index("ix_public_dpak_sync_business_view", table_name="public_dpak_sync_chunks")
    op.drop_index("ix_public_dpak_sync_business_status", table_name="public_dpak_sync_chunks")
    op.drop_table("public_dpak_sync_chunks")

    op.drop_table("public_dpak_datasets")

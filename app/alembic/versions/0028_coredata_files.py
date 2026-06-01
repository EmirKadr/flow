"""store coredata files in postgres

Revision ID: 0028_coredata_files
Revises: 0027_meta_shipment_number
Create Date: 2026-06-01
"""
from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0028_coredata_files"
down_revision: Union[str, None] = "0027_meta_shipment_number"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.create_table(
        "coredata_files",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("business_code", sa.String(length=50), nullable=False),
        sa.Column("file_type", sa.String(length=80), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False, server_default="text/csv"),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False, server_default="upload"),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.UniqueConstraint("business_code", "file_type", name="uq_coredata_files_business_file_type"),
    )
    op.create_index("ix_coredata_files_business_code", "coredata_files", ["business_code"])
    op.create_index("ix_coredata_files_file_type", "coredata_files", ["file_type"])
    op.create_index("ix_coredata_files_content_hash", "coredata_files", ["content_hash"])


def downgrade() -> None:
    op.drop_index("ix_coredata_files_content_hash", table_name="coredata_files")
    op.drop_index("ix_coredata_files_file_type", table_name="coredata_files")
    op.drop_index("ix_coredata_files_business_code", table_name="coredata_files")
    op.drop_table("coredata_files")

"""bug reports

Revision ID: 0047_bug_reports
Revises: 0046_leader_leases
Create Date: 2026-07-07
"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0047_bug_reports"
down_revision: Union[str, None] = "0046_leader_leases"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.create_table(
        "bug_reports",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("business_id", sa.Integer(), sa.ForeignKey("businesses.id"), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("view_id", sa.String(length=80), nullable=True),
        sa.Column("page_path", sa.String(length=300), nullable=True),
        sa.Column("note", sa.String(length=2000), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="new"),
        sa.Column("events_json", sa.Text(), nullable=False),
        sa.Column("events_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("handled_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_bug_reports_created_at", "bug_reports", ["created_at"])
    op.create_index("ix_bug_reports_business_created", "bug_reports", ["business_id", "created_at"])
    op.create_index("ix_bug_reports_status", "bug_reports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_bug_reports_status", table_name="bug_reports")
    op.drop_index("ix_bug_reports_business_created", table_name="bug_reports")
    op.drop_index("ix_bug_reports_created_at", table_name="bug_reports")
    op.drop_table("bug_reports")

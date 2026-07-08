"""audit_log filter and sort indexes

Revision ID: 0048_audit_log_indexes
Revises: 0047_bug_reports
Create Date: 2026-07-07
"""

from __future__ import annotations

from typing import Union

from alembic import op


revision: str = "0048_audit_log_indexes"
down_revision: Union[str, None] = "0047_bug_reports"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])
    op.create_index("ix_audit_log_business_created", "audit_log", ["business_id", "created_at"])
    op.create_index("ix_audit_log_user_created", "audit_log", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_user_created", table_name="audit_log")
    op.drop_index("ix_audit_log_business_created", table_name="audit_log")
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")

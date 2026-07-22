"""schedule history freeze

Revision ID: 0049_schedule_history_freeze
Revises: 0048_audit_log_indexes
Create Date: 2026-07-21
"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0049_schedule_history_freeze"
down_revision: Union[str, None] = "0048_audit_log_indexes"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.add_column(
        "schedule_cells",
        sa.Column(
            "is_template_fill",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_table(
        "schedule_freeze_state",
        # autoincrement=False: singelrad med fast id=1. Utan det blir kolumnen
        # IDENTITY pa MSSQL och INSERT:en nedan avvisas ("Cannot insert
        # explicit value for identity column").
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("frozen_until", sa.Date(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Singelraden skapas direkt sa materialiseringen alltid har en rad att
    # radlasa (UPDLOCK) - det ar den som serialiserar samtidiga korningar
    # mellan bakgrundsjobbet och request-vagarna.
    op.execute("INSERT INTO schedule_freeze_state (id, frozen_until) VALUES (1, NULL)")


def downgrade() -> None:
    op.drop_table("schedule_freeze_state")
    op.drop_column("schedule_cells", "is_template_fill")

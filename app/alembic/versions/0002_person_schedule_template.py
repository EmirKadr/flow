"""person schedule templates

Revision ID: 0002_person_schedule_template
Revises: 0001_initial
Create Date: 2026-05-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_person_schedule_template"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # MSSQL saknar boolean-literalerna true/false i uttryck; PG kraver dem.
    if op.get_bind().dialect.name == "mssql":
        true_lit, false_lit = "1", "0"
    else:
        true_lit, false_lit = "true", "false"
    op.create_table(
        "person_schedule_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("persons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("start_hour", sa.SmallInteger()),
        sa.Column("end_hour", sa.SmallInteger()),
        sa.Column("is_off", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.UniqueConstraint("person_id", "weekday", name="uq_person_schedule_weekday"),
        sa.CheckConstraint(
            f"(is_off = {true_lit} AND start_hour IS NULL AND end_hour IS NULL) OR "
            f"(is_off = {false_lit} AND start_hour IS NOT NULL AND end_hour IS NOT NULL "
            "AND start_hour >= 6 AND end_hour <= 24 AND start_hour < end_hour)",
            name="ck_template_hours",
        ),
    )
    op.create_index("ix_pst_person", "person_schedule_templates", ["person_id"])


def downgrade() -> None:
    op.drop_index("ix_pst_person", table_name="person_schedule_templates")
    op.drop_table("person_schedule_templates")

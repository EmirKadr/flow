"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# JSONB på PostgreSQL, vanlig JSON på övriga dialekter (Azure SQL -> NVARCHAR(max),
# SQLite -> TEXT). Matchar JsonField i backend/models.py.
JSON_TYPE = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(50), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100)),
        sa.Column("role", sa.String(20), nullable=False, server_default="leader"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "areas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "persons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("home_area_id", sa.Integer(), sa.ForeignKey("areas.id")),
        sa.Column("competencies", JSON_TYPE, nullable=False, server_default="[]"),
        sa.Column("comment", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "activities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("label", sa.String(60), nullable=False),
        sa.Column("area_id", sa.Integer(), sa.ForeignKey("areas.id")),
        sa.Column("color", sa.String(20), nullable=False, server_default="#ffffff"),
        sa.Column("category", sa.String(20), nullable=False, server_default="work"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("required_competency", sa.String(40)),
    )

    op.create_table(
        "schedule_cells",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("year", sa.SmallInteger(), nullable=False),
        sa.Column("week", sa.SmallInteger(), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("hour", sa.SmallInteger(), nullable=False),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("persons.id"), nullable=False),
        sa.Column("activity_id", sa.Integer(), sa.ForeignKey("activities.id")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.UniqueConstraint("year", "week", "weekday", "hour", "person_id", name="uq_schedule_cell"),
    )
    op.create_index(
        "ix_schedule_cells_ywd", "schedule_cells", ["year", "week", "weekday"]
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("old_value", JSON_TYPE),
        sa.Column("new_value", JSON_TYPE),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_schedule_cells_ywd", table_name="schedule_cells")
    op.drop_table("schedule_cells")
    op.drop_table("activities")
    op.drop_table("persons")
    op.drop_table("areas")
    op.drop_table("users")

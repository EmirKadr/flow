"""add business companies and person rfid

Revision ID: 0041_company_rfid
Revises: 0040_wait_metric_indexes
Create Date: 2026-06-14
"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0041_company_rfid"
down_revision: Union[str, None] = "0040_wait_metric_indexes"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


company_codes_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column("businesses", sa.Column("company_codes", company_codes_type, nullable=True))
    op.add_column("persons", sa.Column("rfid_code", sa.String(length=120), nullable=True))
    op.get_bind().execute(sa.text("UPDATE businesses SET company_codes = '[]' WHERE company_codes IS NULL"))
    op.alter_column("businesses", "company_codes", existing_type=company_codes_type, nullable=False)
    op.create_unique_constraint("uq_persons_business_rfid_code", "persons", ["business_id", "rfid_code"])


def downgrade() -> None:
    op.drop_constraint("uq_persons_business_rfid_code", "persons", type_="unique")
    op.drop_column("persons", "rfid_code")
    op.drop_column("businesses", "company_codes")

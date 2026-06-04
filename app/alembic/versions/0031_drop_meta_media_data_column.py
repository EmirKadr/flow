"""drop meta_media_uploads.data (bytes now live in MediaStore)

Revision ID: 0031_drop_meta_media_data_column
Revises: 0030_meta_media_storage_key
Create Date: 2026-06-03
"""
from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0031_drop_meta_media_data_column"
down_revision: Union[str, None] = "0030_meta_media_storage_key"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    pending = connection.execute(
        sa.text(
            "SELECT count(*) FROM meta_media_uploads "
            "WHERE storage_key IS NULL OR data IS NOT NULL"
        )
    ).scalar()
    if pending:
        raise RuntimeError(
            "Kan inte droppa meta_media_uploads.data innan alla Meta-media "
            "har storage_key och data ar NULL. Kor forst "
            "`python -m backend.scripts.migrate_meta_blobs_to_store` i lag trafik."
        )
    op.drop_column("meta_media_uploads", "data")


def downgrade() -> None:
    op.add_column(
        "meta_media_uploads",
        sa.Column("data", sa.LargeBinary(), nullable=True),
    )

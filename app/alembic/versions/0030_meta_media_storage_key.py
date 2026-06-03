"""meta media storage key (stream media to MediaStore instead of bytea)

Revision ID: 0030_meta_media_storage_key
Revises: 0029_user_person_link
Create Date: 2026-06-03
"""
from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0030_meta_media_storage_key"
down_revision: Union[str, None] = "0029_user_person_link"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.add_column("meta_media_uploads", sa.Column("storage_backend", sa.String(length=20), nullable=True))
    op.add_column("meta_media_uploads", sa.Column("storage_key", sa.String(length=255), nullable=True))
    # Bytena flyttas till MediaStore; gör kolumnen nullable. Den droppas i en
    # senare migration när alla rader är migrerade.
    op.alter_column("meta_media_uploads", "data", existing_type=sa.LargeBinary(), nullable=True)


def downgrade() -> None:
    op.alter_column("meta_media_uploads", "data", existing_type=sa.LargeBinary(), nullable=False)
    op.drop_column("meta_media_uploads", "storage_key")
    op.drop_column("meta_media_uploads", "storage_backend")

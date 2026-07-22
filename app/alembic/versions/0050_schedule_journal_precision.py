"""schedule journal precision: elapsed-hour cutoff and frozen area attribution

Revision ID: 0050_schedule_journal_precision
Revises: 0049_schedule_history_freeze
Create Date: 2026-07-22

Schemat ar bade plan och journal: framtiden ar plan, forfluten tid journal och
dagens datum en blandning. 0049 fryste hela dygn; den har migrationen ger
tva saker till:

- `schedule_freeze_state.elapsed_date`/`elapsed_hour`: hur langt in i dagens
  datum journalen gar. Timmar fore den gransen far inte langre ritas om av
  veckomallen.
- `schedule_cells.activity_area_id`: vilket omrade aktiviteten tillhorde nar
  arbetet registrerades, sa historisk bemanning per omrade star still aven om
  aktiviteten senare flyttas till ett annat omrade.
"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "0050_schedule_journal_precision"
down_revision: Union[str, None] = "0049_schedule_history_freeze"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


def upgrade() -> None:
    op.add_column("schedule_freeze_state", sa.Column("elapsed_date", sa.Date(), nullable=True))
    op.add_column("schedule_freeze_state", sa.Column("elapsed_hour", sa.Integer(), nullable=True))
    op.add_column("schedule_cells", sa.Column("activity_area_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_schedule_cells_activity_area_id",
        "schedule_cells",
        "areas",
        ["activity_area_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_schedule_cells_activity_area_id", "schedule_cells", type_="foreignkey")
    op.drop_column("schedule_cells", "activity_area_id")
    op.drop_column("schedule_freeze_state", "elapsed_hour")
    op.drop_column("schedule_freeze_state", "elapsed_date")

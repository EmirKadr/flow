from __future__ import annotations

from collections.abc import Iterable

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .models import ScheduleCell, User
from .settings_service import get_lock_foreign_schedule_cells
from .user_access import can_admin, is_super_user


LOCKED_CELL_DETAIL = "Cellen är låst eftersom en annan användare har fyllt i den."


def user_can_bypass_schedule_cell_lock(user: User) -> bool:
    return can_admin(user) or is_super_user(user)


def foreign_schedule_cell_lock_applies(db: Session, user: User) -> bool:
    return get_lock_foreign_schedule_cells(db) and not user_can_bypass_schedule_cell_lock(user)


def is_foreign_schedule_cell(cell: ScheduleCell, user: User) -> bool:
    return cell.updated_by is not None and cell.updated_by != user.id


def assert_can_modify_schedule_cells(
    cells: Iterable[ScheduleCell],
    user: User,
    lock_enabled: bool,
) -> None:
    if not lock_enabled:
        return
    if any(is_foreign_schedule_cell(cell, user) for cell in cells):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=LOCKED_CELL_DETAIL)

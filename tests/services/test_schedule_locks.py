import pytest
from fastapi import HTTPException

from app.backend.models import ScheduleCell, User
from app.backend.schedule_locks import (
    assert_can_modify_schedule_cells,
    is_foreign_schedule_cell,
    user_can_bypass_schedule_cell_lock,
)
from app.backend.settings_service import _parse_bool


def make_user(user_id: int, role: str = "leader", roles: list[str] | None = None) -> User:
    return User(id=user_id, username=f"user{user_id}", role=role, roles=roles, is_active=True)


def make_cell(updated_by: int | None) -> ScheduleCell:
    return ScheduleCell(
        year=2026,
        week=20,
        weekday=3,
        hour=8,
        minute_start=0,
        minute_end=60,
        person_id=1,
        activity_id=1,
        empty_override=False,
        version=1,
        updated_by=updated_by,
    )


def test_foreign_schedule_cell_detection():
    user = make_user(1)

    assert is_foreign_schedule_cell(make_cell(2), user) is True
    assert is_foreign_schedule_cell(make_cell(1), user) is False
    assert is_foreign_schedule_cell(make_cell(None), user) is False


def test_lock_blocks_cells_filled_by_other_users():
    user = make_user(1)

    with pytest.raises(HTTPException) as exc_info:
        assert_can_modify_schedule_cells([make_cell(2)], user, lock_enabled=True)

    assert exc_info.value.status_code == 403


def test_lock_allows_own_cells_and_implicit_schedule_cells():
    user = make_user(1)

    assert_can_modify_schedule_cells([make_cell(1), make_cell(None)], user, lock_enabled=True)


def test_lock_can_be_disabled():
    user = make_user(1)

    assert_can_modify_schedule_cells([make_cell(2)], user, lock_enabled=False)


def test_admins_can_bypass_schedule_cell_lock():
    assert user_can_bypass_schedule_cell_lock(make_user(1, role="admin")) is True
    assert user_can_bypass_schedule_cell_lock(make_user(3, role="viewer", roles=["viewer", "admin"])) is True
    assert user_can_bypass_schedule_cell_lock(make_user(2, role="leader")) is False


def test_bool_setting_parser_accepts_swedish_truthy_value():
    assert _parse_bool("ja") is True
    assert _parse_bool("false") is False
    assert _parse_bool(None, default=True) is True

import pytest
from fastapi import HTTPException

from app.backend.deps import require_allocation_tools_user, require_planning_editor
from app.backend.models import User


def make_user(role: str, roles: list[str] | None = None) -> User:
    return User(id=1, username=f"{role}-user", role=role, roles=roles, is_active=True)


def test_viewer_cannot_edit_planning():
    with pytest.raises(HTTPException) as exc_info:
        require_planning_editor(make_user("viewer"))

    assert exc_info.value.status_code == 403


def test_leader_and_admin_can_edit_planning():
    assert require_planning_editor(make_user("leader")).role == "leader"
    assert require_planning_editor(make_user("admin")).role == "admin"


def test_user_with_viewer_and_leader_can_edit_planning():
    assert require_planning_editor(make_user("viewer", roles=["viewer", "leader"])).role == "viewer"


def test_lagerkontorist_can_open_allocation_tools_but_not_edit_planning():
    user = make_user("warehouse_clerk", roles=["warehouse_clerk"])

    assert require_allocation_tools_user(user).role == "warehouse_clerk"
    with pytest.raises(HTTPException) as exc_info:
        require_planning_editor(user)

    assert exc_info.value.status_code == 403


def test_admin_without_lagerkontorist_cannot_open_allocation_tools():
    with pytest.raises(HTTPException) as exc_info:
        require_allocation_tools_user(make_user("admin"))

    assert exc_info.value.status_code == 403


def test_artikelplacerare_has_no_extra_permissions_yet():
    user = make_user("article_placer", roles=["article_placer"])

    with pytest.raises(HTTPException):
        require_planning_editor(user)
    with pytest.raises(HTTPException):
        require_allocation_tools_user(user)

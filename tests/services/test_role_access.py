import pytest
from fastapi import HTTPException

from app.backend.deps import (
    require_allocation_process_user,
    require_allocation_tools_user,
    require_planning_editor,
    require_planning_viewer,
)
from app.backend.models import User
from app.backend.user_access import can_access_view, is_super_user, role_view_access_level


def make_user(role: str, roles: list[str] | None = None) -> User:
    return User(id=1, username=f"{role}-user", role=role, roles=roles, is_active=True)


def test_viewer_cannot_edit_planning():
    with pytest.raises(HTTPException) as exc_info:
        require_planning_editor(make_user("viewer"))

    assert exc_info.value.status_code == 403


def test_viewer_can_open_bemanning_view():
    assert require_planning_viewer(make_user("viewer")).role == "viewer"


def test_leader_and_admin_can_edit_planning():
    assert require_planning_editor(make_user("leader")).role == "leader"
    assert require_planning_editor(make_user("admin")).role == "admin"


def test_bemanningsansvarig_can_edit_planning():
    assert require_planning_editor(make_user("staffing_manager")).role == "staffing_manager"


def test_user_with_viewer_and_leader_can_edit_planning():
    assert require_planning_editor(make_user("viewer", roles=["viewer", "leader"])).role == "viewer"


def test_lagerkontorist_can_open_allocation_tools_but_not_edit_planning():
    user = make_user("warehouse_clerk", roles=["warehouse_clerk"])

    assert require_allocation_tools_user(user).role == "warehouse_clerk"
    with pytest.raises(HTTPException) as exc_info:
        require_planning_editor(user)

    assert exc_info.value.status_code == 403
    with pytest.raises(HTTPException):
        require_planning_viewer(user)
    with pytest.raises(HTTPException):
        require_allocation_process_user(user)


def test_admin_without_lagerkontorist_cannot_open_allocation_tools():
    with pytest.raises(HTTPException) as exc_info:
        require_allocation_tools_user(make_user("admin"))

    assert exc_info.value.status_code == 403


def test_artikelplacerare_can_open_same_allocation_tools_as_lagerkontorist():
    user = make_user("article_placer", roles=["article_placer"])

    assert require_allocation_tools_user(user).role == "article_placer"
    with pytest.raises(HTTPException):
        require_planning_editor(user)
    with pytest.raises(HTTPException):
        require_planning_viewer(user)
    with pytest.raises(HTTPException):
        require_allocation_process_user(user)


def test_super_user_can_open_allocation_process():
    user = make_user("super_user", roles=["super_user"])

    assert require_allocation_tools_user(user).role == "super_user"
    assert require_allocation_process_user(user).role == "super_user"
    assert role_view_access_level(user, {}, "users") == "edit"


def test_configured_username_is_super_user_even_without_admin_role(monkeypatch):
    monkeypatch.setattr("app.backend.user_access.settings.SUPER_USER_USERNAMES", "mikhal")
    user = User(id=2, username="Mikhal", role="viewer", roles=["viewer"], is_active=True)

    assert is_super_user(user)
    assert require_planning_editor(user).username == "Mikhal"
    assert require_allocation_process_user(user).username == "Mikhal"
    assert role_view_access_level(user, {}, "users") == "edit"


def test_role_view_access_can_grant_and_revoke_feature_permissions():
    leader = make_user("leader")
    staffing = make_user("staffing_manager")
    viewer = make_user("viewer")

    assert can_access_view(staffing, {}, "stallen", "edit")
    assert can_access_view(staffing, {"staffing_manager": {"stallen": "view"}}, "stallen", "view")
    assert not can_access_view(staffing, {"staffing_manager": {"stallen": "view"}}, "stallen", "edit")
    assert can_access_view(leader, {"leader": {"roleAccess": "edit"}}, "roleAccess", "edit")
    assert not can_access_view(viewer, {}, "personImport", "edit")
    assert role_view_access_level(viewer, {"viewer": {"users": "view"}}, "users") == "view"

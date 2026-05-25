from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.models import AppSetting, AuditLog, User
from app.backend.routers import settings as settings_router
from app.backend.schemas import AppSettingsUpdate, RoleViewAccessUpdate, SidebarLayoutItem, SidebarLayoutUpdate
from app.backend.settings_service import (
    ROLE_VIEW_ACCESS_KEY,
    SIDEBAR_LAYOUT_KEY,
    get_role_view_access,
    get_sidebar_layout,
    set_role_view_access,
    set_sidebar_layout,
)


def make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    User.__table__.create(engine)
    AppSetting.__table__.create(engine)
    AuditLog.__table__.create(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    return engine, session


def drop_session_tables(engine):
    AuditLog.__table__.drop(engine)
    AppSetting.__table__.drop(engine)
    User.__table__.drop(engine)


def test_sidebar_layout_setting_roundtrips():
    engine, session = make_session()
    try:
        assert get_sidebar_layout(session) == []

        set_sidebar_layout(
            session,
            [
                {"id": "schedule", "heading": "Planering", "parent_id": None},
                {"id": "overview", "heading": "", "parent_id": "schedule"},
            ],
            user_id=12,
        )
        session.commit()

        row = session.get(AppSetting, {"business_id": 1, "key": SIDEBAR_LAYOUT_KEY})
        assert row is not None
        assert row.updated_by == 12
        assert get_sidebar_layout(session)[1]["parent_id"] == "schedule"
    finally:
        session.close()
        drop_session_tables(engine)
        engine.dispose()


def test_sidebar_router_cleans_layout_before_saving():
    engine, session = make_session()
    try:
        admin = User(id=7, username="root", role="admin", roles=["super_user"], is_active=True)
        payload = SidebarLayoutUpdate(items=[
            SidebarLayoutItem(id="schedule", heading="  Planering  "),
            SidebarLayoutItem(id="overview", parent_id="schedule"),
            SidebarLayoutItem(id="overview", heading="Dubblett"),
            SidebarLayoutItem(id="persons", parent_id="activities"),
            SidebarLayoutItem(id="stallen", parent_id="persons"),
            SidebarLayoutItem(id="ghost", parent_id="schedule"),
        ])

        result = settings_router.update_sidebar_settings(payload, session, admin)

        assert [item.id for item in result.items] == ["schedule", "overview", "persons", "activities", "ghost"]
        assert result.items[0].heading == "Planering"
        assert result.items[1].parent_id == "schedule"
        assert result.items[2].parent_id is None
        assert result.items[3].parent_id == "persons"
        entry = session.query(AuditLog).filter_by(entity_type="app_setting", action="update_sidebar_layout").one()
        assert entry.user_id == admin.id
        assert entry.old_value == {"key": SIDEBAR_LAYOUT_KEY, "value": {"items": []}}
        assert entry.new_value["key"] == SIDEBAR_LAYOUT_KEY
        assert entry.new_value["value"]["items"][0]["id"] == "schedule"
    finally:
        session.close()
        drop_session_tables(engine)
        engine.dispose()


def test_role_view_access_setting_roundtrips():
    engine, session = make_session()
    try:
        assert get_role_view_access(session) == {}

        set_role_view_access(
            session,
            {"viewer": {"schedule": "view", "users": "none"}},
            user_id=9,
        )
        session.commit()

        row = session.get(AppSetting, {"business_id": 1, "key": ROLE_VIEW_ACCESS_KEY})
        assert row is not None
        assert row.updated_by == 9
        assert get_role_view_access(session)["viewer"]["schedule"] == "view"
    finally:
        session.close()
        drop_session_tables(engine)
        engine.dispose()


def test_role_view_access_is_global_across_businesses():
    engine, session = make_session()
    try:
        set_role_view_access(
            session,
            {"warehouse_clerk": {"allocationProcess": "edit"}},
            user_id=9,
            business_id=2,
        )
        session.commit()

        row = session.get(AppSetting, {"business_id": 1, "key": ROLE_VIEW_ACCESS_KEY})
        assert row is not None
        assert get_role_view_access(session, business_id=1)["warehouse_clerk"]["allocationProcess"] == "edit"
        assert get_role_view_access(session, business_id=2)["warehouse_clerk"]["allocationProcess"] == "edit"
    finally:
        session.close()
        drop_session_tables(engine)
        engine.dispose()


def test_role_view_access_router_cleans_unknown_roles_views_and_levels():
    engine, session = make_session()
    try:
        admin = User(id=7, username="root", role="admin", roles=["super_user"], is_active=True)
        payload = RoleViewAccessUpdate(access={
            "viewer": {"schedule": "view", "users": "edit", "ghost": "edit"},
            "leader": {"overview": "edit", "stallen": "delete", "personImport": "edit", "activityImport": "view"},
            "admin": {"roleAccess": "edit", "sidebarLayout": "edit", "appSettings": "edit"},
            "demo": {"users": "view", "businesses": "none"},
            "super_user": {"users": "none"},
            "unknown": {"schedule": "edit"},
        })

        result = settings_router.update_role_access_settings(payload, session, admin)

        assert result.access == {
            "viewer": {"schedule": "view", "users": "edit"},
            "leader": {"overview": "edit", "personImport": "edit", "activityImport": "view"},
            "admin": {"roleAccess": "edit", "sidebarLayout": "edit", "appSettings": "edit"},
            "demo": {"users": "view", "businesses": "none"},
        }
        entry = session.query(AuditLog).filter_by(entity_type="app_setting", action="update_role_access").one()
        assert entry.user_id == admin.id
        assert entry.business_id is None
        assert entry.old_value == {"key": ROLE_VIEW_ACCESS_KEY, "value": {"access": {}}}
        assert entry.new_value["value"]["access"]["viewer"]["users"] == "edit"
    finally:
        session.close()
        drop_session_tables(engine)
        engine.dispose()


def test_app_settings_update_writes_audit_log():
    engine, session = make_session()
    try:
        admin = User(id=7, username="root", role="admin", roles=["super_user"], is_active=True)

        result = settings_router.update_app_settings(
            AppSettingsUpdate(lock_foreign_schedule_cells=True),
            session,
            admin,
        )

        assert result.lock_foreign_schedule_cells is True
        entry = session.query(AuditLog).filter_by(entity_type="app_setting", action="update_lock").one()
        assert entry.user_id == admin.id
        assert entry.old_value == {
            "key": "lock_foreign_schedule_cells",
            "value": {"lock_foreign_schedule_cells": False},
        }
        assert entry.new_value == {
            "key": "lock_foreign_schedule_cells",
            "value": {"lock_foreign_schedule_cells": True},
        }
    finally:
        session.close()
        drop_session_tables(engine)
        engine.dispose()

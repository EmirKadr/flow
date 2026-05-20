from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.models import AppSetting, User
from app.backend.routers import settings as settings_router
from app.backend.schemas import RoleViewAccessUpdate, SidebarLayoutItem, SidebarLayoutUpdate
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
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    return engine, session


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

        row = session.get(AppSetting, SIDEBAR_LAYOUT_KEY)
        assert row is not None
        assert row.updated_by == 12
        assert get_sidebar_layout(session)[1]["parent_id"] == "schedule"
    finally:
        session.close()
        AppSetting.__table__.drop(engine)
        User.__table__.drop(engine)
        engine.dispose()


def test_sidebar_router_cleans_layout_before_saving():
    engine, session = make_session()
    try:
        admin = User(id=7, username="root", role="admin", roles=["super_user"], is_active=True)
        payload = SidebarLayoutUpdate(items=[
            SidebarLayoutItem(id="schedule", heading="  Planering  "),
            SidebarLayoutItem(id="overview", parent_id="schedule"),
            SidebarLayoutItem(id="overview", heading="Dubblett"),
            SidebarLayoutItem(id="persons", parent_id="stallen"),
            SidebarLayoutItem(id="stallen", parent_id="persons"),
            SidebarLayoutItem(id="ghost", parent_id="schedule"),
        ])

        result = settings_router.update_sidebar_settings(payload, session, admin)

        assert [item.id for item in result.items] == ["schedule", "overview", "persons", "stallen", "ghost"]
        assert result.items[0].heading == "Planering"
        assert result.items[1].parent_id == "schedule"
        assert result.items[2].parent_id is None
        assert result.items[3].parent_id == "persons"
    finally:
        session.close()
        AppSetting.__table__.drop(engine)
        User.__table__.drop(engine)
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

        row = session.get(AppSetting, ROLE_VIEW_ACCESS_KEY)
        assert row is not None
        assert row.updated_by == 9
        assert get_role_view_access(session)["viewer"]["schedule"] == "view"
    finally:
        session.close()
        AppSetting.__table__.drop(engine)
        User.__table__.drop(engine)
        engine.dispose()


def test_role_view_access_router_cleans_unknown_roles_views_and_levels():
    engine, session = make_session()
    try:
        admin = User(id=7, username="root", role="admin", roles=["super_user"], is_active=True)
        payload = RoleViewAccessUpdate(access={
            "viewer": {"schedule": "view", "users": "edit", "ghost": "edit"},
            "leader": {"overview": "edit", "stallen": "delete", "personImport": "edit"},
            "admin": {"roleAccess": "edit", "sidebarLayout": "edit", "appSettings": "edit"},
            "unknown": {"schedule": "edit"},
        })

        result = settings_router.update_role_access_settings(payload, session, admin)

        assert result.access == {
            "viewer": {"schedule": "view", "users": "edit"},
            "leader": {"overview": "edit", "personImport": "edit"},
            "admin": {"roleAccess": "edit", "sidebarLayout": "edit", "appSettings": "edit"},
        }
    finally:
        session.close()
        AppSetting.__table__.drop(engine)
        User.__table__.drop(engine)
        engine.dispose()

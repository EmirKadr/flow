from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.models import AppSetting, User
from app.backend.routers import settings as settings_router
from app.backend.schemas import SidebarLayoutItem, SidebarLayoutUpdate
from app.backend.settings_service import SIDEBAR_LAYOUT_KEY, get_sidebar_layout, set_sidebar_layout


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

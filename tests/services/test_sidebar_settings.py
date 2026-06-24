import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backend.models import Activity, AppSetting, Area, AuditLog, Business, User
from app.backend.routers import settings as settings_router
from app.backend.schemas import (
    AppSettingsUpdate,
    ProductivityFinanceCalculationTestRequest,
    RoleViewAccessUpdate,
    SidebarLayoutItem,
    SidebarLayoutUpdate,
    StaffingSettingsUpdate,
    ProductivityFinanceSettingsUpdate,
)
from app.backend.settings_service import (
    PRODUCTIVITY_FINANCE_KEY,
    ROLE_VIEW_ACCESS_KEY,
    SIDEBAR_LAYOUT_KEY,
    STAFFING_ACTIVITY_CAPACITY_ACTIVITY_IDS_KEY,
    STAFFING_HISTORY_HOURS_KEY,
    clean_productivity_finance_invoice_rows,
    get_productivity_finance_settings,
    get_staffing_activity_capacity_activity_ids,
    get_staffing_history_hours,
    get_role_view_access,
    get_sidebar_layout,
    productivity_finance_invoice_rows_for_company,
    set_productivity_finance_settings,
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


def make_business_settings_session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Business.__table__.create(engine)
    Area.__table__.create(engine)
    Activity.__table__.create(engine)
    User.__table__.create(engine)
    AppSetting.__table__.create(engine)
    AuditLog.__table__.create(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    return engine, session


def drop_business_settings_tables(engine):
    AuditLog.__table__.drop(engine)
    AppSetting.__table__.drop(engine)
    User.__table__.drop(engine)
    Activity.__table__.drop(engine)
    Area.__table__.drop(engine)
    Business.__table__.drop(engine)


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


def test_staffing_history_hours_defaults_to_40_and_updates_with_audit_log():
    engine, session = make_session()
    try:
        admin = User(id=7, username="root", role="admin", roles=["super_user"], is_active=True)

        assert get_staffing_history_hours(session) == 40.0
        assert get_staffing_activity_capacity_activity_ids(session) is None

        result = settings_router.update_staffing_settings(
            StaffingSettingsUpdate(history_hours=32, activity_capacity_activity_ids=[2, 1, 2]),
            session,
            admin,
        )

        assert result.history_hours == 32.0
        assert result.min_history_hours == 1.0
        assert result.max_history_hours == 240.0
        assert result.activity_capacity_activity_ids == [2, 1]
        row = session.get(AppSetting, {"business_id": 1, "key": STAFFING_HISTORY_HOURS_KEY})
        assert row is not None
        assert row.value == "32"
        activity_row = session.get(AppSetting, {"business_id": 1, "key": STAFFING_ACTIVITY_CAPACITY_ACTIVITY_IDS_KEY})
        assert activity_row is not None
        assert activity_row.value == "[2,1]"
        assert get_staffing_activity_capacity_activity_ids(session) == [2, 1]
        entry = session.query(AuditLog).filter_by(
            entity_type="app_setting",
            action="update_staffing_settings",
        ).one()
        assert entry.old_value == {
            "key": "staffing_settings",
            "value": {
                "history_hours": 40.0,
                "min_history_hours": 1.0,
                "max_history_hours": 240.0,
                "activity_capacity_activity_ids": None,
            },
        }
        assert entry.new_value == {
            "key": "staffing_settings",
            "value": {
                "history_hours": 32.0,
                "min_history_hours": 1.0,
                "max_history_hours": 240.0,
                "activity_capacity_activity_ids": [2, 1],
            },
        }

        reset = settings_router.update_staffing_settings(
            StaffingSettingsUpdate(history_hours=32, activity_capacity_activity_ids=None),
            session,
            admin,
        )

        assert reset.activity_capacity_activity_ids is None
        assert get_staffing_activity_capacity_activity_ids(session) is None
        assert session.get(AppSetting, {"business_id": 1, "key": STAFFING_ACTIVITY_CAPACITY_ACTIVITY_IDS_KEY}).value == "null"
    finally:
        session.close()
        drop_session_tables(engine)
        engine.dispose()


def test_productivity_finance_settings_normalize_and_roundtrip():
    engine, session = make_session()
    try:
        assert get_productivity_finance_settings(session) == {
            "hourly_cost": 0.0,
            "vas_hourly_revenue_by_company": {},
            "invoice_rows_by_company": {},
        }

        set_productivity_finance_settings(
            session,
            {
                "hourly_cost": "211.756",
                "vas_hourly_revenue_by_company": {
                    " gg ": "525.2",
                    "": 100,
                    "mg!": {"blue_collar": -5, "white_collar": "650.4"},
                    "EH": {"blue_collar": 10000001, "white_collar": "1200,25"},
                },
            },
            user_id=7,
        )
        session.commit()

        row = session.get(AppSetting, {"business_id": 1, "key": PRODUCTIVITY_FINANCE_KEY})
        assert row is not None
        assert row.updated_by == 7
        assert get_productivity_finance_settings(session) == {
            "hourly_cost": 211.76,
            "vas_hourly_revenue_by_company": {
                "GG": {
                    "blue_collar": {"normal": 525.2, "ot_50": 0.0, "ob1_40": 0.0, "ob2_70": 0.0, "ob3_100": 0.0},
                    "white_collar": {"normal": 525.2, "ot_50": 0.0, "ob1_40": 0.0, "ob2_70": 0.0, "ob3_100": 0.0},
                },
                "MG": {
                    "blue_collar": {"normal": 0.0, "ot_50": 0.0, "ob1_40": 0.0, "ob2_70": 0.0, "ob3_100": 0.0},
                    "white_collar": {"normal": 650.4, "ot_50": 0.0, "ob1_40": 0.0, "ob2_70": 0.0, "ob3_100": 0.0},
                },
                "EH": {
                    "blue_collar": {"normal": 10000000.0, "ot_50": 0.0, "ob1_40": 0.0, "ob2_70": 0.0, "ob3_100": 0.0},
                    "white_collar": {"normal": 1200.25, "ot_50": 0.0, "ob1_40": 0.0, "ob2_70": 0.0, "ob3_100": 0.0},
                },
            },
            "invoice_rows_by_company": {},
        }
    finally:
        session.close()
        drop_session_tables(engine)
        engine.dispose()


def test_productivity_finance_settings_use_business_company_codes_only():
    engine, session = make_business_settings_session()
    try:
        business = Business(id=1, code="STIGAMO", name="Stigamo", company_codes=["GG", "MG"])
        area_as = Area(id=10, business_id=1, code="AS", name="Autostore")
        area_gg = Area(id=11, business_id=1, code="GG", name="Granngården")
        activity_as = Activity(id=20, business_id=1, area_id=10, code="AS_VAS", label="AS VAS", work_type="vas")
        activity_gg = Activity(id=21, business_id=1, area_id=11, code="GG_VAS", label="GG VAS", work_type="vas")
        admin = User(id=7, username="root", role="super_user", roles=["super_user"], is_active=True)
        session.add_all([business, area_as, area_gg, activity_as, activity_gg, admin])
        session.commit()

        initial = settings_router._productivity_finance_settings_out(session, 1)

        assert initial.company_codes == ["GG", "MG"]
        assert "AS" not in initial.company_codes
        assert "STIGAMO" not in initial.company_codes
        initial_payload = initial.model_dump()
        assert initial_payload["invoice_rows_by_company"]["GG"][0]["id"] == "inbound_container_unloading"
        # Priser är hemliga och ligger inte i repot; defaulten är 0.0 (riktiga värden
        # overlay:as från en gitignore:ad lokal fil). Verifiera struktur/typ, inte värde.
        assert isinstance(initial_payload["invoice_rows_by_company"]["GG"][0]["price"], (int, float))
        assert initial_payload["invoice_rows_by_company"]["GG"][0]["price"] >= 0
        assert isinstance(initial_payload["vas_hourly_revenue_by_company"]["GG"]["blue_collar"]["normal"], (int, float))
        gg_rows = {row["id"]: row for row in initial_payload["invoice_rows_by_company"]["GG"]}
        assert gg_rows["inbound_labels"]["calculation_prompt"] == "antal poster i varumottagningslogg\nexkludera typ 45, 91 & 100"
        assert gg_rows["inbound_labels"]["calculation_plan"]["filters"][-1] == {"id": "company", "operator": "EQ", "value": "GG"}
        assert gg_rows["inbound_labels"]["calculation_sql"] == (
            "SELECT COUNT(*) AS st_antal FROM v_ask_receive_log WHERE type <> '45' AND type <> '91' "
            "AND type <> '100' AND company = 'GG';"
        )
        assert gg_rows["store_picked_orders"]["calculation_plan"]["calculation"] == {
            "metric": "count_distinct",
            "field": None,
            "distinct_by": ["order_num"],
            "group_by": [],
            "sort_by": None,
            "limit": None,
        }
        assert gg_rows["store_picked_orders"]["calculation_sql"] == (
            "SELECT COUNT(DISTINCT order_num) AS value FROM v_ask_pick_log_full WHERE order_num LIKE 'TO%' "
            "AND company = 'GG';"
        )
        assert gg_rows["store_picked_rows"]["calculation_prompt"] == (
            "antal poster i plocklogg full\ninkludera endast ordernummer som börjar på TO\n"
            "exkludera poster med zon = H\nexkludera rader med <1 i kolumn plockat"
        )
        assert gg_rows["store_picked_rows"]["calculation_plan"]["filters"] == [
            {"id": "order_num", "operator": "StartsWith", "value": "TO"},
            {"id": "pick_zone", "operator": "NE", "value": "H"},
            {"id": "qty_suf", "operator": "GTE", "value": 1},
            {"id": "company", "operator": "EQ", "value": "GG"},
        ]
        assert gg_rows["store_picked_rows"]["calculation_sql"] == (
            "SELECT COUNT(*) AS value FROM v_ask_pick_log_full WHERE order_num LIKE 'TO%' "
            "AND pick_zone <> 'H' AND qty_suf >= 1 AND company = 'GG';"
        )
        assert gg_rows["store_full_pallets"]["calculation_prompt"] == (
            "antal poster i plocklogg full med zon = H\n"
            "exkludera rader med <1 i kolumn plockat\n"
            "inkludera endast ordernummer som börjar på TO"
        )
        assert gg_rows["store_full_pallets"]["calculation_plan"]["filters"] == [
            {"id": "pick_zone", "operator": "EQ", "value": "H"},
            {"id": "qty_suf", "operator": "GTE", "value": 1},
            {"id": "order_num", "operator": "StartsWith", "value": "TO"},
            {"id": "company", "operator": "EQ", "value": "GG"},
        ]
        assert gg_rows["store_full_pallets"]["calculation_sql"] == (
            "SELECT COUNT(*) AS value FROM v_ask_pick_log_full WHERE pick_zone = 'H' AND qty_suf >= '1' "
            "AND order_num LIKE 'TO%' AND company = 'GG';"
        )
        assert gg_rows["store_loaded_pallets"]["calculation_prompt"] == (
            "antal poster i dispatchpallar utan värde i kolumnen pappapallsnr"
        )
        assert gg_rows["store_loaded_pallets"]["calculation_plan"]["filters"] == [
            {"id": "parent_pick_pall_num", "operator": "NE", "value": ""},
            {"id": "company", "operator": "EQ", "value": "GG"},
        ]
        assert gg_rows["store_loaded_pallets"]["calculation_sql"] == (
            "SELECT COUNT(*) AS value FROM v_ask_dispatch_pallet WHERE parent_pick_pall_num <> '' "
            "AND company = 'GG';"
        )
        assert gg_rows["inbound_article_rows"]["calculation_plan"]["calculation"]["distinct_by"] == ["book_num", "line_num"]
        assert gg_rows["inbound_article_rows"]["calculation_sql"] == (
            "SELECT COUNT(DISTINCT (book_num, line_num)) AS value FROM v_ask_receive_log WHERE type NOT IN "
            "(23,45,46,47,63,81,91,100) AND qty_suf > 0 AND company = 'GG';"
        )
        mg_rows = {row["id"]: row for row in initial_payload["invoice_rows_by_company"]["MG"]}
        assert set(mg_rows) == {
            "vas_blue_normal",
            "vas_blue_ot_50",
            "vas_blue_ob1_40",
            "vas_blue_ob2_70",
            "vas_blue_ob3_100",
            "vas_white_normal",
            "vas_white_ot_50",
            "vas_white_ob1_40",
            "vas_white_ob2_70",
            "vas_white_ob3_100",
            "it_hourly",
        }
        assert all(mg_rows[row_id]["price"] == gg_rows[row_id]["price"] for row_id in mg_rows if row_id.startswith("vas_"))
        # it_hourly är ett hemligt pris (default 0.0 i repot, riktigt värde lokalt). Kolla typ, inte värde.
        assert isinstance(mg_rows["it_hourly"]["price"], (int, float))
        assert initial_payload["vas_hourly_revenue_by_company"]["MG"] == initial_payload["vas_hourly_revenue_by_company"]["GG"]

        set_productivity_finance_settings(
            session,
            {
                "invoice_rows_by_company": {
                    "MG": [
                        {
                            "id": "inbound_container_unloading",
                            "section": "Inbound",
                            "service": "Inbound",
                            "description": "Containerlossning",
                            "unit": "Per lossad m3",
                            "price": 999,
                        },
                        {
                            "id": "vas_blue_normal",
                            "section": "VAS",
                            "service": "Blue collar VAS",
                            "description": "Per timme",
                            "unit": "Normal",
                            "price": 0,
                            "collar_type": "blue_collar",
                            "vas_rate_type": "normal",
                        },
                        {
                            "id": "it_hourly",
                            "section": "IT",
                            "service": "IT",
                            "description": "Per timme",
                            "unit": "",
                            "price": 0,
                        },
                    ]
                }
            },
            user_id=7,
            business_id=1,
        )
        session.commit()
        legacy_payload = settings_router._productivity_finance_settings_out(session, 1).model_dump()
        legacy_mg_rows = {row["id"]: row for row in legacy_payload["invoice_rows_by_company"]["MG"]}
        assert "inbound_container_unloading" not in legacy_mg_rows
        assert legacy_mg_rows["vas_blue_normal"]["price"] == gg_rows["vas_blue_normal"]["price"]
        assert legacy_mg_rows["it_hourly"]["price"] == 445.0

        result = settings_router.update_productivity_finance_settings_route(
            ProductivityFinanceSettingsUpdate(
                hourly_cost=200,
                vas_hourly_revenue_by_company={
                    "AS": {"blue_collar": 100, "white_collar": 150},
                    "GG": {"blue_collar": 500, "white_collar": 650},
                    "MG": {"blue_collar": 450, "white_collar": 600},
                    "STIGAMO": {"blue_collar": 900, "white_collar": 950},
                },
            ),
            session,
            admin,
            business_id=1,
        )

        assert result.company_codes == ["GG", "MG"]
        assert result.model_dump()["vas_hourly_revenue_by_company"] == {
            "GG": {
                "blue_collar": {"normal": 500.0, "ot_50": 0.0, "ob1_40": 0.0, "ob2_70": 0.0, "ob3_100": 0.0},
                "white_collar": {"normal": 650.0, "ot_50": 0.0, "ob1_40": 0.0, "ob2_70": 0.0, "ob3_100": 0.0},
            },
            "MG": {
                "blue_collar": {"normal": 450.0, "ot_50": 0.0, "ob1_40": 0.0, "ob2_70": 0.0, "ob3_100": 0.0},
                "white_collar": {"normal": 600.0, "ot_50": 0.0, "ob1_40": 0.0, "ob2_70": 0.0, "ob3_100": 0.0},
            },
        }
        assert get_productivity_finance_settings(session, business_id=1) == {
            "hourly_cost": 200.0,
            "vas_hourly_revenue_by_company": {
                "GG": {
                    "blue_collar": {"normal": 500.0, "ot_50": 0.0, "ob1_40": 0.0, "ob2_70": 0.0, "ob3_100": 0.0},
                    "white_collar": {"normal": 650.0, "ot_50": 0.0, "ob1_40": 0.0, "ob2_70": 0.0, "ob3_100": 0.0},
                },
                "MG": {
                    "blue_collar": {"normal": 450.0, "ot_50": 0.0, "ob1_40": 0.0, "ob2_70": 0.0, "ob3_100": 0.0},
                    "white_collar": {"normal": 600.0, "ot_50": 0.0, "ob1_40": 0.0, "ob2_70": 0.0, "ob3_100": 0.0},
                },
            },
            "invoice_rows_by_company": {},
        }
    finally:
        session.close()
        drop_business_settings_tables(engine)
        engine.dispose()


def test_productivity_finance_default_calculations_fill_empty_saved_rows():
    stored_rows = [
        {
            "id": "inbound_labels",
            "section": "Inbound",
            "service": "Inbound",
            "description": "Mottagna etiketter",
            "unit": "Per etikett eller låda",
            "price": 42.72,
            "calculation_prompt": "",
            "calculation_plan": None,
            "calculation_sql": "",
        },
        {
            "id": "store_picked_orders",
            "section": "BUTIK",
            "service": "Outbound",
            "description": "Plockade orders",
            "unit": "Per order",
            "price": 34.84,
            "calculation_prompt": "egen prompt",
            "calculation_plan": {"custom": True},
            "calculation_sql": "SELECT 1;",
            "linked_process_key": "manual_pick!",
            "linked_process_label": "Manual Pick",
        },
    ]

    rows = {row["id"]: row for row in productivity_finance_invoice_rows_for_company("GG", stored_rows)}

    assert rows["inbound_labels"]["calculation_prompt"].startswith("antal poster")
    assert rows["inbound_labels"]["calculation_plan"]["view"] == "v_ask_receive_log"
    assert "company = 'GG'" in rows["inbound_labels"]["calculation_sql"]
    assert rows["store_picked_orders"]["calculation_prompt"] == "egen prompt"
    assert rows["store_picked_orders"]["calculation_plan"] == {"custom": True}
    assert rows["store_picked_orders"]["calculation_sql"] == "SELECT 1;"
    assert rows["store_picked_orders"]["linked_process_key"] == "MANUAL_PICK"
    assert rows["store_picked_orders"]["linked_process_label"] == "Manual Pick"


def test_productivity_finance_invoice_row_cleaning_removes_period_filters():
    rows = clean_productivity_finance_invoice_rows(
        [
            {
                "id": "store_picked_rows",
                "section": "BUTIK",
                "service": "Outbound",
                "description": "Plockade rader",
                "unit": "Per rad",
                "calculation_plan": {
                    "status": "ok",
                    "view": "v_ask_pick_log_full",
                    "filters": [
                        {"id": "order_num", "operator": "StartsWith", "value": "TO"},
                        {"id": "time_stamp_int", "operator": "Between", "value": [20260601, 20260630]},
                        {"id": "company", "operator": "EQ", "value": "GG"},
                    ],
                },
                "calculation_sql": (
                    "SELECT COUNT(*) AS value FROM v_ask_pick_log_full WHERE order_num LIKE 'TO%' "
                    "AND time_stamp_int BETWEEN 20260601 AND 20260630 AND company = 'GG';"
                ),
            }
        ]
    )

    assert rows[0]["calculation_plan"]["filters"] == [
        {"id": "order_num", "operator": "StartsWith", "value": "TO"},
        {"id": "company", "operator": "EQ", "value": "GG"},
    ]
    assert rows[0]["calculation_sql"] == (
        "SELECT COUNT(*) AS value FROM v_ask_pick_log_full WHERE order_num LIKE 'TO%' AND company = 'GG';"
    )


def test_productivity_finance_calculation_test_uses_data_fetch_plan(monkeypatch):
    engine, session = make_business_settings_session()
    try:
        business = Business(id=1, code="STIGAMO", name="Stigamo", company_codes=["GG"], tenant="frey")
        admin = User(id=7, username="root", role="super_user", roles=["super_user"], is_active=True)
        session.add_all([business, admin])
        session.commit()
        captured = {}

        async def fake_plan(prompt):
            captured["prompt"] = prompt
            return {
                "status": "ok",
                "view": "v_ask_receive_log",
                "view_label": "Varumottagningslogg",
                "output_columns": ["rowid"],
                "filters": [{"id": "timestamp", "operator": "Between", "value": ["2026-04-01", "2026-04-30"]}],
            }

        def fake_fetch_rows(plan, error_id, tenant):
            captured["plan"] = plan
            captured["tenant"] = tenant
            return [{"rowid": 1}, {"rowid": 2}, {"rowid": 3}]

        class FakeCatalog:
            def view(self, view_id):
                assert view_id == "v_ask_receive_log"
                timestamp = type("FakeColumn", (), {"id": "timestamp", "label_en": "Timestamp", "label_sv": "Datum"})()
                company = type("FakeColumn", (), {"id": "company", "label_en": "Company", "label_sv": "Bolag"})()
                return type(
                    "FakeView",
                    (),
                    {"column_by_id": {"timestamp": timestamp, "company": company}, "columns": (timestamp, company)},
                )()

        monkeypatch.setattr(settings_router, "_plan_from_prompt", fake_plan)
        monkeypatch.setattr(settings_router, "_fetch_rows", fake_fetch_rows)
        monkeypatch.setattr(settings_router, "load_catalog", lambda: FakeCatalog())

        result = asyncio.run(
            settings_router.test_productivity_finance_calculation_route(
                ProductivityFinanceCalculationTestRequest(
                    prompt="antal rader i varumottagningsloggen",
                    month=4,
                    company_code="GG",
                ),
                session,
                admin,
                business_id=1,
                area_focus=None,
            )
        )

        assert "april" in captured["prompt"]
        assert captured["tenant"] == "frey"
        assert captured["plan"]["view"] == "v_ask_receive_log"
        assert captured["plan"]["filters"][0] == {"id": "timestamp", "operator": "Between", "value": ["2026-04-01", "2026-04-30"]}
        assert captured["plan"]["filters"][-1] == {"id": "company", "operator": "EQ", "value": "GG"}
        assert result.plan["filters"] == [{"id": "company", "operator": "EQ", "value": "GG"}]
        assert result.quantity == 3
        assert result.view == "v_ask_receive_log"
        assert result.view_label == "Varumottagningslogg"
        assert result.calculation_sql == (
            "SELECT COUNT(*) AS value FROM v_ask_receive_log "
            "WHERE company = 'GG';"
        )
    finally:
        session.close()
        drop_business_settings_tables(engine)
        engine.dispose()


def test_productivity_finance_calculation_company_filter_requires_company_column(monkeypatch):
    class FakeCatalog:
        def view(self, view_id):
            assert view_id == "v_ask_receive_log"
            return type("FakeView", (), {"column_by_id": {"timestamp": object()}, "columns": ()})()

    plan = {
        "status": "ok",
        "view": "v_ask_receive_log",
        "filters": [{"id": "timestamp", "operator": "Between", "value": ["2026-04-01", "2026-04-30"]}],
    }
    monkeypatch.setattr(settings_router, "load_catalog", lambda: FakeCatalog())

    assert settings_router._calculation_plan_with_company_filter(plan, "GG") == plan


def test_productivity_finance_calculation_counts_distinct_purchase_items(monkeypatch):
    engine, session = make_business_settings_session()
    try:
        business = Business(id=1, code="STIGAMO", name="Stigamo", company_codes=["GG"], tenant="frey")
        admin = User(id=7, username="root", role="super_user", roles=["super_user"], is_active=True)
        session.add_all([business, admin])
        session.commit()
        captured = {}

        async def fake_plan(prompt):
            captured["prompt"] = prompt
            return {
                "status": "ok",
                "view": "v_ask_receive_log",
                "view_label": "Varumottagningslogg",
                "output_columns": ["book_num", "item_num"],
                "output_column_labels": {"book_num": "Inköpsnr", "item_num": "Artikel"},
                "filters": [
                    {"id": "type", "operator": "NE", "value": 45},
                    {"id": "type", "operator": "NE", "value": 91},
                    {"id": "type", "operator": "NE", "value": 100},
                ],
                "calculation": {
                    "metric": "count_distinct",
                    "field": None,
                    "distinct_by": ["book_num", "item_num"],
                    "group_by": [],
                    "sort_by": None,
                    "limit": None,
                },
            }

        def fake_fetch_rows(plan, error_id, tenant):
            captured["plan"] = plan
            captured["tenant"] = tenant
            return [
                {"book_num": "PO1", "item_num": "A1"},
                {"book_num": "PO1", "item_num": "A1"},
                {"book_num": "PO1", "item_num": "A2"},
                {"book_num": "PO2", "item_num": "A1"},
            ]

        class FakeCatalog:
            def view(self, view_id):
                assert view_id == "v_ask_receive_log"
                return type("FakeView", (), {"column_by_id": {"company": object()}, "columns": ()})()

        monkeypatch.setattr(settings_router, "_plan_from_prompt", fake_plan)
        monkeypatch.setattr(settings_router, "_fetch_rows", fake_fetch_rows)
        monkeypatch.setattr(settings_router, "load_catalog", lambda: FakeCatalog())

        result = asyncio.run(
            settings_router.test_productivity_finance_calculation_route(
                ProductivityFinanceCalculationTestRequest(
                    prompt="antal unika artiklar per inköp i varumottagningsloggen",
                    month=4,
                    company_code="GG",
                ),
                session,
                admin,
                business_id=1,
                area_focus=None,
            )
        )

        assert result.quantity == 3
        assert captured["tenant"] == "frey"
        assert captured["plan"]["filters"][-1] == {"id": "company", "operator": "EQ", "value": "GG"}
        assert result.calculation_sql == (
            "SELECT COUNT(DISTINCT (book_num, item_num)) AS value FROM v_ask_receive_log "
            "WHERE type <> 45 AND type <> 91 AND type <> 100 AND company = 'GG';"
        )
    finally:
        session.close()
        drop_business_settings_tables(engine)
        engine.dispose()

"""Tester för apphjälpens tool-register, handlers, tool-loop och audit."""
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend import assistant_tools
from app.backend.assistant_tools.runtime import run_tool_loop
from app.backend.config import settings
from app.backend.database import Base
from app.backend.deps import get_current_user, get_db
from app.backend.main import app
from app.backend.models import (
    Activity,
    Area,
    AuditLog,
    Business,
    Person,
    PersonProductivityDaily,
    ScheduleCell,
    User,
)
from app.backend.routers import assistant
from app.backend.user_access import ROLE_VIEW_IDS

TEST_DATE = date(2026, 7, 6)  # måndag, ISO-vecka 28


def make_session():
    # StaticPool + check_same_thread=False: endpointen kör tool-loopen i en
    # trådpool och in-memory-sqlite måste dela en och samma anslutning.
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return engine, SessionLocal()


def seed(session):
    stigamo = Business(code="STIGAMO", name="Stigamo", sort_order=1)
    r3 = Business(code="R3", name="R3", sort_order=2)
    session.add_all([stigamo, r3])
    session.flush()
    gg = Area(business_id=stigamo.id, code="GG", name="Granngården", sort_order=1)
    frys = Area(business_id=stigamo.id, code="FRYS", name="Frys", sort_order=2)
    r3_area = Area(business_id=r3.id, code="R3A", name="R3-området", sort_order=1)
    session.add_all([gg, frys, r3_area])
    session.flush()
    plock = Activity(business_id=stigamo.id, code="GG_PLOCK", label="GG Plock", area_id=gg.id, category="work", sort_order=1)
    ledig = Activity(business_id=stigamo.id, code="LEDIG", label="Ledig", category="absence", sort_order=2)
    r3_plock = Activity(business_id=r3.id, code="R3_PLOCK", label="R3 Plock", area_id=r3_area.id, category="work", sort_order=1)
    session.add_all([plock, ledig, r3_plock])
    session.flush()
    anna = Person(business_id=stigamo.id, name="Anna Andersson", home_area_id=gg.id, competencies=["truck"])
    bert = Person(business_id=stigamo.id, name="Bert Berg", home_area_id=frys.id, competencies=[])
    rut = Person(business_id=r3.id, name="Rut R3", home_area_id=r3_area.id, competencies=[])
    session.add_all([anna, bert, rut])
    session.flush()
    leader = User(username="ledare", role="leader", roles=["leader"], business_id=stigamo.id, is_active=True)
    root = User(username="root", role="super_user", roles=["super_user"], business_id=stigamo.id, is_active=True)
    session.add_all([leader, root])
    session.flush()

    year, week, weekday = TEST_DATE.isocalendar()
    session.add_all(
        [
            ScheduleCell(year=year, week=week, weekday=weekday, hour=8, person_id=anna.id, activity_id=plock.id),
            ScheduleCell(year=year, week=week, weekday=weekday, hour=9, person_id=anna.id, activity_id=plock.id),
            ScheduleCell(year=year, week=week, weekday=weekday, hour=8, person_id=bert.id, activity_id=ledig.id),
            ScheduleCell(year=year, week=week, weekday=weekday, hour=8, person_id=rut.id, activity_id=r3_plock.id),
        ]
    )
    session.add(
        PersonProductivityDaily(
            business_id=stigamo.id,
            snapshot_date=TEST_DATE,
            person_id=anna.id,
            row_type="activity",
            item_key="plock",
            metric="points",
            kpi_points=42.5,
            kpi_minutes=120,
        )
    )
    session.add(
        AuditLog(
            business_id=stigamo.id,
            entity_type="person",
            entity_id=anna.id,
            action="update",
            old_value=None,
            new_value={"name": "Anna Andersson"},
            user_id=leader.id,
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
    )
    session.commit()
    return {
        "stigamo": stigamo,
        "r3": r3,
        "gg": gg,
        "leader": leader,
        "root": root,
        "anna": anna,
        "plock": plock,
    }


# ---------------------------------------------------------------- registret


def test_registry_has_many_read_only_tools():
    tools = assistant_tools.all_tools()
    assert len(tools) >= 25
    names = [tool.name for tool in tools]
    assert len(names) == len(set(names))
    for tool in tools:
        assert tool.description.strip()
        assert tool.parameters.get("type") == "object"
        assert tool.view_id in ROLE_VIEW_IDS, f"{tool.name} har okänd view_id {tool.view_id}"
        assert tool.min_level in {"view", "edit"}


def test_openai_declarations_match_registry():
    tools = assistant_tools.all_tools()
    declarations = assistant_tools.openai_tool_declarations(tools)
    assert [entry["function"]["name"] for entry in declarations] == [tool.name for tool in tools]
    assert all(entry["type"] == "function" for entry in declarations)


def test_enforcement_flag_filters_tools_by_view_access(monkeypatch):
    engine, session = make_session()
    data = seed(session)
    try:
        leader = data["leader"]
        all_count = len(assistant_tools.allowed_tools_for(leader, {}))
        assert all_count == len(assistant_tools.all_tools())

        monkeypatch.setattr(settings, "ASSISTANT_TOOLS_ENFORCE_VIEW_ACCESS", True)
        no_analytics = {"leader": {view_id: "none" for view_id in ROLE_VIEW_IDS}}
        filtered = assistant_tools.allowed_tools_for(leader, no_analytics)
        assert filtered == []
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------- handlers


def test_list_areas_is_business_scoped():
    engine, session = make_session()
    data = seed(session)
    try:
        result = assistant_tools.run_tool(session, data["leader"], "list_areas", {})
        codes = {row["code"] for row in result["result"]["areas"]}
        assert codes == {"GG", "FRYS"}

        super_result = assistant_tools.run_tool(session, data["root"], "list_areas", {})
        super_codes = {row["code"] for row in super_result["result"]["areas"]}
        assert super_codes == {"GG", "FRYS", "R3A"}

        r3_result = assistant_tools.run_tool(session, data["root"], "list_areas", {"business": "R3"})
        assert {row["code"] for row in r3_result["result"]["areas"]} == {"R3A"}
    finally:
        session.close()
        engine.dispose()


def test_leader_cannot_reach_other_business_data():
    engine, session = make_session()
    data = seed(session)
    try:
        result = assistant_tools.run_tool(session, data["leader"], "list_areas", {"business": "R3"})
        assert "error" in result

        persons = assistant_tools.run_tool(session, data["leader"], "search_persons", {"query": "Rut"})
        assert persons["result"]["count"] == 0
    finally:
        session.close()
        engine.dispose()


def test_get_person_and_schedule_day():
    engine, session = make_session()
    data = seed(session)
    try:
        person = assistant_tools.run_tool(session, data["leader"], "get_person", {"person": "Anna Andersson"})
        assert person["result"]["home_area"]["code"] == "GG"
        assert person["result"]["competencies"] == ["truck"]

        day = assistant_tools.run_tool(
            session, data["leader"], "get_schedule_day", {"date": TEST_DATE.isoformat()}
        )
        persons = {row["name"]: row for row in day["result"]["persons"]}
        assert "Anna Andersson" in persons
        assert {segment["hour"] for segment in persons["Anna Andersson"]["segments"]} == {8, 9}
        assert "Rut R3" not in persons
    finally:
        session.close()
        engine.dispose()


def test_schedule_staffing_summary_counts_work_and_absence():
    engine, session = make_session()
    data = seed(session)
    try:
        summary = assistant_tools.run_tool(
            session, data["leader"], "schedule_staffing_summary", {"date": TEST_DATE.isoformat()}
        )
        result = summary["result"]
        assert result["persons_per_area"] == {"GG": 1}
        assert result["persons_with_absence"] == 1
        assert result["scheduled_persons_total"] == 2
    finally:
        session.close()
        engine.dispose()


def test_productivity_summary_aggregates():
    engine, session = make_session()
    data = seed(session)
    try:
        result = assistant_tools.run_tool(
            session,
            data["leader"],
            "productivity_summary",
            {"date_from": TEST_DATE.isoformat(), "date_to": TEST_DATE.isoformat()},
        )
        days = result["result"]["days"]
        assert len(days) == 1
        assert days[0]["kpi_points"] == 42.5
        assert days[0]["kpi_minutes"] == 120
    finally:
        session.close()
        engine.dispose()


def test_search_audit_log_scoped_and_truncated():
    engine, session = make_session()
    data = seed(session)
    try:
        result = assistant_tools.run_tool(
            session, data["leader"], "search_audit_log", {"entity_type": "person", "period": "24h"}
        )
        entries = result["result"]["entries"]
        assert len(entries) == 1
        assert entries[0]["username"] == "ledare"
        assert len(entries[0]["payload"]) <= 300
    finally:
        session.close()
        engine.dispose()


def test_list_users_never_exposes_secrets():
    engine, session = make_session()
    data = seed(session)
    try:
        result = assistant_tools.run_tool(session, data["leader"], "list_users", {})
        users = result["result"]["users"]
        assert users
        for row in users:
            assert "password" not in str(sorted(row.keys())).lower()
            assert "hash" not in str(sorted(row.keys())).lower()
    finally:
        session.close()
        engine.dispose()


def test_run_tool_handles_unknown_tool_and_bad_input():
    engine, session = make_session()
    data = seed(session)
    try:
        unknown = assistant_tools.run_tool(session, data["leader"], "drop_database", {})
        assert "error" in unknown

        bad_date = assistant_tools.run_tool(
            session, data["leader"], "get_schedule_day", {"date": "vecka 12"}
        )
        assert "error" in bad_date
        assert "YYYY-MM-DD" in bad_date["error"]
    finally:
        session.close()
        engine.dispose()


def test_resolve_date_tool_returns_iso_parts():
    engine, session = make_session()
    data = seed(session)
    try:
        result = assistant_tools.run_tool(
            session, data["leader"], "resolve_date", {"date": TEST_DATE.isoformat()}
        )
        assert result["result"] == {
            "date": "2026-07-06",
            "iso_year": 2026,
            "iso_week": 28,
            "weekday": 1,
            "weekday_label": "måndag",
        }
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------- tool-loopen


def _tool_call(call_id, name, arguments="{}"):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


def _response(content=None, tool_calls=None):
    message = {"role": "assistant", "content": content or ""}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {"choices": [{"message": message}]}


def test_tool_loop_runs_tools_and_returns_answer():
    engine, session = make_session()
    data = seed(session)
    try:
        responses = [
            _response(tool_calls=[_tool_call("call_1", "list_areas")]),
            _response(content="Det finns två områden: GG och FRYS."),
        ]
        bodies = []

        def call_model(body):
            bodies.append({key: value for key, value in body.items()})
            return responses.pop(0)

        result = run_tool_loop(
            session,
            data["leader"],
            {"model": "test", "messages": [{"role": "user", "content": "Hur många områden?"}], "max_tokens": 700},
            call_model=call_model,
        )
        assert result.answer == "Det finns två områden: GG och FRYS."
        assert result.tool_calls == 1
        assert result.tools_used == ["list_areas"]
        assert result.tool_errors == 0

        assert bodies[0]["max_tokens"] == 1200
        second_messages = bodies[1]["messages"]
        assert second_messages[-1]["role"] == "tool"
        assert "GG" in second_messages[-1]["content"]
        assert second_messages[-2]["role"] == "assistant"
    finally:
        session.close()
        engine.dispose()


def test_tool_loop_forces_answer_on_last_step(monkeypatch):
    engine, session = make_session()
    data = seed(session)
    try:
        monkeypatch.setattr(settings, "ASSISTANT_TOOLS_MAX_STEPS", 2)
        tool_choices = []

        def call_model(body):
            tool_choices.append(body.get("tool_choice"))
            if body.get("tool_choice") == "none":
                return _response(content="Tvingat svar.")
            return _response(tool_calls=[_tool_call("call_x", "list_areas")])

        result = run_tool_loop(
            session,
            data["leader"],
            {"model": "test", "messages": [{"role": "user", "content": "Loopa!"}]},
            call_model=call_model,
        )
        assert result.answer == "Tvingat svar."
        assert tool_choices == ["auto", "none"]
        assert result.tool_calls == 1
    finally:
        session.close()
        engine.dispose()


def test_tool_loop_counts_tool_errors():
    engine, session = make_session()
    data = seed(session)
    try:
        responses = [
            _response(tool_calls=[_tool_call("call_1", "get_schedule_day", '{"date": "trasigt"}')]),
            _response(content="Jag kunde inte tolka datumet."),
        ]
        result = run_tool_loop(
            session,
            data["leader"],
            {"model": "test", "messages": [{"role": "user", "content": "Schema?"}]},
            call_model=lambda _body: responses.pop(0),
        )
        assert result.tool_errors == 1
        assert result.answer == "Jag kunde inte tolka datumet."
    finally:
        session.close()
        engine.dispose()


def test_tool_loop_without_tools_calls_model_once(monkeypatch):
    engine, session = make_session()
    data = seed(session)
    try:
        monkeypatch.setattr(settings, "ASSISTANT_TOOLS_ENABLED", False)
        calls = []

        def call_model(body):
            calls.append(body)
            return _response(content="Bara text.")

        result = run_tool_loop(
            session,
            data["leader"],
            {"model": "test", "messages": [{"role": "user", "content": "Hej"}]},
            call_model=call_model,
        )
        assert result.answer == "Bara text."
        assert result.tool_calls == 0
        assert "tools" not in calls[0]
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------- endpoint + audit


def test_chat_endpoint_runs_tools_and_writes_audit(monkeypatch):
    engine, session = make_session()
    data = seed(session)
    responses = [
        _response(tool_calls=[_tool_call("call_1", "list_areas")]),
        _response(content="Ni har områdena GG och FRYS."),
    ]
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr(assistant, "_minimax_response", lambda _payload: responses.pop(0))
    monkeypatch.setattr(assistant, "get_role_view_access", lambda _db: {})
    app.dependency_overrides[get_current_user] = lambda: data["leader"]
    app.dependency_overrides[get_db] = lambda: session
    try:
        client = TestClient(app)
        response = client.post(
            "/api/assistant/chat",
            json={"messages": [{"role": "user", "content": "Vilka områden har vi?"}]},
        )
    finally:
        app.dependency_overrides.clear()

    try:
        assert response.status_code == 200
        body = response.json()
        assert body["answer"] == "Ni har områdena GG och FRYS."
        assert body["tool_calls"] == 1
        assert body["tools_used"] == ["list_areas"]

        entries = session.query(AuditLog).filter(AuditLog.entity_type == "assistant_chat").all()
        assert len(entries) == 1
        entry = entries[0]
        assert entry.action == "tools_used"
        assert entry.business_id == data["stigamo"].id
        assert entry.new_value["tool_calls"] == 1
        assert entry.new_value["tools_used"] == ["list_areas"]
        # Payload får aldrig innehålla frågetext eller svarstext.
        assert "Vilka områden" not in str(entry.new_value)
        assert "GG och FRYS" not in str(entry.new_value)
        assert entry.new_value["question_chars"] == len("Vilka områden har vi?")
    finally:
        session.close()
        engine.dispose()


def test_chat_endpoint_without_tool_calls_writes_no_audit(monkeypatch):
    engine, session = make_session()
    data = seed(session)
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr(assistant, "_minimax_response", lambda _payload: _response(content="Bara wiki-svar."))
    monkeypatch.setattr(assistant, "get_role_view_access", lambda _db: {})
    app.dependency_overrides[get_current_user] = lambda: data["leader"]
    app.dependency_overrides[get_db] = lambda: session
    try:
        client = TestClient(app)
        response = client.post(
            "/api/assistant/chat",
            json={"messages": [{"role": "user", "content": "Hur fungerar Kopiera dag?"}]},
        )
    finally:
        app.dependency_overrides.clear()

    try:
        assert response.status_code == 200
        assert response.json()["tool_calls"] == 0
        assert session.query(AuditLog).filter(AuditLog.entity_type == "assistant_chat").count() == 0
    finally:
        session.close()
        engine.dispose()

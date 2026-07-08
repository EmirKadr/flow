from __future__ import annotations

from datetime import date
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.backend.database import Base
from app.backend.public_dpak_service import (
    _pick_filters_for_view,
    _pick_source_ranges,
    answer_public_dpak_question,
    replace_public_dpak_dataset,
)
from app.backend.models import PublicDpakRawItemAlias, PublicDpakRawItemAttribute, PublicDpakRawPicklog
from app.backend.public_dpak_agent import PublicDpakAgentError, _align_answer_numbers, run_public_dpak_agent, run_sql_tool
from app.backend.routers import public_dpak


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return SessionLocal()


def _seed(session):
    alias_rows = [
        {"item_num": "100", "unit": "DFP", "conversion_factor": "6"},
        {"item_num": "200", "unit": "DFP", "conversion_factor": "12"},
        {"item_num": "300", "unit": "DFP", "conversion_factor": "4"},
    ]
    attribute_rows = [
        {"item_num": "100", "name": "LastSupplierName", "value": "Bostik"},
        {"item_num": "200", "name": "LastSupplierName", "value": "Bostik"},
        {"item_num": "300", "name": "LastSupplierName", "value": "Annan Leverantor"},
    ]
    live_rows = [
        {
            "rowid": "live-1",
            "time_stamp_int": "20260605",
            "order_num": "O1",
            "custom_num": "K1",
            "line_num": "1",
            "pick_zone": "R",
            "location": "AUTOSTORE",
            "item_num": "100",
            "item_desc": "Lim",
            "qty_suf": "5",
            "pick_pall_num": "B1",
        },
        {
            "rowid": "live-2",
            "time_stamp_int": "20260605",
            "order_num": "O1",
            "custom_num": "K1",
            "line_num": "1",
            "pick_zone": "R",
            "location": "R01",
            "item_num": "100",
            "item_desc": "Lim",
            "qty_suf": "7",
            "pick_pall_num": "B2",
        },
        {
            "rowid": "live-3",
            "time_stamp_int": "20260607",
            "order_num": "O2",
            "custom_num": "K2",
            "line_num": "1",
            "pick_zone": "R",
            "location": "R02",
            "item_num": "200",
            "item_desc": "Tejp",
            "qty_suf": "12",
            "pick_pall_num": "B3",
        },
        {
            "rowid": "live-4",
            "time_stamp_int": "20260608",
            "order_num": "O3",
            "custom_num": "K3",
            "line_num": "1",
            "pick_zone": "A",
            "location": "AUTOSTORE",
            "item_num": "300",
            "item_desc": "Skruv",
            "qty_suf": "8",
            "pick_pall_num": "B4",
        },
        {
            "rowid": "live-5",
            "time_stamp_int": "20260609",
            "order_num": "O4",
            "custom_num": "K4",
            "line_num": "1",
            "pick_zone": "R",
            "location": "R03",
            "item_num": "300",
            "item_desc": "Skruv",
            "qty_suf": "4",
            "pick_pall_num": "B5",
        },
    ]
    archive_rows = [
        {
            "rowid": "archive-duplicate",
            "time_stamp_int": "20260607",
            "order_num": "O2",
            "custom_num": "K2",
            "line_num": "1",
            "pick_zone": "R",
            "location": "R02",
            "item_num": "200",
            "item_desc": "Tejp",
            "qty_suf": "12",
            "pick_pall_num": "B3",
        }
    ]
    for row in live_rows + archive_rows:
        row["company"] = "MG"
    replace_public_dpak_dataset(
        session,
        business_code="STIGAMO",
        pick_sources=[("v_ask_pick_log_full", live_rows), ("dblog_pick_log", archive_rows)],
        alias_rows=alias_rows,
        attribute_rows=attribute_rows,
        source_summary={"mode": "test", "start": "2025-07-01", "end": "2026-07-01"},
    )
    session.commit()


def _ask(session, *contents: str):
    messages = [{"role": "user", "content": content} for content in contents]
    return answer_public_dpak_question(session, messages=messages, business_code="STIGAMO")


def test_public_dpak_sold_in_june_and_follow_up_zone_r():
    session = _session()
    try:
        _seed(session)
        assert "6 D-pak" in _ask(session, "hur många d-pak sålde vi i juni")["answer"]
        assert "4 D-pak" in _ask(session, "hur många d-pak sålde vi i juni", "i zon r?")["answer"]
    finally:
        session.close()


def test_public_dpak_sold_question_handles_real_swedish_characters():
    session = _session()
    try:
        _seed(session)
        question = "hur m" + chr(229) + "nga d-pak s" + chr(229) + "lde vi i juni"
        assert "6 D-pak" in _ask(session, question)["answer"]
    finally:
        session.close()


def test_public_dpak_supplier_count_and_autostore_orders():
    session = _session()
    try:
        _seed(session)
        assert "2 leverant" in _ask(session, "hur många leverantörer har vi totalt plockat")["answer"]
        assert "2 leverant" in _ask(session, "hur många leverantörer har vi totalt plockat", "i zon r?")["answer"]
        assert "2 ordrar" in _ask(session, "hur många ordrar finns det i siffrorna autostore")["answer"]
        assert "1 ordrar" in _ask(
            session,
            "hur många ordrar finns det i siffrorna autostore",
            "i zon r?",
        )["answer"]
    finally:
        session.close()


def test_public_dpak_top_broken_articles_and_dates():
    session = _session()
    try:
        _seed(session)
        result = _ask(session, "vilka artiklar från leverantören bostik bryts oftast")
        assert result["table"][0]["Artikelnr"] == "100"
        assert result["table"][0]["Onödigt brutna"] == 1

        dates = _ask(session, "vilka datum kollar vi")["answer"]
        assert "2025-07-01" in dates
        assert "2026-07-01" in dates
    finally:
        session.close()


def test_public_dpak_raw_import_preserves_three_raw_files():
    session = _session()
    try:
        _seed(session)
        assert session.query(PublicDpakRawPicklog).count() == 6
        assert session.query(PublicDpakRawItemAlias).count() == 3
        assert session.query(PublicDpakRawItemAttribute).count() == 3

        row = session.query(PublicDpakRawPicklog).first()
        assert row.company == "MG"
        assert row.data["company"] == "MG"
        assert row.data["item_num"] == "100"
    finally:
        session.close()


def test_public_dpak_raw_sql_tool_allows_only_raw_selects():
    session = _session()
    try:
        _seed(session)
        result = run_sql_tool(
            session,
            "STIGAMO",
            "select company, count(*) as rows from public_dpak_raw_picklog "
            "where business_code = 'STIGAMO' group by company",
        )
        assert result["rows"] == [{"company": "MG", "rows": 6}]

        try:
            run_sql_tool(session, "STIGAMO", "select * from users")
        except PublicDpakAgentError as exc:
            assert "råa D-pak-tabellerna" in str(exc)
        else:
            raise AssertionError("users table should be blocked")

        try:
            run_sql_tool(session, "STIGAMO", "drop table public_dpak_raw_picklog")
        except PublicDpakAgentError as exc:
            assert "SELECT" in str(exc) or "otillåtna" in str(exc)
        else:
            raise AssertionError("DDL should be blocked")

        try:
            run_sql_tool(session, "STIGAMO", "select * from public_dpak_raw_picklog p, users u")
        except PublicDpakAgentError as exc:
            assert "kommaseparerade" in str(exc)
        else:
            raise AssertionError("comma table joins should be blocked")
    finally:
        session.close()


def test_public_dpak_agent_uses_tools_over_raw_data():
    session = _session()
    calls = []

    def fake_model(payload):
        calls.append(json.loads(payload["messages"][1]["content"]))
        if len(calls) == 1:
            return json.dumps({"type": "tool", "tool": "list_files", "args": {}})
        if len(calls) == 2:
            return json.dumps(
                {
                    "type": "tool",
                    "tool": "run_sql",
                    "args": {
                        "sql": "select company, count(*) as rows from public_dpak_raw_picklog "
                        "where business_code = 'STIGAMO' group by company"
                    },
                }
            )
        return json.dumps(
            {
                "type": "final",
                "answer": "Underlaget jag ser innehåller bara MG.",
                "table": [{"Bolag": "MG", "Rader": 6}],
            },
            ensure_ascii=False,
        )

    try:
        _seed(session)
        result = run_public_dpak_agent(
            session,
            messages=[{"role": "user", "content": "vilket bolag, är alla GG eller MG?"}],
            business_code="STIGAMO",
            call_model=fake_model,
        )
        assert "bara MG" in result["answer"]
        assert result["table"] == [{"Bolag": "MG", "Rader": 6}]
        assert calls[1]["tool_trace"][0]["tool_result"]["files"][0]["companies"] == ["MG"]
    finally:
        session.close()


def test_public_dpak_agent_aligns_answer_numbers_to_table():
    answer = _align_answer_numbers(
        "Hela datasetet innehåller 1 410 088 rader.",
        [{"Bolag": "MG", "Rader": 1411088}],
    )
    assert "1 411 088" in answer


def test_public_dpak_status_endpoint_does_not_require_login(monkeypatch):
    monkeypatch.setattr(public_dpak.settings, "PUBLIC_DPAK_LINK_TOKEN", "")
    session = _session()
    app = FastAPI()
    app.include_router(public_dpak.router)

    def override_db():
        yield session

    app.dependency_overrides[public_dpak.get_db] = override_db
    try:
        response = TestClient(app).get("/api/public/dpak-chat/status")
        assert response.status_code == 200
        assert response.json()["status"] == "missing"
    finally:
        session.close()


def test_public_dpak_message_endpoint_uses_raw_agent_without_token(monkeypatch):
    monkeypatch.setattr(public_dpak.settings, "PUBLIC_DPAK_LINK_TOKEN", "")
    monkeypatch.setattr(public_dpak.settings, "MINIMAX_API_KEY", "test-key")
    calls = []

    def fake_model(payload):
        calls.append(json.loads(payload["messages"][1]["content"]))
        if len(calls) == 1:
            return json.dumps({"type": "tool", "tool": "list_files", "args": {}})
        return json.dumps(
            {
                "type": "final",
                "answer": "Underlaget jag ser innehåller bara MG.",
                "table": [{"Bolag": "MG"}],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(public_dpak, "_call_minimax", fake_model)
    session = _session()
    app = FastAPI()
    app.include_router(public_dpak.router)

    def override_db():
        yield session

    app.dependency_overrides[public_dpak.get_db] = override_db
    try:
        _seed(session)
        response = TestClient(app).post(
            "/api/public/dpak-chat/message",
            json={"messages": [{"role": "user", "content": "vilket bolag är det?"}]},
        )
        assert response.status_code == 200
        payload = response.json()
        assert "bara MG" in payload["answer"]
        assert payload["table"] == [{"Bolag": "MG"}]
    finally:
        session.close()


def test_public_dpak_pick_source_ranges_split_archive_and_live(monkeypatch):
    from app.backend.config import settings

    monkeypatch.setattr(settings, "PUBLIC_DPAK_PREFER_ARCHIVE_DUCKDB", False)
    ranges = _pick_source_ranges(date(2025, 7, 1), date(2026, 7, 1), today=date(2026, 7, 7))

    assert ranges == [
        ("dblog_pick_log", date(2025, 7, 1), date(2026, 5, 27)),
        ("v_ask_pick_log_full", date(2026, 5, 28), date(2026, 7, 1)),
    ]


def test_public_dpak_pick_source_ranges_prefers_local_archive(monkeypatch):
    from app.backend.config import settings

    monkeypatch.setattr(settings, "PUBLIC_DPAK_PREFER_ARCHIVE_DUCKDB", True)
    monkeypatch.setattr(settings, "PUBLIC_DPAK_ARCHIVE_DUCKDB", __file__)
    ranges = _pick_source_ranges(date(2025, 7, 1), date(2026, 7, 1), today=date(2026, 7, 7))

    assert ranges == [("dblog_pick_log", date(2025, 7, 1), date(2026, 7, 1))]


def test_public_dpak_pick_filters_include_company():
    filters = _pick_filters_for_view("dblog_pick_log", date(2025, 7, 1), date(2025, 7, 1), ["GG"])

    assert {"id": "company", "operator": "EQ", "value": "GG"} in filters

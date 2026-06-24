import asyncio
import json
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.backend.routers import sankey as sankey_router
from app.backend.sankey_inbound_service import SankeyInboundError


class FakeDb:
    def __init__(self, business):
        self.business = business

    def get(self, model, id):
        return self.business if id == self.business.id else None

    def close(self):
        pass


async def _collect_sse(response):
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk if isinstance(chunk, str) else chunk.decode("utf-8"))
    text = "".join(chunks)
    events = []
    for block in text.strip().split("\n\n"):
        block = block.strip()
        if block.startswith("data: "):
            events.append(json.loads(block[len("data: "):]))
    return events


def route_user():
    return SimpleNamespace(id=7, username="sankey-user", business_id=1)


def route_business():
    return SimpleNamespace(id=1, code="STIGAMO", name="Stigamo", company_codes=["GG"], tenant="frey")


def test_sankey_inbound_route_returns_payload_and_audits(monkeypatch):
    audits = []
    payload = {
        "period": {"type": "day", "start_date": "2026-06-01", "end_date": "2026-06-01"},
        "filters": {"company": "ALL", "only_consumed": False},
        "summary": {
            "labels_received": 1,
            "purchase_lines_received": 1,
            "labels_traced": 1,
            "labels_consumed": 0,
            "gross_income": 12,
            "gross_income_labels": 10,
            "gross_income_purchase_lines": 2,
        },
        "source_status": [{"key": "receive", "view": "v_ask_receive_log", "status": "api", "rows": 1}],
        "warnings": [],
    }

    monkeypatch.setattr(sankey_router, "get_productivity_finance_settings", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(sankey_router, "load_sankey_inbound_payload", lambda **_kwargs: dict(payload))
    monkeypatch.setattr(sankey_router.audit, "log_and_commit", lambda *args, **kwargs: audits.append(kwargs))

    result = sankey_router.get_sankey_inbound(
        period="day",
        selected_date=date(2026, 6, 1),
        company=None,
        only_consumed=False,
        user=route_user(),
        db=FakeDb(route_business()),
    )

    assert result["business"]["code"] == "STIGAMO"
    assert result["summary"]["gross_income"] == 12
    assert audits[0]["entity_type"] == "sankey_inbound_report"
    assert audits[0]["action"] == "run"
    assert audits[0]["new_value"]["summary"]["purchase_lines_received"] == 1
    assert audits[0]["new_value"]["summary"]["gross_income_purchase_lines"] == 2
    assert audits[0]["new_value"]["source_status"][0]["rows"] == 1


def test_sankey_inbound_route_audits_failed_source(monkeypatch):
    audits = []

    def fail(**_kwargs):
        raise SankeyInboundError(
            "Extern datakalla kunde inte nas.",
            status_code=502,
            source_status=[{"key": "receive", "view": "v_ask_receive_log", "status": "error", "rows": 0}],
        )

    monkeypatch.setattr(sankey_router, "get_productivity_finance_settings", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(sankey_router, "load_sankey_inbound_payload", fail)
    monkeypatch.setattr(sankey_router.audit, "log_and_commit", lambda *args, **kwargs: audits.append(kwargs))

    with pytest.raises(HTTPException) as exc:
        sankey_router.get_sankey_inbound(
            period="day",
            selected_date=date(2026, 6, 1),
            company="GG",
            only_consumed=True,
            user=route_user(),
            db=FakeDb(route_business()),
        )

    assert exc.value.status_code == 502
    assert audits[0]["action"] == "run_failed"
    assert audits[0]["new_value"]["filters"] == {"company": "GG", "only_consumed": True}
    assert audits[0]["new_value"]["warning_codes"] == ["sankey_inbound_error"]


def test_sankey_inbound_stream_emits_progress_then_done(monkeypatch):
    def fake_load(**kwargs):
        callback = kwargs.get("progress_callback")
        if callback:
            callback({"step": 1, "total": 8, "key": "receive", "label": "Hämtar Varumottagningslogg"})
            callback({"step": 1, "total": 8, "key": "receive", "label": "Varumottagningslogg klar", "rows": 3, "done": True})
        return {"summary": {"gross_income": 5}, "period": {}, "warnings": [], "source_status": []}

    monkeypatch.setattr(sankey_router, "get_productivity_finance_settings", lambda *_a, **_k: {})
    monkeypatch.setattr(sankey_router, "load_sankey_inbound_payload", fake_load)
    monkeypatch.setattr(sankey_router, "SessionLocal", lambda: FakeDb(route_business()))
    monkeypatch.setattr(sankey_router, "_audit_sankey_report", lambda *_a, **_k: None)

    response = asyncio.run(
        sankey_router.stream_sankey_inbound(
            period="day",
            selected_date=date(2026, 6, 1),
            company=None,
            only_consumed=False,
            user=route_user(),
            db=FakeDb(route_business()),
        )
    )
    events = asyncio.run(_collect_sse(response))
    types = [event["type"] for event in events]

    assert types[0] == "start"
    assert events[0]["total"] == 8
    assert "progress" in types
    assert types[-1] == "done"
    assert events[-1]["payload"]["summary"]["gross_income"] == 5
    assert events[-1]["payload"]["business"]["code"] == "STIGAMO"

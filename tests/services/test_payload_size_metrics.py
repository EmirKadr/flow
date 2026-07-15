"""Guardrail för mätpunkten i #46: SSE-payloadens storlek ska förbli MÄTT.

Bakgrund: Starlettes GZipMiddleware undantar `text/event-stream`
(`tests/services/test_http_delivery.py::test_gzip_middleware_leaves_sse_streams_alone`
låser det medvetet), och både Sankey - Inbound och Produktivitetsöversikten
levererar hela slutrapporten i SSE-strömmens `done`-event. Payloaden går alltså
okomprimerad över nätet, och ingen visste hur många bytes det var - beslutströskeln
för att bygga om leveransvägen (rå payload >= ~300 KiB) gick inte att utvärdera.

Testerna här skyddar två saker samtidigt:

1. Att mätpunkten finns kvar (en storleksrad per byggd rapport, för båda strömmarna).
2. Att mätpunkten är just en MÄTPUNKT: `done`-eventets payload ska vara byte-identisk
   med vad tjänsten byggde. Ett test som bara kollade loggraden hade inte upptäckt om
   någon råkade banta payloaden "på vägen".

Loggraden får bara bära storlekar och räknare - aldrig rad-, kund- eller filterdata.
"""
from __future__ import annotations

import asyncio
import gzip
import json
import logging
from datetime import date
from types import SimpleNamespace

import pytest

from app.backend.config import settings
from app.backend.observability import log_json_payload_size, measure_json_payload_bytes
from app.backend.routers import productivity as productivity_router
from app.backend.routers import sankey as sankey_router
from app.backend.routers import productivity_helpers


class _FakeDb:
    def __init__(self, business=None):
        self.business = business

    def get(self, _model, _id):
        return self.business

    def close(self):
        pass


def _route_user():
    return SimpleNamespace(id=7, username="metrics-user", business_id=1)


def _route_business():
    return SimpleNamespace(id=1, code="STIGAMO", name="Stigamo", company_codes=["GG"], tenant="frey")


async def _collect_sse(response):
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk if isinstance(chunk, str) else chunk.decode("utf-8"))
    events = []
    for block in "".join(chunks).strip().split("\n\n"):
        block = block.strip()
        if block.startswith("data: "):
            events.append(json.loads(block[len("data: "):]))
    return events


MEASURED_LOGGERS = (
    "app.backend.observability",
    "app.backend.routers.sankey",
    "app.backend.routers.productivity",
)


@pytest.fixture
def payload_logs(caplog):
    """Gor INFO-raderna fangbara aven mitt i en full svit.

    Tva fallgropar, bada kanda i repot:

    1. `observability._install_otel_log_exporter` satter `logging.getLogger("app")` till
       OTEL_LOG_LEVEL (default WARNING). Att bara sanka rotloggern racker inte - raden
       filtreras redan pa `app`-niva. (I drift ar det inget problem: k8s kor
       OTEL_LOG_LEVEL=INFO, sa matpunkten nar Seq.)
    2. Ett tidigare router-test kan ha kort `dictConfig(disable_existing_loggers=True)`
       som satter `.disabled = True` pa modul-loggern - och caplog aterstaller INTE
       `.disabled`. Samma workaround som tests/services/test_productivity_v2.py:858.
    """
    caplog.set_level(logging.INFO)
    caplog.set_level(logging.INFO, logger="app")
    for name in MEASURED_LOGGERS:
        module_logger = logging.getLogger(name)
        module_logger.disabled = False
        caplog.set_level(logging.INFO, logger=name)
    return caplog


def _size_events(caplog) -> list[logging.LogRecord]:
    return [record for record in caplog.records if getattr(record, "event_name", "").endswith(".payload_size")]


def _big_payload() -> dict:
    # Realistiskt formad rapport: många upprepade nycklar => gzip biter hårt.
    return {
        "period": {"type": "month", "start_date": "2026-06-01", "end_date": "2026-06-30"},
        "summary": {"gross_income": 5, "labels_received": 12},
        "warnings": [],
        "source_status": [{"key": "receive", "view": "v_ask_receive_log", "status": "api", "rows": 3}],
        "client_filters": {
            "views": {
                f"month|{index}|0": {"nodes": [{"id": f"n{index}", "value": index}] * 5}
                for index in range(40)
            }
        },
    }


def test_measure_json_payload_bytes_matches_the_bytes_that_go_on_the_wire():
    payload = _big_payload()
    raw_bytes, gzip_bytes = measure_json_payload_bytes(payload)

    expected_raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    assert raw_bytes == len(expected_raw)
    assert gzip_bytes == len(gzip.compress(expected_raw, compresslevel=6, mtime=0))
    assert 0 < gzip_bytes < raw_bytes


def test_log_json_payload_size_emits_sizes_and_never_leaks_content(payload_logs):
    payload = {"rows": [{"kund": "hemlig", "artikel": "A1"}]}
    sizes = log_json_payload_size(
        "flow.test.payload_size",
        feature="test",
        payload=payload,
        attributes={"sse_period": "day"},
    )

    assert sizes is not None and sizes["payload_bytes"] > 0
    record = _size_events(payload_logs)[0]
    assert record.payload_bytes == sizes["payload_bytes"]
    assert record.payload_gzip_bytes == sizes["payload_gzip_bytes"]
    assert record.sse_period == "day"
    # Ingen payloadtext i loggraden.
    serialized = json.dumps({key: str(value) for key, value in record.__dict__.items()}, ensure_ascii=False)
    assert "hemlig" not in serialized and "artikel" not in serialized


def test_log_json_payload_size_is_off_when_flagged_off(monkeypatch, payload_logs):
    monkeypatch.setattr(settings, "PAYLOAD_SIZE_LOGGING_ENABLED", False)
    assert log_json_payload_size("flow.test.payload_size", feature="test", payload={"a": 1}) is None
    assert _size_events(payload_logs) == []


def test_log_json_payload_size_never_breaks_the_report_it_measures(payload_logs):
    class Unserializable:
        pass

    # Får inte kasta - en mätpunkt som fäller rapporten är värre än ingen mätpunkt.
    assert log_json_payload_size("flow.test.payload_size", feature="test", payload=Unserializable()) is None
    assert _size_events(payload_logs) == []


def test_sankey_stream_measures_done_payload_and_delivers_it_unchanged(monkeypatch, payload_logs):
    payload = _big_payload()

    monkeypatch.setattr(sankey_router, "get_productivity_finance_settings", lambda *_a, **_k: {})
    monkeypatch.setattr(sankey_router, "load_sankey_inbound_payload", lambda **_k: json.loads(json.dumps(payload)))
    monkeypatch.setattr(sankey_router, "SessionLocal", lambda: _FakeDb(_route_business()))
    monkeypatch.setattr(sankey_router, "_audit_sankey_report", lambda *_a, **_k: None)

    response = asyncio.run(
        sankey_router.stream_sankey_inbound(
            period="month",
            selected_date=date(2026, 6, 1),
            company=None,
            only_consumed=False,
            user=_route_user(),
            db=_FakeDb(_route_business()),
        )
    )
    events = asyncio.run(_collect_sse(response))

    done = events[-1]
    assert done["type"] == "done"
    # Beteendebevarande: done-payloaden är oförändrad (business tillagd, inget bortbantat).
    expected = {**payload, "business": done["payload"]["business"]}
    assert done["payload"] == expected

    records = _size_events(payload_logs)
    assert len(records) == 1, "Sankey-strömmen ska mäta payloaden exakt en gång per byggd rapport"
    record = records[0]
    assert record.event_name == "flow.sankey_inbound.payload_size"
    assert record.payload_bytes == len(json.dumps(done["payload"], ensure_ascii=False).encode("utf-8"))
    assert record.payload_gzip_bytes < record.payload_bytes
    assert record.client_filter_views == 40
    assert record.sse_period == "month"


def test_productivity_stream_measures_done_payload_and_delivers_it_unchanged(monkeypatch, payload_logs):
    payload = _big_payload()

    def fake_run(_request, _db, _user, *, period, date_filter, start_date, end_date, progress_callback=None):
        return json.loads(json.dumps(payload))

    monkeypatch.setattr(productivity_helpers, "_run_productivity_overview", fake_run)
    monkeypatch.setattr(productivity_helpers, "SessionLocal", lambda: _FakeDb())

    response = asyncio.run(
        productivity_router.stream_productivity_overview(
            request=SimpleNamespace(),
            period="day",
            date_filter=date(2026, 6, 1),
            start_date=None,
            end_date=None,
            user=_route_user(),
            db=_FakeDb(),
        )
    )
    events = asyncio.run(_collect_sse(response))

    done = events[-1]
    assert done["type"] == "done"
    assert done["payload"] == payload

    records = _size_events(payload_logs)
    assert len(records) == 1, "Produktivitetsströmmen ska mäta payloaden exakt en gång per byggd rapport"
    record = records[0]
    assert record.event_name == "flow.productivity.payload_size"
    assert record.payload_bytes == len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    assert record.payload_gzip_bytes < record.payload_bytes


@pytest.mark.parametrize(
    "module, function",
    [
        (sankey_router, "stream_sankey_inbound"),
        (productivity_router, "stream_productivity_overview"),
    ],
)
def test_streams_still_measure_after_refactor(module, function):
    """Kontrakt: båda SSE-strömmarna måste fortsätta anropa mätpunkten.

    Skyddar mot att någon tar bort mätningen i en senare refaktor utan att märka det -
    då blir #46 omätbar igen och beslutet faller tillbaka på gissningar.
    """
    import inspect

    source = inspect.getsource(getattr(module, function))
    assert "log_json_payload_size" in source

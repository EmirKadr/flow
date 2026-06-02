from types import SimpleNamespace

from app.backend import main
from app.backend.business_scope import DEFAULT_BUSINESS_CODE


def test_startup_observations_sync_can_be_disabled_without_loading_tools(monkeypatch):
    monkeypatch.setattr(main.settings, "ALLOCATION_OBSERVATIONS_STARTUP_SYNC", False)
    monkeypatch.setattr(main.allocation_bridge, "require_available", lambda: (_ for _ in ()).throw(AssertionError("loaded")))

    main._sync_allocation_observations_background()


def test_startup_observations_sync_waits_and_spaces_businesses(monkeypatch):
    sleeps: list[float] = []
    calls: list[str] = []
    engine = SimpleNamespace(fetch_observations_from_github=lambda business_code: calls.append(business_code))

    monkeypatch.setattr(main.settings, "ALLOCATION_OBSERVATIONS_STARTUP_SYNC", True)
    monkeypatch.setattr(main.settings, "ALLOCATION_OBSERVATIONS_STARTUP_DELAY_SECONDS", 12.5)
    monkeypatch.setattr(main.settings, "ALLOCATION_OBSERVATIONS_STARTUP_SPACING_SECONDS", 3.5)
    monkeypatch.setattr(main.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(main.allocation_bridge, "require_available", lambda: (engine, SimpleNamespace()))
    monkeypatch.setattr(main, "_allocation_observation_business_codes", lambda: [DEFAULT_BUSINESS_CODE, "R3", "T3"])

    main._sync_allocation_observations_background()

    assert sleeps == [12.5, 3.5, 3.5]
    assert calls == [DEFAULT_BUSINESS_CODE, "R3", "T3"]


def test_startup_observations_sync_falls_back_to_stigamo_when_business_query_fails(monkeypatch):
    class BrokenSession:
        def query(self, *_args, **_kwargs):
            raise RuntimeError("database unavailable")

        def close(self):
            pass

    monkeypatch.setattr(main, "SessionLocal", lambda: BrokenSession())

    assert main._allocation_observation_business_codes() == [DEFAULT_BUSINESS_CODE]


def test_startup_observations_sync_uses_active_business_codes(monkeypatch):
    class Query:
        def filter(self, *_args, **_kwargs):
            return self

        def order_by(self, *_args, **_kwargs):
            return self

        def all(self):
            return [
                SimpleNamespace(code="STIGAMO"),
                SimpleNamespace(code="r3"),
                SimpleNamespace(code="T3"),
                SimpleNamespace(code="R3"),
            ]

    class Session:
        def query(self, *_args, **_kwargs):
            return Query()

        def close(self):
            pass

    monkeypatch.setattr(main, "SessionLocal", lambda: Session())

    assert main._allocation_observation_business_codes() == ["STIGAMO", "R3", "T3"]

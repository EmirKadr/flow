from services.health_service import (
    HealthCheckError,
    build_health_url,
    check_server_health,
)


class FakeResponse:
    def __init__(self, data=None, status_code=200):
        self._data = data or {}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, response):
        self.responses = list(response) if isinstance(response, list) else [response]
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[index]


def test_build_health_url_appends_api_health():
    assert build_health_url("https://example.test").endswith("/api/health")


def test_check_server_health_returns_info():
    response = FakeResponse({"status": "ok", "environment": "production"})
    info = check_server_health(
        base_url="https://example.test",
        session=FakeSession(response),
    )

    assert info.status == "ok"
    assert info.environment == "production"


def test_check_server_health_raises_for_bad_status():
    response = FakeResponse({"status": "down"})

    try:
        check_server_health(session=FakeSession(response))
    except HealthCheckError as exc:
        assert "ok" in str(exc).lower()
    else:
        raise AssertionError("Expected HealthCheckError")


def test_check_server_health_retries_transient_gateway_error(monkeypatch):
    session = FakeSession(
        [
            FakeResponse({"status": "down"}, status_code=502),
            FakeResponse({"status": "down"}, status_code=502),
            FakeResponse({"status": "ok", "environment": "production"}),
        ]
    )
    sleeps = []
    monkeypatch.setattr("services.health_service.time.sleep", lambda seconds: sleeps.append(seconds))

    info = check_server_health(
        base_url="https://example.test",
        session=session,
        attempts=3,
        retry_delay=0.25,
    )

    assert info.status == "ok"
    assert len(session.calls) == 3
    assert sleeps == [0.25, 0.25]

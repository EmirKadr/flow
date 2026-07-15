"""Payloadbudget-kontrakt (W29): leveranslagrets bytes blir mätbara.

Latensbudgeten (test_gap_latency_budget.py) skyddar tiden, frågebudgeten
(tests/services/test_query_count_budgets.py) skyddar antalet SQL-frågor —
men ingen siffra i repot skyddade ANTALET BYTES. Det är därför en svälld
payload eller en gzip som slutat fungera kunde ligga obemärkt.

Tre lager här:

(a) tools/payload_budgets.json <-> api_benchmark: varje budgetnyckel måste
    finnas EXAKT som en DEFAULT_ENDPOINTS-post (inga döda budgetnycklar).
(b) check_payload_budgets-enheten: flaggar över-tak OCH tappad komprimering,
    men inte under-tak. Plus bakåtkompatibilitet: gamla rapportfiler i
    artifacts/api_benchmark/ saknar bytefälten och får aldrig krascha
    print_report/--compare.
(c) DET SKARPA TAKET, som körs i pre-push utan miljö: TestClient mot
    kärnendpoints med deterministiskt seedad databas. En payload som svällt
    (nytt fält per rad, oavsiktlig join, glömd projektion) bryter taket
    lokalt istället för att bli tyst transportkostnad i drift.

Gäller INTE SSE. Produktivitets- och sankey-strömmarna levereras som
text/event-stream, komprimeras aldrig och saknar Content-Length. Varken
api_benchmark eller det här kontraktet säger något om deras payload.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.middleware.gzip import GZipMiddleware

from app.backend.database import Base
from app.backend.deps import get_db
from app.backend.main import app
from app.backend.models import (
    Activity,
    Area,
    Business,
    Person,
    PersonScheduleTemplate,
    ScheduleCell,
    User,
)
from app.backend.security import hash_password
from tools import api_benchmark

BUDGETS_PATH = Path(api_benchmark.__file__).resolve().parent / "payload_budgets.json"


def _load_budgets() -> dict:
    return json.loads(BUDGETS_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# (a) budget-nycklar <-> DEFAULT_ENDPOINTS
# --------------------------------------------------------------------------- #
def test_payload_budget_file_exists_and_parses():
    budgets = _load_budgets()
    assert isinstance(budgets, dict)
    assert any(not str(k).startswith("_") for k in budgets)


def test_every_payload_budget_key_is_exactly_a_default_endpoint():
    budgets = _load_budgets()
    default_endpoints = set(api_benchmark.DEFAULT_ENDPOINTS)
    budget_keys = [k for k in budgets if not str(k).startswith("_")]

    assert budget_keys, "payloadbudgeten saknar riktiga endpoint-nycklar"
    for key in budget_keys:
        assert key in default_endpoints, (
            f"payloadbudgetnyckel {key!r} finns inte exakt i DEFAULT_ENDPOINTS "
            f"(död/felstavad budget); DEFAULT_ENDPOINTS={sorted(default_endpoints)}"
        )


def test_every_default_endpoint_has_a_payload_budget_key():
    """Omvänd riktning: kontraktet ovan enforcar bara budgetnyckel ->
    DEFAULT_ENDPOINTS. Utan den här riktningen kan en ny kärnendpoint läggas i
    DEFAULT_ENDPOINTS utan budgetnyckel och därmed få NOLL byte-tak OCH noll
    gzip-kontroll (check_payload_budgets hoppar tyst över endpoints utan nyckel)
    utan att något test rodnar. Båda riktningarna måste hållas."""
    budgets = _load_budgets()
    budget_keys = {k for k in budgets if not str(k).startswith("_")}

    for endpoint in api_benchmark.DEFAULT_ENDPOINTS:
        assert endpoint in budget_keys, (
            f"DEFAULT_ENDPOINTS-posten {endpoint!r} saknar nyckel i "
            f"payload_budgets.json — den får då varken payload- eller "
            f"gzip-kontroll. Lägg till nyckeln (null om taket är okalibrerat). "
            f"Budgetnycklar: {sorted(budget_keys)}"
        )


def test_payload_budget_values_are_null_or_positive_numbers():
    """null = medvetet okalibrerad. Allt annat måste vara ett positivt byte-tak."""
    budgets = _load_budgets()
    for key, value in budgets.items():
        if str(key).startswith("_"):
            continue
        if value is None:
            continue
        assert isinstance(value, (int, float)) and not isinstance(value, bool), (
            f"payloadbudget för {key!r} är varken null eller ett tal: {value!r}"
        )
        assert value > 0, f"payloadbudget för {key!r} måste vara > 0, är {value!r}"


def test_gzip_minimum_size_matches_the_app_configuration():
    """api_benchmark avgör 'gzip har slutat fungera' utifrån appens minimum_size.
    Driftar den i main.py utan att följas åt här blir kontrollen fel.

    Kopplingen läser den FAKTISKT konfigurerade middlewaren (app.user_middleware),
    inte en regex mot källtexten. En regex som ``GZipMiddleware,\\s*minimum_size=``
    hade blivit falskt röd av en semantiskt identisk omkastning av kwargs
    (``compresslevel=6, minimum_size=1024``); inspektionen bryr sig bara om det
    faktiska värdet."""
    gzip_layers = [m for m in app.user_middleware if m.cls is GZipMiddleware]
    assert len(gzip_layers) == 1, (
        f"förväntar exakt en GZipMiddleware i app-kedjan, fann {len(gzip_layers)}"
    )
    configured = gzip_layers[0].kwargs.get("minimum_size")
    assert configured == api_benchmark.GZIP_MINIMUM_SIZE_BYTES, (
        f"GZipMiddleware minimum_size={configured!r} != "
        f"api_benchmark.GZIP_MINIMUM_SIZE_BYTES={api_benchmark.GZIP_MINIMUM_SIZE_BYTES!r} "
        "— håll siffran i tools/api_benchmark.py i takt med appens middleware."
    )


# --------------------------------------------------------------------------- #
# (b) measure() registrerar bytefälten; check_payload_budgets-enhet;
#     bakåtkompatibilitet mot gamla rapportfiler
# --------------------------------------------------------------------------- #
class _FakeResponse:
    def __init__(self, body: bytes, headers: dict[str, str], status_code: int = 200):
        self.content = body
        self.headers = headers
        self.status_code = status_code

    @property
    def ok(self) -> bool:
        return self.status_code < 400


class _FakeSession:
    def __init__(self, response: _FakeResponse):
        self._response = response

    def get(self, url: str, timeout: int | None = None) -> _FakeResponse:
        return self._response


def test_measure_records_decompressed_bytes_wire_bytes_and_encoding():
    """Två olika storlekar, med flit: len(content) är den uppackade payloaden
    (requests dekomprimerar åt oss), Content-Length är bytes på tråden."""
    response = _FakeResponse(b"x" * 5000, {"Content-Length": "812", "Content-Encoding": "gzip"})

    row = api_benchmark.measure(_FakeSession(response), "http://x.invalid", "/api/areas", samples=2)

    assert row["content_length_bytes"] == 5000
    assert row["wire_bytes"] == 812
    assert row["content_encoding"] == "gzip"
    assert row["content_bytes_samples"] == [5000, 5000]
    assert row["median_ms"] is not None  # latensmätningen är orörd


def test_measure_leaves_wire_bytes_none_without_content_length():
    """Chunked svar (t.ex. SSE) saknar Content-Length. Då finns ingen wire-siffra
    att rapportera - verktyget ska säga None, inte gissa."""
    response = _FakeResponse(b"x" * 5000, {})

    row = api_benchmark.measure(_FakeSession(response), "http://x.invalid", "/api/areas", samples=1)

    assert row["content_length_bytes"] == 5000
    assert row["wire_bytes"] is None
    assert row["content_encoding"] is None


# --------------------------------------------------------------------------- #
def _row(endpoint: str, size: int | None, encoding: str | None = "gzip", status: object = 200) -> dict:
    return {
        "endpoint": endpoint,
        "median_ms": 10.0,
        "best_ms": 9.0,
        "content_length_bytes": size,
        "wire_bytes": size,
        "content_encoding": encoding,
        "status": status,
    }


def test_check_payload_budgets_flags_oversized_payload():
    report = {"results": [_row("/api/areas", 5000)]}
    breaches = api_benchmark.check_payload_budgets(report, {"/api/areas": 4000})

    assert len(breaches) == 1
    assert "/api/areas" in breaches[0]
    assert "5000" in breaches[0]


def test_check_payload_budgets_is_silent_under_the_cap():
    report = {"results": [_row("/api/areas", 3000)]}
    assert api_benchmark.check_payload_budgets(report, {"/api/areas": 4000}) == []


def test_check_payload_budgets_flags_lost_compression():
    """Stor payload utan content-encoding: gzip = komprimeringen har tappats."""
    report = {"results": [_row("/api/areas", 3000, encoding=None)]}
    breaches = api_benchmark.check_payload_budgets(report, {"/api/areas": 4000})

    assert len(breaches) == 1
    assert "gzip" in breaches[0]


def test_check_payload_budgets_ignores_compression_below_gzip_minimum():
    small = api_benchmark.GZIP_MINIMUM_SIZE_BYTES - 1
    report = {"results": [_row("/api/areas", small, encoding=None)]}
    assert api_benchmark.check_payload_budgets(report, {"/api/areas": 4000}) == []


def test_check_payload_budgets_checks_compression_at_exactly_gzip_minimum():
    """Gränsvärdet, precis 1024 B: Starlettes GZipMiddleware komprimerar vid
    len(body) >= minimum_size, så ett svar på EXAKT minimum_size SKA vara gzippat.
    check_payload_budgets måste därför använda `>=`, inte `>`. Med `>` vore
    kontrollen blind på precis den byte den kodar — det här testet fäller den
    mutationen."""
    exact = api_benchmark.GZIP_MINIMUM_SIZE_BYTES

    uncompressed = {"results": [_row("/api/areas", exact, encoding=None)]}
    breaches = api_benchmark.check_payload_budgets(uncompressed, {"/api/areas": None})
    assert len(breaches) == 1, (
        f"ett okomprimerat svar på exakt {exact} B ska flaggas (>=), inte tystas"
    )
    assert "gzip" in breaches[0]

    # Ett gzippat svar på exakt gränsen är korrekt och ska INTE flaggas.
    compressed = {"results": [_row("/api/areas", exact, encoding="gzip")]}
    assert api_benchmark.check_payload_budgets(compressed, {"/api/areas": None}) == []


def test_content_encoding_collapses_uniform_but_keeps_mixed_distinct():
    """_content_encoding: enhetliga sample kollapsar till ETT värde, allt-identity
    rapporteras som None (okomprimerat), men blandade sample behålls distinkta
    (kommaseparerat) i stället för att maskeras till ett enda värde."""
    assert api_benchmark._content_encoding(["gzip", "gzip"]) == "gzip"
    assert api_benchmark._content_encoding([None, None]) is None
    assert api_benchmark._content_encoding(["", "identity"]) is None
    assert api_benchmark._content_encoding(["gzip", None]) == "gzip,identity"


def test_check_payload_budgets_flags_partial_gzip_from_samples():
    """Blandade sample via content_encoding_samples: ETT gzippat sample får inte
    maskera att övriga levererades OKOMPRIMERADE. En substrängmatchning
    ('gzip' in encoding) hade godtagit det här som OK — token-räkningen (alla
    sample MÅSTE vara gzip) fäller det som instabil komprimering."""
    row = {
        "endpoint": "/api/areas",
        "median_ms": 10.0,
        "best_ms": 9.0,
        "content_length_bytes": 5000,
        "wire_bytes": 5000,
        "content_encoding": "gzip,identity",
        "content_encoding_samples": ["identity", "gzip", "identity"],
        "status": 200,
    }
    breaches = api_benchmark.check_payload_budgets({"results": [row]}, {"/api/areas": 6000})

    assert len(breaches) == 1, "1 av 3 gzippat får inte räknas som OK"
    assert "1 av 3" in breaches[0]
    assert "delvis" in breaches[0]


def test_check_payload_budgets_flags_partial_gzip_from_legacy_encoding_string():
    """Även utan per-sample-fältet (äldre rapport) faller ett blandat
    content_encoding tillbaka på komma-split → minst två tokens → inte OK. Det
    stänger substrängmatchningen även för gamla rapportrader."""
    report = {"results": [_row("/api/areas", 5000, encoding="gzip,identity")]}
    breaches = api_benchmark.check_payload_budgets(report, {"/api/areas": 6000})

    assert len(breaches) == 1
    assert "delvis" in breaches[0]
    assert "1 av 2" in breaches[0]


def test_null_budget_still_checks_compression_but_not_size():
    """Okalibrerat tak får inte tysta gzip-kontrollen."""
    budgets = {"/api/areas": None}
    huge_but_gzipped = {"results": [_row("/api/areas", 10_000_000)]}
    assert api_benchmark.check_payload_budgets(huge_but_gzipped, budgets) == []

    uncompressed = {"results": [_row("/api/areas", 10_000, encoding=None)]}
    assert len(api_benchmark.check_payload_budgets(uncompressed, budgets)) == 1


def test_check_payload_budgets_reports_missing_size_and_skips_unbudgeted():
    report = {
        "results": [
            _row("/api/areas", None, encoding=None, status="fel: Timeout"),
            _row("/api/unbudgeted", 9_999_999, encoding=None),
        ]
    }
    breaches = api_benchmark.check_payload_budgets(report, {"_kommentar": "x", "/api/areas": None})

    assert len(breaches) == 1
    assert "/api/areas" in breaches[0]
    assert "/api/unbudgeted" not in " ".join(breaches)


def test_payload_budget_suggestions_only_for_uncalibrated_keys():
    report = {"results": [_row("/api/areas", 1000), _row("/api/persons", 2000)]}
    budgets = {"/api/areas": None, "/api/persons": 5000}

    suggestions = api_benchmark.payload_budget_suggestions(report, budgets)

    assert len(suggestions) == 1
    assert "/api/areas" in suggestions[0]
    assert "1800" in suggestions[0]  # 1000 * PAYLOAD_BUDGET_MARGIN


def _legacy_report() -> dict:
    """Rapport från före payloadmätningen — exakt formen i
    artifacts/api_benchmark/baslinje-20260707.json."""
    return {
        "base_url": "https://example.invalid",
        "ran_at": "2026-07-07T08:20:32",
        "label": "baslinje-20260707",
        "samples": 3,
        "results": [
            {
                "endpoint": "/api/areas",
                "samples_ms": [220.5, 138.2, 130.7],
                "best_ms": 130.7,
                "median_ms": 138.2,
                "status": 200,
            },
            {
                "endpoint": "/api/persons",
                "samples_ms": [],
                "best_ms": None,
                "median_ms": None,
                "status": "fel: Timeout",
            },
        ],
    }


def test_print_report_tolerates_legacy_reports_without_byte_fields(capsys):
    """Bakåtkompatibilitet: en gammal baslinjefil får varken krascha som aktuell
    rapport eller som --compare-underlag. Direkt indexering på de nya fälten
    hade gett KeyError här."""
    api_benchmark.print_report(_legacy_report(), _legacy_report())

    output = capsys.readouterr().out
    assert "/api/areas" in output
    assert "bytes" in output


def test_print_report_compares_new_report_against_legacy_baseline(capsys):
    current = {
        "results": [
            _row("/api/areas", 4096) | {"best_ms": 100.0, "median_ms": 110.0},
        ]
    }
    api_benchmark.print_report(current, _legacy_report())

    output = capsys.readouterr().out
    assert "/api/areas" in output
    assert "4096" in output


def test_check_payload_budgets_tolerates_legacy_report_rows():
    breaches = api_benchmark.check_payload_budgets(_legacy_report(), _load_budgets())

    # Gamla rader saknar bytefälten -> rapporteras som "ingen payloadstorlek",
    # aldrig KeyError.
    assert len(breaches) == 2
    assert all("payloadstorlek" in breach for breach in breaches)


# --------------------------------------------------------------------------- #
# (c) det skarpa taket: TestClient mot kärnendpoints, ingen miljö
# --------------------------------------------------------------------------- #
_TARGET = date.today() + timedelta(days=7)
_ISO = _TARGET.isocalendar()

PERSONS = 20
AREAS = 2
ACTIVITIES = 4

# Uppmätta 2026-07-14 mot seeden nedan (dekomprimerade bytes): areas 175,
# activities 961, persons 4 692, schedule 40 965, summary 493, overview 18 206.
# Taken är +10 %, inte latensbudgetens 60-80 %: seeden är deterministisk och
# saknar brus, så marginalen behöver bara täcka datumbetingad textdrift
# (vecko-/årsnummer är 1-2 tecken). Ett tight tak är hela poängen - med 25 %
# marginal hade ett nytt fält per person (~+10 %) glidit igenom osett.
# Spricker taket: mät om, motivera ökningen, skriv upp siffran här.
PAYLOAD_BUDGET_BYTES = {
    "/api/areas": 195,
    "/api/activities": 1_060,
    "/api/persons": 5_160,
    f"/api/schedule?year={_ISO[0]}&week={_ISO[1]}&weekday=3": 45_000,
    f"/api/schedule/summary?year={_ISO[0]}&week={_ISO[1]}&weekday=3": 545,
    f"/api/overview?year={_ISO[0]}&week={_ISO[1]}": 20_000,
}


@pytest.fixture(scope="module")
def seeded_client():
    """Deterministisk databas -> deterministisk payloadstorlek.

    Egen seed (inte query-budgetens) med flit: byte-taken nedan är låsta till
    exakt den här datamängden, och ska inte kunna spricka för att ett annat
    testmodulsseed ändras."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()

    session.add(Business(id=1, code="STIGAMO", name="Stigamo", sort_order=1, is_active=True))
    session.flush()
    for area_id in range(1, AREAS + 1):
        session.add(
            Area(
                id=area_id,
                business_id=1,
                code=f"A{area_id}",
                name=f"Omrade {area_id}",
                sort_order=area_id,
                is_active=True,
            )
        )
    for activity_id in range(1, ACTIVITIES + 1):
        session.add(
            Activity(
                id=activity_id,
                business_id=1,
                code=f"AKT{activity_id}",
                label=f"Aktivitet {activity_id}",
                category="work",
                area_id=1 + (activity_id % AREAS),
                sort_order=activity_id,
                is_active=True,
            )
        )
    session.flush()
    for person_id in range(1, PERSONS + 1):
        session.add(
            Person(
                id=person_id,
                business_id=1,
                name=f"Person {person_id:02d}",
                home_area_id=1 + (person_id % AREAS),
                is_active=True,
                has_fixed_schedule=True,
            )
        )
    session.flush()
    for person_id in range(1, PERSONS + 1):
        for weekday in range(1, 6):
            session.add(PersonScheduleTemplate(person_id=person_id, weekday=weekday, start_hour=7, end_hour=16))
            for hour in range(7, 16):
                session.add(
                    ScheduleCell(
                        year=_ISO[0],
                        week=_ISO[1],
                        weekday=weekday,
                        hour=hour,
                        person_id=person_id,
                        activity_id=1 + (hour % ACTIVITIES),
                    )
                )
    session.add(
        User(
            username="ledare",
            password_hash=hash_password("pass"),
            role="leader",
            roles=["leader"],
            business_id=1,
            is_active=True,
            must_change_password=False,
        )
    )
    session.commit()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            login = client.post("/api/auth/login", json={"username": "ledare", "password": "pass"})
            assert login.status_code == 200, login.text
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        engine.dispose()


@pytest.mark.parametrize("endpoint", sorted(PAYLOAD_BUDGET_BYTES))
def test_endpoint_stays_within_payload_budget(seeded_client, endpoint):
    response = seeded_client.get(endpoint, headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200, response.text
    # httpx packar upp gzip: len(content) = dekomprimerad payload, samma
    # storleksmått som api_benchmark.measure registrerar.
    size = len(response.content)
    budget = PAYLOAD_BUDGET_BYTES[endpoint]
    assert size <= budget, (
        f"{endpoint} svarar med {size} B (tak {budget} B) för {PERSONS} personer. "
        "Ett sprucket tak betyder oftast ett nytt fält per rad eller en glömd "
        "projektion - transportkostnaden syns aldrig i latenstesterna."
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/persons",
        f"/api/schedule?year={_ISO[0]}&week={_ISO[1]}&weekday=3",
        f"/api/overview?year={_ISO[0]}&week={_ISO[1]}",
    ],
)
def test_large_api_payloads_are_still_gzip_compressed(seeded_client, endpoint):
    """Andra halvan av guardrailen: en komprimering som slutat fungera är lika
    illa som en svälld payload, och lika osynlig."""
    response = seeded_client.get(endpoint, headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200, response.text
    size = len(response.content)
    assert size > api_benchmark.GZIP_MINIMUM_SIZE_BYTES, (
        f"{endpoint} gav bara {size} B - för litet för att bevisa något om gzip; "
        "seeden måste ge ett svar över minimum_size."
    )
    assert response.headers.get("content-encoding") == "gzip", (
        f"{endpoint}: {size} B levereras okomprimerat. GZipMiddleware i "
        "app/backend/main.py komprimerar inte längre API-svaren."
    )
    wire = int(response.headers["content-length"])
    assert wire < size, f"{endpoint}: content-length {wire} B < payload {size} B förväntades"

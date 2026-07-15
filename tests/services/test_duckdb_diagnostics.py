"""Guardrail för mätpunkten i #08: poddens DuckDB-defaults ska gå att LÄSA - utan att
mätningen ändrar vad användaren ser.

`local_archive_store._connect()` öppnar DuckDB utan en enda SET. Optimeringsplanens
antagande är att DuckDB då tar `threads` från nodens kärnor och `memory_limit` från
nodens RAM i stället för från poddens cgroup (CPU 300m / ~1 Gi). Antagandet är
overifierat - det avgörs bara av att läsa `current_setting(...)` i den KÖRANDE podden.
Emir har ingen kubectl-åtkomst, så mätningen exponeras via den befintliga Super
User-healthchecken (`GET /api/healthcheck` -> `duckdb`-blocket) och
`python -m tools.healthcheck duckdb`.

Testerna låser fyra saker:

(a) Mätningen finns kvar i healthcheck-rapporten och larmar i sina `verdicts` när
    DuckDB väljer värden som spränger cgroup-limits - annars vore den ett tyst "ok"
    som ingen kan lita på.
(b) Mätningen ändrar ALDRIG healthcheckens globala status, inte ens i poddfallet där
    verdicts blir "warn". Steg 4 är MÄTA, inte fixa: samma systemtillstånd ska ge
    samma utdata som före mätpunkten. En permanent warn i Historik/Hälsa vore både en
    användarsynlig beteendeändring och en desensibiliserad hälsovy (AGENTS.md
    hälsoregel).
(c) Checken "DuckDB (arkivcache)" skrivs bara när arkivcachen faktiskt är PÅ. Är den
    av öppnar appen aldrig DuckDB, och då får healthchecken inte uttala sig om en
    anslutning som inte finns.
(d) Mätningen går genom arkivcachens egen `_connect` - annars börjar checken ljuga
    den dag #08 lägger `SET threads`/`SET memory_limit` där.

(e) Och den fäller aldrig healthchecken, ens när DuckDB saknas/kraschar.
"""
from __future__ import annotations

import duckdb
import pytest

from app.backend import duckdb_diagnostics as diag
from app.backend import local_archive_store
from app.backend.config import settings as app_settings
from app.backend.healthcheck_service import (
    DUCKDB_CHECK_NAME,
    collect_duckdb,
    run_healthcheck,
    status_rank,
    worst_status,
)
from tools import healthcheck as healthcheck_cli


POD_CGROUP = {"version": "v2", "cpu_limit_cores": 0.3, "memory_limit_bytes": 1024**3}
NODE_HOST = {"cpu_count": 64, "affinity_cpus": 64, "memory_total_bytes": 256 * 1024**3}
# DuckDB i podden: läser VÄRDENS defaults (64 trådar, 204.8 GiB) trots cgroup 0,3 kärnor / 1 GiB.
POD_SETTINGS = {"version": "1.5.4", "settings": {"threads": 64, "memory_limit": "204.8 GiB"}}


@pytest.fixture
def archive_cache_on(monkeypatch):
    """Arkivcachen PÅ, som i drift (k8s: ARCHIVE_CACHE_ENABLED=1). Default är av."""
    monkeypatch.setattr(app_settings, "ARCHIVE_CACHE_ENABLED", True)


@pytest.fixture
def pod_shaped_duckdb(monkeypatch, archive_cache_on):
    """Exakt poddfallet: DuckDB ignorerar cgroupen och tar nodens kärnor/RAM."""
    monkeypatch.setattr(diag, "cgroup_limits", lambda: dict(POD_CGROUP))
    monkeypatch.setattr(diag, "host_facts", lambda: dict(NODE_HOST))
    monkeypatch.setattr(diag, "duckdb_settings", lambda: {**POD_SETTINGS, "settings": dict(POD_SETTINGS["settings"])})


@pytest.mark.parametrize(
    "text, expected",
    [
        ("13.9 GiB", int(13.9 * 1024**3)),
        ("256MB", 256 * 1000**2),
        ("1073741824", 1073741824),
        ("", None),
        ("lagom", None),
    ],
)
def test_parse_size_bytes(text, expected):
    assert diag.parse_size_bytes(text) == expected


def test_cgroup_limits_reads_a_v2_pod(monkeypatch):
    """Cgroup-parsningen kors BARA i podden - en tyst parse-bugg dar skulle ge
    'ingen cgroup hittad' och darmed fel bedomning av #08. Darfor testas den har."""
    files = {"/sys/fs/cgroup/cpu.max": "30000 100000", "/sys/fs/cgroup/memory.max": "1073741824"}
    monkeypatch.setattr(diag, "_read_text", lambda path: files.get(path))

    assert diag.cgroup_limits() == {
        "version": "v2",
        "cpu_limit_cores": 0.3,  # 300m
        "memory_limit_bytes": 1073741824,
    }


def test_cgroup_limits_reads_a_v1_pod(monkeypatch):
    files = {
        "/sys/fs/cgroup/cpu/cpu.cfs_quota_us": "30000",
        "/sys/fs/cgroup/cpu/cpu.cfs_period_us": "100000",
        "/sys/fs/cgroup/memory/memory.limit_in_bytes": "1073741824",
    }
    monkeypatch.setattr(diag, "_read_text", lambda path: files.get(path))

    assert diag.cgroup_limits() == {
        "version": "v1",
        "cpu_limit_cores": 0.3,
        "memory_limit_bytes": 1073741824,
    }


def test_cgroup_limits_treats_unlimited_as_no_limit(monkeypatch):
    files = {"/sys/fs/cgroup/cpu.max": "max 100000", "/sys/fs/cgroup/memory.max": "max"}
    monkeypatch.setattr(diag, "_read_text", lambda path: files.get(path))

    assert diag.cgroup_limits() == {"version": "v2", "cpu_limit_cores": None, "memory_limit_bytes": None}


def test_host_facts_reads_node_memory(monkeypatch):
    monkeypatch.setattr(diag, "_read_text", lambda _path: "MemTotal:       263905636 kB\nMemFree: 12 kB\n")

    assert diag.host_facts()["memory_total_bytes"] == 263905636 * 1024


def test_pod_shaped_run_warns_on_both_axes(monkeypatch):
    """Hela kedjan med poddens verklighet: nod med 64 karnor/256 GiB, cgroup 0,3 karnor/1 GiB."""
    monkeypatch.setattr(diag, "cgroup_limits", lambda: dict(POD_CGROUP))
    monkeypatch.setattr(diag, "host_facts", lambda: dict(NODE_HOST))
    monkeypatch.setattr(
        diag,
        "duckdb_settings",
        lambda: {"version": "1.5.4", "settings": {"threads": 64, "memory_limit": "204.8 GiB"}},
    )

    report = diag.duckdb_diagnostics()

    assert [item["status"] for item in report["verdicts"]] == ["warn", "warn"]
    assert report["memory_limit_bytes"] > POD_CGROUP["memory_limit_bytes"]


def test_threads_verdict_warns_when_duckdb_ignores_the_cpu_limit():
    status, message = diag._threads_verdict(64, POD_CGROUP, NODE_HOST)

    assert status == "warn"
    assert "threads=64" in message
    assert "0.3" in message


def test_threads_verdict_is_ok_when_duckdb_respects_the_cpu_limit():
    status, message = diag._threads_verdict(1, POD_CGROUP, NODE_HOST)

    assert status == "ok"
    assert "#08" in message


def test_memory_verdict_warns_when_duckdb_limit_exceeds_the_pod_limit():
    status, message = diag._memory_verdict(int(204 * 1024**3), "204.8 GiB", POD_CGROUP, NODE_HOST)

    assert status == "warn"
    assert "OOMKill" in message


def test_memory_verdict_is_ok_when_duckdb_limit_fits_in_the_pod():
    status, _message = diag._memory_verdict(256 * 1024**2, "256.0 MiB", POD_CGROUP, NODE_HOST)

    assert status == "ok"


def test_duckdb_diagnostics_reads_the_settings_that_08_hangs_on():
    report = diag.duckdb_diagnostics()

    assert report["available"] is True, report.get("error")
    assert report["version"], "DuckDB-versionen ska rapporteras"
    assert int(report["settings"]["threads"]) >= 1
    assert diag.parse_size_bytes(report["settings"]["memory_limit"]) > 0
    assert {item["key"] for item in report["verdicts"]} == {"threads", "memory_limit"}
    # Mätningen går via arkivcachens _connect (se nästa test) men mot :memory:, så den
    # rör aldrig tenant-filerna eller deras lås.
    assert report["source"] == ":memory: via local_archive_store._connect"


def test_diagnostics_measures_the_connection_the_check_claims_to_measure(monkeypatch):
    """Checken heter "DuckDB (arkivcache)" - då MÅSTE den mäta arkivcachens anslutning.

    #08:s fix är att lägga `SET threads` / `SET memory_limit` i
    `local_archive_store._connect`. Mätte diagnostiken en naken `duckdb.connect()` skulle
    den efter den fixen fortsätta rapportera DuckDB:s ogated defaults - dvs. checken
    skulle påstå att arkivcachen kör 64 trådar medan den i själva verket kör 1, och
    ingen skulle märka det. Testet binder ihop dem: sätter man SET i `_connect` ska
    mätningen läsa just de värdena.
    """
    calls: list[tuple[str, bool]] = []

    def fake_connect(path, *, read_only):
        calls.append((str(path), read_only))
        con = duckdb.connect()
        con.execute("SET threads=3")
        con.execute("SET memory_limit='512MiB'")
        return con

    monkeypatch.setattr(local_archive_store, "_connect", fake_connect)

    probe = diag.duckdb_settings()

    assert calls, "duckdb_settings() öppnade inte arkivcachens anslutning (local_archive_store._connect)"
    assert calls[0][0] == ":memory:", "sonden får aldrig öppna en tenant-fil"
    assert int(probe["settings"]["threads"]) == 3, "mätningen läste inte _connect:s SET threads"
    assert diag.parse_size_bytes(probe["settings"]["memory_limit"]) == 512 * 1024**2


def test_duckdb_diagnostics_degrades_softly_when_duckdb_is_missing(monkeypatch):
    def boom():
        raise ModuleNotFoundError("No module named 'duckdb'")

    monkeypatch.setattr(diag, "duckdb_settings", boom)
    report = diag.duckdb_diagnostics()

    assert report["available"] is False
    assert "duckdb" in report["error"]
    assert report["verdicts"][0]["status"] == "unknown"


def test_healthcheck_exposes_the_duckdb_measurement(archive_cache_on):
    report = run_healthcheck(db=None)

    assert report["duckdb"]["available"] is True
    duckdb_check = [item for item in report["checks"] if item["name"] == DUCKDB_CHECK_NAME]
    assert len(duckdb_check) == 1
    details = duckdb_check[0]["details"]
    assert details["threads"] is not None
    assert details["memory_limit"]
    assert "cgroup" in details and "host" in details
    # Bedömningen finns kvar - men som information, inte som hälsoutslag.
    assert details["verdicts"], "verdicts ska följa med checken"
    assert report["duckdb"]["verdict_status"] in {"ok", "info", "warn", "unknown"}


def test_pod_shaped_measurement_never_changes_the_global_status(pod_shaped_duckdb):
    """BLOCKERARE-guardrail: en ren MÄTPUNKT får inte ändra vad användaren ser.

    I podden läser DuckDB värdens defaults (threads=64 mot 0,3 kärnor, memory_limit
    204.8 GiB mot 1 GiB) och båda verdicts blir "warn". Skrevs den warnen in i `checks`
    - listan hela rapportens globala status räknas fram ur - skulle GET /api/healthcheck
    flippa permanent från "ok" till "warn" för Super User i Historik/Hälsa. Beteendet ska
    vara bevarat: samma systemtillstånd, samma utdata. Warn-fakta ska finnas kvar, men i
    report["duckdb"], inte i den globala statusen.
    """
    report = run_healthcheck(db=None)

    duckdb_checks = [item for item in report["checks"] if item["name"] == DUCKDB_CHECK_NAME]
    other_checks = [item for item in report["checks"] if item["name"] != DUCKDB_CHECK_NAME]
    assert len(duckdb_checks) == 1

    # Mätningen larmar fortfarande - annars vore den värdelös.
    assert [item["status"] for item in report["duckdb"]["verdicts"]] == ["warn", "warn"]
    assert report["duckdb"]["verdict_status"] == "warn"
    assert duckdb_checks[0]["details"]["verdict_status"] == "warn"

    # ...men den kan inte lyfta rapportens globala status. Två oberoende assertions:
    # den globala statusen är EXAKT densamma som utan mätpunkten, och checkens egen
    # status är icke-eskalerande (rank 0 = samma som "ok").
    assert report["status"] == worst_status(other_checks), (
        f"Mätpunkten ändrade rapportens globala status till {report['status']!r} "
        f"(utan mätpunkten: {worst_status(other_checks)!r})"
    )
    assert status_rank(duckdb_checks[0]["status"]) == 0, (
        f"DuckDB-mätpunkten har eskalerande status {duckdb_checks[0]['status']!r} - "
        "den flippar då /api/healthcheck för Super User"
    )
    # Och den smittar inte rekommendationerna heller.
    assert all(item["severity"] != "error" for item in report["recommendations"])


def test_no_duckdb_check_when_the_archive_cache_is_off(monkeypatch):
    """Med ARCHIVE_CACHE_ENABLED=0 öppnar appen aldrig DuckDB (arkivcachen är enda
    konsumenten). Då får healthchecken varken mäta eller uttala sig om "DuckDB
    (arkivcache)" - en check om en anslutning som inte finns är ren desinformation."""
    monkeypatch.setattr(app_settings, "ARCHIVE_CACHE_ENABLED", False)

    def must_not_run():
        raise AssertionError("DuckDB sondades trots att arkivcachen är avstängd")

    monkeypatch.setattr(diag, "duckdb_settings", must_not_run)
    checks: list[dict] = []

    report = collect_duckdb(checks)

    assert checks == [], f"ingen DuckDB-check ska skrivas när arkivcachen är av: {checks}"
    assert report["archive_cache_enabled"] is False
    assert report["available"] is False
    assert "ARCHIVE_CACHE_ENABLED" in report["reason"]


def test_duckdb_check_never_fails_the_healthcheck(monkeypatch, archive_cache_on):
    """Diagnostiken får aldrig fälla healthchecken - inte heller när DuckDB kraschar."""
    monkeypatch.setattr(diag, "duckdb_settings", lambda: (_ for _ in ()).throw(RuntimeError("trasig")))
    checks: list[dict] = []

    report = collect_duckdb(checks)

    assert report["available"] is False
    assert status_rank(checks[0]["status"]) == 0, (
        f"en misslyckad MÄTNING är inte ett hälsofel, men status {checks[0]['status']!r} "
        "lyfter worst_status och flippar /api/healthcheck"
    )
    assert "trasig" in checks[0]["message"]


def test_healthcheck_cli_has_a_duckdb_command_and_reads_the_pod_block(monkeypatch, capsys):
    assert healthcheck_cli.parse_args(["duckdb", "--local"]).command == "duckdb"

    pod_report = {
        "status": "warn",
        "duckdb": {
            "available": True,
            "source": ":memory:",
            "version": "1.5.4",
            "settings": {"threads": 64, "memory_limit": "204.8 GiB"},
            "cgroup": POD_CGROUP,
            "host": NODE_HOST,
            "verdicts": [{"key": "threads", "status": "warn", "message": "threads=64 > 0.3 karnor"}],
        },
    }
    monkeypatch.setattr(healthcheck_cli, "get_remote", lambda *_a, **_k: pod_report)

    assert healthcheck_cli.main(["duckdb", "--base-url", "https://example.test"]) == 0
    out = capsys.readouterr().out
    assert "1.5.4" in out and "threads" in out and "0.3" in out

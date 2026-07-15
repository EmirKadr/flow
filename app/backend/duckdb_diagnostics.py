"""Mätpunkt (inte en optimering): vilka defaults väljer DuckDB i den här processen?

Bakgrund (optimeringskandidat #08): ``local_archive_store._connect()`` öppnar
DuckDB utan en enda ``SET``. Antagandet i optimeringsplanen är att DuckDB då
härleder ``threads`` från VÄRDENS kärnor och ``memory_limit`` från VÄRDENS RAM
(~80 %) i stället för från poddens cgroup-limits (CPU 300m / #{JOB_MEMORY_MAX}Mi).
Antagandet är overifierat - nyare DuckDB kan mycket väl läsa cgroupen. Innan någon
fix byggs ska premissen mätas i den KÖRANDE podden, och det här är mätningen.

Så här läser du den utan kubectl (Emirs maskin har ingen kubectl-åtkomst):

    python -m tools.healthcheck duckdb --base-url https://<miljö> --username <user>

Den går via den befintliga Super User-endpointen ``GET /api/healthcheck``, som nu
bär ett ``duckdb``-block. Lokalt: ``python -m tools.healthcheck duckdb --local``.

Mätningen går genom ARKIVCACHENS EGEN anslutningsfunktion
(``local_archive_store._connect``) och inte genom en naken ``duckdb.connect()``.
Det är avsiktligt: checken i healthchecken heter "DuckDB (arkivcache)" och utger
sig för att beskriva arkivcachens anslutning. Den dag #08 byggs och ``_connect``
börjar köra ``SET threads`` / ``SET memory_limit`` fångar mätningen det
automatiskt. Med en naken ``duckdb.connect()`` skulle den i stället fortsätta
rapportera ogated defaults - och alltså börja LJUGA om exakt den anslutning den
påstår sig mäta. ``tests/services/test_duckdb_diagnostics.py`` låser bindningen.

Två saker som gör mätningen ofarlig för driften:

- Den öppnar ``_connect(Path(":memory:"))``, aldrig en tenant-fil. ``threads`` och
  ``memory_limit`` härleds identiskt oavsett om databasen ligger på disk eller i
  minnet, så svaret blir detsamma - men vi rör varken filens lås eller DuckDB:s
  instanscache och kan därmed inte störa en pågående seed/läsning.
- Den skriver ingenting och läser inga rader. Bara ``current_setting(...)`` plus
  cgroup-/värdfakta ur ``/sys/fs/cgroup`` och ``/proc``.

Undantag: ``temp_directory`` rapporteras för in-memory-anslutningen och är därför
INTE samma värde som en filbackad databas får (den defaultar till
``<dbfil>.tmp/`` bredvid databasfilen). Fältet finns med för fullständighets skull,
men slutsatser om spill-katalogen ska inte dras ur det.

Mätningen är INFORMATION, inte ett hälsoutslag: ``collect_duckdb`` i
``healthcheck_service`` lägger den aldrig i healthcheckens globala status (se
``DUCKDB_CHECK_STATUS`` där). Bedömningarna nedan (``verdicts``) läses via
``python -m tools.healthcheck duckdb`` och ur ``report["duckdb"]``.
"""
from __future__ import annotations

import logging
import math
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Inställningar vi frågar DuckDB om. Okända namn hoppas tyst över (versionsskillnader).
SETTING_NAMES = ("memory_limit", "threads", "external_threads", "temp_directory")

_SIZE_RE = re.compile(r"^\s*([0-9]+(?:[.,][0-9]+)?)\s*([A-Za-z]*)\s*$")
_SIZE_UNITS = {
    "": 1,
    "B": 1,
    "KB": 1000,
    "KIB": 1024,
    "MB": 1000**2,
    "MIB": 1024**2,
    "GB": 1000**3,
    "GIB": 1024**3,
    "TB": 1000**4,
    "TIB": 1024**4,
}


def parse_size_bytes(value: Any) -> int | None:
    """'13.9 GiB' / '256MB' / '1073741824' -> bytes. None när det inte går att tolka."""
    match = _SIZE_RE.match(str(value or ""))
    if not match:
        return None
    number = float(match.group(1).replace(",", "."))
    unit = _SIZE_UNITS.get(match.group(2).upper())
    if unit is None:
        return None
    return int(number * unit)


def _read_text(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except Exception:
        return None


def cgroup_limits() -> dict[str, Any]:
    """Poddens faktiska limits, cgroup v2 först och v1 som fallback. Tomt utanför Linux."""
    result: dict[str, Any] = {"version": None, "cpu_limit_cores": None, "memory_limit_bytes": None}

    cpu_max = _read_text("/sys/fs/cgroup/cpu.max")  # "max 100000" eller "30000 100000"
    memory_max = _read_text("/sys/fs/cgroup/memory.max")
    if cpu_max or memory_max:
        result["version"] = "v2"
        parts = (cpu_max or "").split()
        if len(parts) == 2 and parts[0] != "max":
            try:
                quota, period = int(parts[0]), int(parts[1])
                if period > 0:
                    result["cpu_limit_cores"] = round(quota / period, 3)
            except ValueError:
                pass
        if memory_max and memory_max != "max":
            try:
                result["memory_limit_bytes"] = int(memory_max)
            except ValueError:
                pass
        return result

    quota_text = _read_text("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
    period_text = _read_text("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
    memory_text = _read_text("/sys/fs/cgroup/memory/memory.limit_in_bytes")
    if quota_text or memory_text:
        result["version"] = "v1"
        try:
            quota, period = int(quota_text or "-1"), int(period_text or "0")
            if quota > 0 and period > 0:
                result["cpu_limit_cores"] = round(quota / period, 3)
        except ValueError:
            pass
        try:
            limit = int(memory_text or "0")
            # v1 markerar "ingen limit" med ett absurt stort tal.
            if 0 < limit < (1 << 62):
                result["memory_limit_bytes"] = limit
        except ValueError:
            pass
    return result


def host_facts() -> dict[str, Any]:
    """Nodens kärnor/RAM - det DuckDB härleder sina defaults ur om den ignorerar cgroupen."""
    facts: dict[str, Any] = {
        "cpu_count": os.cpu_count(),
        "affinity_cpus": None,
        "memory_total_bytes": None,
    }
    try:
        facts["affinity_cpus"] = len(os.sched_getaffinity(0))  # type: ignore[attr-defined]
    except Exception:
        facts["affinity_cpus"] = None
    meminfo = _read_text("/proc/meminfo")
    if meminfo:
        for line in meminfo.splitlines():
            if line.startswith("MemTotal:"):
                digits = re.sub(r"[^0-9]", "", line)
                if digits:
                    facts["memory_total_bytes"] = int(digits) * 1024
                break
    return facts


# Sonden går via arkivcachens egen _connect(), men mot :memory: i stället för en
# tenant-fil: samma kodväg (och därmed samma framtida SET-satser från #08), utan att
# ta ett fillås eller krocka med DuckDB:s instanscache. Path(":memory:").parent är "."
# så _connect:s mkdir är en no-op och ingen fil skapas.
PROBE_PATH = Path(":memory:")
PROBE_SOURCE = ":memory: via local_archive_store._connect"


def duckdb_settings() -> dict[str, Any]:
    """current_setting() för de inställningar som #08 handlar om, mätt på ARKIVCACHENS
    anslutningsväg (``local_archive_store._connect``). Rör aldrig tenant-filerna."""
    import duckdb  # lazy: samma mönster som local_archive_store._connect

    from .local_archive_store import _connect

    result: dict[str, Any] = {"version": getattr(duckdb, "__version__", None), "settings": {}}
    con = _connect(PROBE_PATH, read_only=False)
    if con is None:  # _connect returnerar bara None för read_only mot en saknad fil
        raise RuntimeError("local_archive_store._connect gav ingen anslutning")
    try:
        for name in SETTING_NAMES:
            try:
                row = con.execute("SELECT current_setting(?)", [name]).fetchone()
            except Exception:
                continue
            if row:
                result["settings"][name] = row[0]
    finally:
        con.close()
    return result


def _threads_verdict(threads: int | None, cgroup: dict[str, Any], host: dict[str, Any]) -> tuple[str, str]:
    cores = cgroup.get("cpu_limit_cores")
    if threads is None:
        return "unknown", "DuckDB rapporterade ingen threads-inställning."
    if cores is None:
        return (
            "info",
            f"DuckDB kör med threads={threads}. Ingen cgroup-CPU-limit hittad "
            f"(kör utanför container?), så det här speglar maskinens kärnor "
            f"({host.get('cpu_count')}).",
        )
    allowed = max(1, math.ceil(float(cores)))
    if threads > allowed:
        return (
            "warn",
            f"DuckDB valde threads={threads} trots CPU-limit {cores} kärnor "
            f"(nod: {host.get('cpu_count')} kärnor). DuckDB läser alltså INTE cgroupen - "
            "varje arkivfråga startar fler trådar än podden får köra och bränner CFS-kvoten.",
        )
    return (
        "ok",
        f"DuckDB valde threads={threads}, vilket ryms i CPU-limiten ({cores} kärnor). "
        "Trådtaket i kandidat #08 behövs inte.",
    )


def _memory_verdict(limit_bytes: int | None, raw: Any, cgroup: dict[str, Any], host: dict[str, Any]) -> tuple[str, str]:
    pod_limit = cgroup.get("memory_limit_bytes")
    if limit_bytes is None:
        return "unknown", f"Kunde inte tolka DuckDB:s memory_limit ({raw!r})."
    if pod_limit is None:
        host_total = host.get("memory_total_bytes")
        suffix = f" (maskinens RAM: {round((host_total or 0) / 1024**3, 1)} GiB)" if host_total else ""
        return "info", f"DuckDB memory_limit = {raw}. Ingen cgroup-minneslimit hittad{suffix}."
    if limit_bytes > pod_limit:
        return (
            "warn",
            f"DuckDB memory_limit = {raw} ({round(limit_bytes / 1024**3, 2)} GiB) är större än poddens "
            f"minneslimit ({round(pod_limit / 1024**3, 2)} GiB). Taket skyddar alltså inte podden - "
            "OOMKill sker innan DuckDB själv säger ifrån.",
        )
    return (
        "ok",
        f"DuckDB memory_limit = {raw} ryms i poddens minneslimit "
        f"({round(pod_limit / 1024**3, 2)} GiB).",
    )


def duckdb_diagnostics() -> dict[str, Any]:
    """Hela mätpunkten: DuckDB-defaults + cgroup-/värdfakta + en läsbar bedömning."""
    cgroup = cgroup_limits()
    host = host_facts()
    report: dict[str, Any] = {
        "available": False,
        "source": PROBE_SOURCE,
        "version": None,
        "settings": {},
        "cgroup": cgroup,
        "host": host,
        "verdicts": [],
    }
    try:
        probe = duckdb_settings()
    except Exception as exc:  # noqa: BLE001 - diagnostiken får aldrig fälla healthchecken
        logger.debug("DuckDB-diagnostiken kunde inte köras", exc_info=True)
        report["error"] = str(exc)[:300]
        report["verdicts"] = [{"status": "unknown", "message": f"DuckDB kunde inte läsas: {str(exc)[:200]}"}]
        return report

    report["available"] = True
    report["version"] = probe.get("version")
    report["settings"] = probe.get("settings") or {}

    raw_threads = report["settings"].get("threads")
    try:
        threads = int(raw_threads) if raw_threads is not None else None
    except (TypeError, ValueError):
        threads = None
    raw_memory = report["settings"].get("memory_limit")
    memory_bytes = parse_size_bytes(raw_memory)
    report["memory_limit_bytes"] = memory_bytes

    status_threads, message_threads = _threads_verdict(threads, cgroup, host)
    status_memory, message_memory = _memory_verdict(memory_bytes, raw_memory, cgroup, host)
    report["verdicts"] = [
        {"key": "threads", "status": status_threads, "message": message_threads},
        {"key": "memory_limit", "status": status_memory, "message": message_memory},
    ]
    return report

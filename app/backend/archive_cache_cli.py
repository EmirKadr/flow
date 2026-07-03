"""CLI: fyll den lokala DuckDB-cachen UTAN att starta servern, parallellt och
med live-progressbar per tenant/vy.

    python -m app.backend.archive_cache_cli               # seeda alla aktiva tenants
    python -m app.backend.archive_cache_cli --tenant frey # bara en tenant
    python -m app.backend.archive_cache_cli --snapshots-only
    python -m app.backend.archive_cache_cli --view item_alias
    python -m app.backend.archive_cache_cli --productivity-only --productivity-start 2025-01-01
    python -m app.backend.archive_cache_cli --tenant frey --with-productivity --productivity-date 2026-07-01
    python -m app.backend.archive_cache_cli --workers 8   # fler parallella hämtningar
    python -m app.backend.archive_cache_cli --status      # visa bara täckning + logg

Arkivvyer (`dblog_*`) chunkas per datum. Snapshotvyer (i dag `item_alias`) görs
som full replace. Körningen är återupptagningsbar för arkivvyer (Ctrl+C och kör
igen fortsätter där den slutade). Kräver ARCHIVE_CACHE_ENABLED=1 och API-uppgifter
i app/.env.

Produktivitetslage utan datum hamtar samma bakatfonster som ARCHIVE_CACHE_SEED_DAYS,
till och med igar. Startdatum utan slutdatum hamtar till och med igar, aldrig dagens
datum i defaultlaget. Det kan samtidigt bygga `person_productivity_daily`.
`--productivity-prebuild-existing` bygger bara redan hamtade snapshots.
`--productivity-only` kan koras utan DuckDB-arkivcachen.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from collections import OrderedDict
from datetime import date, datetime, timedelta

from sqlalchemy import text

from . import archive_cache_sync as sync
from . import local_archive_store as store
from .business_scope import DEFAULT_BUSINESS_CODE
from .config import settings
from .database import SessionLocal
from .productivity_sync import (
    LOCAL_TZ,
    ProductivitySyncError,
    prebuild_ready_productivity_days,
    productivity_snapshot_is_stale,
    productivity_snapshot_status,
    sync_productivity_snapshot,
    sync_productivity_snapshot_history,
)

_BAR_WIDTH = 22
_DEFAULT_PRODUCTIVITY_CHUNK_DAYS = 31


def _fmt_int(value: int) -> str:
    return f"{int(value):,}".replace(",", " ")


def _bar(done: int, total: int) -> tuple[str, float]:
    pct = max(0.0, min(1.0, (done / total) if total else 1.0))
    fill = int(pct * _BAR_WIDTH)
    return "#" * fill + "." * (_BAR_WIDTH - fill), pct * 100


def _parse_iso_date(parser: argparse.ArgumentParser, value: str | None, label: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        parser.error(f"{label} maste vara YYYY-MM-DD.")
    return None


def _default_productivity_end() -> date:
    return datetime.now(LOCAL_TZ).date() - timedelta(days=1)


def _default_productivity_start(end: date) -> date:
    seed_days = max(1, int(getattr(settings, "ARCHIVE_CACHE_SEED_DAYS", 400) or 400))
    return end - timedelta(days=seed_days - 1)


def _productivity_date_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> tuple[str, date | None, date | None]:
    single = _parse_iso_date(parser, args.productivity_date, "--productivity-date")
    start = _parse_iso_date(parser, args.productivity_start, "--productivity-start")
    end = _parse_iso_date(parser, args.productivity_end, "--productivity-end")
    if single and (start or end):
        parser.error("--productivity-date kan inte kombineras med --productivity-start/--productivity-end.")
    if single:
        return "day", single, single
    if getattr(args, "productivity_prebuild_existing", False):
        if start or end:
            parser.error("--productivity-prebuild-existing kan inte kombineras med --productivity-start/--productivity-end.")
        return "prebuild", None, None
    if end and not start:
        start = _default_productivity_start(end)
    if not start and not end:
        range_end = _default_productivity_end()
        return "range", _default_productivity_start(range_end), range_end
    range_start = start
    range_end = end or _default_productivity_end()
    if range_start is not None and range_start > range_end:
        parser.error("--productivity-start far inte vara efter --productivity-end/igar.")
    return "range", range_start, range_end


def _productivity_chunks(start: date, end: date, chunk_days: int) -> list[tuple[date, date]]:
    span_days = max(1, int(chunk_days or _DEFAULT_PRODUCTIVITY_CHUNK_DAYS))
    chunks: list[tuple[date, date]] = []
    current = start
    while current <= end:
        chunk_end = min(end, current + timedelta(days=span_days - 1))
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return list(reversed(chunks))


def _date_range(start: date, end: date) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def _date_span_text(dates: list[date] | list[str]) -> str:
    if not dates:
        return "-"
    values = [str(item)[:10] for item in dates]
    if len(values) == 1:
        return values[0]
    return f"{values[0]}..{values[-1]}"


def _source_rows_total(sources: list[dict] | None) -> int:
    total = 0
    for source in sources or []:
        try:
            total += int(source.get("rows") or 0)
        except (TypeError, ValueError):
            continue
    return total


def _productivity_snapshot_scan(chunk_dates: list[date]) -> dict:
    saved_days = 0
    current_days = 0
    saved_rows = 0
    stale_dates: list[date] = []
    for snapshot_date in chunk_dates:
        status = productivity_snapshot_status(snapshot_date)
        ready = bool(status.get("ready"))
        stale = productivity_snapshot_is_stale(snapshot_date)
        if ready:
            saved_days += 1
            saved_rows += _source_rows_total(status.get("sources") or [])
        if ready and not stale:
            current_days += 1
        if stale:
            stale_dates.append(snapshot_date)
    return {
        "days": len(chunk_dates),
        "saved_days": saved_days,
        "current_days": current_days,
        "missing_days": max(0, len(chunk_dates) - saved_days),
        "stale_saved_days": max(0, saved_days - current_days),
        "saved_rows": saved_rows,
        "stale_dates": stale_dates,
    }


def _productivity_scan_text(scan: dict) -> str:
    total_days = int(scan.get("days") or 0)
    parts = [
        f"snapshots aktuella {int(scan.get('current_days') or 0)}/{total_days}d",
    ]
    stale_saved = int(scan.get("stale_saved_days") or 0)
    missing = int(scan.get("missing_days") or 0)
    if stale_saved:
        parts.append(f"sparade men gamla {stale_saved}d")
    if missing:
        parts.append(f"saknas {missing}d")
    parts.append(f"rader i sparade snapshots {_fmt_int(int(scan.get('saved_rows') or 0))}")
    return ", ".join(parts)


def _productivity_result_counters(result: dict) -> dict:
    counters = {
        "synced_days": len(result.get("synced_dates") or []),
        "skipped_days": len(result.get("skipped_dates") or []),
        "api_rows": 0,
        "person_current": 0,
        "person_materialized": 0,
        "person_errors": 0,
    }
    for item in result.get("results") or []:
        if not isinstance(item, dict):
            continue
        counters["api_rows"] += _source_rows_total(item.get("sources") or [])
        person_result = item.get("person_cache")
        if not isinstance(person_result, dict) and item.get("snapshot") == "ready":
            person_result = item
        if isinstance(person_result, dict):
            status_text = str(person_result.get("status") or "")
            if status_text == "current":
                counters["person_current"] += 1
            elif status_text == "materialized":
                counters["person_materialized"] += 1
            elif status_text == "error":
                counters["person_errors"] += 1
    return counters


def _productivity_done_text(result: dict, scan: dict, *, warm_cache: bool) -> str:
    counters = _productivity_result_counters(result)
    parts = [
        f"API hämtade={counters['synced_days']}d",
        f"sparade snapshots={counters['skipped_days']}d",
    ]
    if counters["synced_days"]:
        parts.append(f"API-rader={_fmt_int(counters['api_rows'])}")
    else:
        parts.append(f"sparade snapshotrader={_fmt_int(int(scan.get('saved_rows') or 0))}")
    if warm_cache:
        parts.append(
            "persondagar "
            f"aktuella={counters['person_current']}d, "
            f"byggda={counters['person_materialized']}d"
        )
        if counters["person_errors"]:
            parts.append(f"persondagsfel={counters['person_errors']}d")
    else:
        parts.append("persondagar=av")
    errors = result.get("errors") or []
    if errors:
        parts.append(f"fel={len(errors)}")
    return ", ".join(parts)


def _print_productivity_chunk_start(
    index: int,
    total: int,
    chunk_start: date,
    chunk_end: date,
    scan: dict,
    *,
    warm_cache: bool,
) -> None:
    bar, pct = _bar(index - 1, total)
    stale_dates = scan.get("stale_dates") or []
    if stale_dates:
        action = f"hämtar API för {len(stale_dates)}d ({_date_span_text(stale_dates)})"
        if warm_cache:
            action += " och bygger/kontrollerar persondagar"
    elif warm_cache:
        action = "ingen API-hämtning; kontrollerar/bygger persondagar från sparade snapshots"
    else:
        action = "redan klar; hoppar över"
    print(f"Produktivitet {index}/{total} [{bar}] {pct:5.1f}%: {chunk_start}..{chunk_end}")
    print(f"  Sparat före start: {_productivity_scan_text(scan)}.")
    print(f"  Åtgärd: {action}.")


def _print_productivity_chunk_done(index: int, total: int, text: str) -> None:
    bar, pct = _bar(index, total)
    print(f"  KLAR {index}/{total} [{bar}] {pct:5.1f}%: {text}.")


def _productivity_range_done_text(result: dict, *, warm_cache: bool) -> str:
    totals = {
        "synced_days": 0,
        "skipped_days": 0,
        "api_rows": 0,
        "person_current": 0,
        "person_materialized": 0,
        "person_errors": 0,
    }
    for chunk_result in result.get("results") or []:
        if not isinstance(chunk_result, dict):
            continue
        counters = _productivity_result_counters(chunk_result)
        for key in totals:
            totals[key] += counters[key]
    parts = [
        f"API hämtade {totals['synced_days']} datum",
        f"återanvände {totals['skipped_days']} sparade snapshotdatum",
        f"API-rader {_fmt_int(totals['api_rows'])}",
    ]
    if warm_cache:
        parts.append(
            "persondagar "
            f"aktuella {totals['person_current']}, "
            f"byggda {totals['person_materialized']}"
        )
        if totals["person_errors"]:
            parts.append(f"persondagsfel {totals['person_errors']}")
    return ", ".join(parts)


def _sync_productivity_range(
    start: date,
    end: date,
    *,
    args: argparse.Namespace,
    business_code: str,
    db,
    warm_cache: bool,
) -> dict:
    results = []
    errors = []
    dates: list[str] = []
    chunk_days = max(1, int(args.productivity_chunk_days or _DEFAULT_PRODUCTIVITY_CHUNK_DAYS))
    chunks = _productivity_chunks(start, end, chunk_days)
    for index, (chunk_start, chunk_end) in enumerate(chunks, start=1):
        chunk_dates = _date_range(chunk_start, chunk_end)
        scan = _productivity_snapshot_scan(chunk_dates)
        needs_fetch = bool(scan.get("stale_dates"))
        _print_productivity_chunk_start(
            index,
            len(chunks),
            chunk_start,
            chunk_end,
            scan,
            warm_cache=warm_cache,
        )
        if not needs_fetch and not warm_cache:
            dates.extend(item.isoformat() for item in chunk_dates)
            result = {
                "status": "ok",
                "source": "api_snapshot_history",
                "dates": [item.isoformat() for item in chunk_dates],
                "synced_dates": [],
                "skipped_dates": [item.isoformat() for item in chunk_dates],
                "errors": [],
            }
            results.append(result)
            _print_productivity_chunk_done(
                index,
                len(chunks),
                _productivity_done_text(result, scan, warm_cache=warm_cache),
            )
            continue
        try:
            result = sync_productivity_snapshot_history(
                chunk_end,
                days_back=(chunk_end - chunk_start).days,
                business_code=business_code,
                db=db,
                warm_cache=warm_cache,
                skip_ready=True,
            )
        except ProductivitySyncError as exc:
            errors.append(
                {
                    "start": chunk_start.isoformat(),
                    "end": chunk_end.isoformat(),
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
            break
        results.append(result)
        dates.extend(str(item) for item in (result.get("dates") or []))
        _print_productivity_chunk_done(
            index,
            len(chunks),
            _productivity_done_text(result, scan, warm_cache=warm_cache),
        )
        chunk_errors = result.get("errors") or []
        if chunk_errors:
            errors.append({"start": chunk_start.isoformat(), "end": chunk_end.isoformat(), "errors": chunk_errors})
            break
        if str(result.get("status") or "ok") in {"error", "running", "not_configured"}:
            errors.append(
                {
                    "start": chunk_start.isoformat(),
                    "end": chunk_end.isoformat(),
                    "status": result.get("status"),
                }
            )
            break
    return {
        "status": "error" if errors else "ok",
        "source": "api_snapshot_history_chunks",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "chunk_days": chunk_days,
        "dates": dates,
        "results": results,
        "errors": errors,
    }


def _productivity_db_error(db) -> str | None:
    execute = getattr(db, "execute", None)
    if not callable(execute):
        return None
    try:
        execute(text("SELECT 1"))
    except Exception as exc:
        rollback = getattr(db, "rollback", None)
        if callable(rollback):
            rollback()
        return f"{type(exc).__name__}: {exc}"
    return None


def _run_productivity(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    mode, start, end = _productivity_date_args(args, parser)
    business_code = str(args.business_code or DEFAULT_BUSINESS_CODE or "").strip() or DEFAULT_BUSINESS_CODE
    warm_cache = not bool(args.productivity_no_prebuild)
    db = SessionLocal()
    try:
        if warm_cache:
            db_error = _productivity_db_error(db)
            if db_error:
                print(
                    "Produktivitet kan inte bygga person_productivity_daily: "
                    "appdatabasen gar inte att ansluta. Starta databasen eller peka DATABASE_URL ratt. "
                    "Vill du bara hamta snapshotfiler, kor med --productivity-no-prebuild."
                )
                print(f"DB-fel: {db_error}")
                return 1
        if mode == "day" and start is not None:
            result = sync_productivity_snapshot(
                start,
                business_code=business_code,
                db=db,
                warm_cache=warm_cache,
            )
        elif mode == "range" and start is not None and end is not None:
            result = _sync_productivity_range(
                start,
                end,
                args=args,
                business_code=business_code,
                db=db,
                warm_cache=warm_cache,
            )
        else:
            result = prebuild_ready_productivity_days(
                business_code=business_code,
                db=db,
                force=bool(args.force_productivity_prebuild),
            )
    except ProductivitySyncError as exc:
        print(f"Produktivitet misslyckades: {exc}")
        return 1
    finally:
        db.close()

    status_text = str(result.get("status") or "ok")
    failed_status = status_text in {"error", "running", "not_configured"}

    if args.productivity_json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 1 if result.get("errors") or failed_status else 0

    dates = result.get("dates")
    if not dates and result.get("date"):
        dates = [result.get("date")]
    errors = result.get("errors") or []
    print(
        f"Produktivitet klar: status={status_text}, business={business_code}, "
        f"datum={len(dates or [])}, prebuild={'pa' if warm_cache else 'av'}"
        + (f", fel={len(errors)}" if errors else ".")
    )
    if result.get("source") == "api_snapshot_history_chunks":
        print("Produktivitet summering: " + _productivity_range_done_text(result, warm_cache=warm_cache) + ".")
    for err in errors:
        print("  FEL Produktivitet: " + json.dumps(err, ensure_ascii=False, default=str))
    return 1 if errors or failed_status else 0


class ProgressUI:
    """Trådsäker multi-rad progressrenderare (en rad per tenant/vy + en total-rad)."""

    def __init__(self, use_ansi: bool) -> None:
        self._lock = threading.Lock()
        self._rows: "OrderedDict[tuple[str, str], dict]" = OrderedDict()
        self._drawn = 0
        self._use_ansi = use_ansi
        self._last_plain = 0.0

    def on_event(self, ev: dict) -> None:
        key = (str(ev.get("tenant")), str(ev.get("view")))
        with self._lock:
            state = self._rows.get(key)
            if state is None:
                state = {"tenant": ev.get("tenant"), "view": ev.get("view"), "done": 0,
                         "total": 1, "source": "", "chunk": "", "rows": 0, "status": "väntar"}
                self._rows[key] = state
            kind = ev.get("type")
            if kind == "start":
                state["total"] = max(1, int(ev.get("target_span_days") or 1))
                state["done"] = int(ev.get("covered_before_days") or 0)
                if ev.get("skipped"):
                    state["status"] = "ej seedad"
                elif int(ev.get("todo_days") or 0) == 0:
                    state["status"] = "KLAR"
                else:
                    state["status"] = "seedar" if ev.get("will_seed") else "toppar"
            elif kind == "chunk":
                state["done"] = int(ev.get("done_days") or 0)
                state["total"] = max(1, int(ev.get("total_days") or 1))
                state["source"] = str(ev.get("source") or "")
                state["chunk"] = f"{ev.get('start')}..{ev.get('end')}"
                state["rows"] += int(ev.get("rows") or 0)
                state["status"] = "hämtar"
            elif kind == "done":
                if ev.get("fully_covered"):
                    state["done"] = state["total"]
                    state["status"] = "KLAR"
                elif ev.get("skipped"):
                    state["status"] = "ej seedad"
                else:
                    state["status"] = "delvis"
            self._render()

    def _line(self, state: dict) -> str:
        bar, pct = _bar(state["done"], state["total"])
        name = f"{state['tenant']}/{state['view']}"
        chunk = f"  {state['source']:5s} {state['chunk']}" if state["chunk"] else ""
        return (
            f"{name:34s} [{bar}] {pct:5.1f}%  {state['done']:>4}/{state['total']:<4}d  "
            f"{_fmt_int(state['rows']):>10} rader  {state['status']}{chunk}"
        )

    def _render(self) -> None:
        lines = [self._line(state) for state in self._rows.values()]
        done = sum(s["done"] for s in self._rows.values())
        total = sum(s["total"] for s in self._rows.values()) or 1
        bar, pct = _bar(done, total)
        lines.append(f"{'TOTALT':34s} [{bar}] {pct:5.1f}%  {done}/{total}d")

        if self._use_ansi:
            out = []
            if self._drawn:
                out.append(f"\033[{self._drawn}A")
            for line in lines:
                out.append("\r\033[K" + line + "\n")
            sys.stdout.write("".join(out))
            sys.stdout.flush()
            self._drawn = len(lines)
        else:
            now = time.time()
            if now - self._last_plain >= 2.0:
                self._last_plain = now
                print(lines[-1], flush=True)


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # åäö/progress oavsett konsol-encoding
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Fyll lokal DuckDB-cache och/eller Produktivitetens API-dagar.")
    parser.add_argument("--tenant", action="append", help="Tenant att seeda (kan upprepas / kommaseparerat). Default: alla aktiva.")
    parser.add_argument("--view", action="append", help="Cachevy att seeda (kan upprepas / kommaseparerat), t.ex. dblog_dispatch_pallet_log eller item_alias.")
    parser.add_argument("--workers", type=int, default=None, help="Parallella hämtningar (default ARCHIVE_CACHE_SEED_WORKERS).")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--archive-only", action="store_true", help="Hämta bara arkivvyerna, inte snapshotvyer.")
    group.add_argument("--snapshots-only", action="store_true", help="Hämta bara snapshotvyerna, t.ex. item_alias.")
    parser.add_argument("--status", action="store_true", help="Visa bara täckning + synk-logg och avsluta.")
    parser.add_argument("--with-productivity", action="store_true", help="Kor Produktivitetens API-dagar/prebuild efter DuckDB-cachen.")
    parser.add_argument("--productivity-only", action="store_true", help="Kor bara Produktivitetens API-dagar/prebuild, ingen DuckDB-arkivcache.")
    parser.add_argument("--business-code", default=DEFAULT_BUSINESS_CODE, help=f"Verksamhetskod for Produktivitet (default {DEFAULT_BUSINESS_CODE}).")
    parser.add_argument("--productivity-date", help="Hamta/prebygg ett Produktivitetsdatum (YYYY-MM-DD).")
    parser.add_argument("--productivity-start", help="Startdatum for Produktivitetsintervall (YYYY-MM-DD).")
    parser.add_argument("--productivity-end", help="Slutdatum for Produktivitetsintervall (YYYY-MM-DD). Default: igar nar start anges.")
    parser.add_argument("--productivity-chunk-days", type=int, default=_DEFAULT_PRODUCTIVITY_CHUNK_DAYS, help="Max dagar per produktivitets-API-hamtning (default 31).")
    parser.add_argument("--productivity-no-prebuild", action="store_true", help="Hamta produktivitetsfiler men bygg inte person_productivity_daily.")
    parser.add_argument("--productivity-prebuild-existing", action="store_true", help="Bygg bara befintliga produktivitetssnapshots, utan att hamta ett seed-intervall.")
    parser.add_argument("--force-productivity-prebuild", action="store_true", help="Bygg om historiska person_productivity_daily aven om dagens prebuild redan korts.")
    parser.add_argument("--productivity-json", action="store_true", help="Skriv full JSON for produktivitetsdelen.")
    args = parser.parse_args(argv)

    if args.productivity_only and (args.archive_only or args.snapshots_only):
        parser.error("--productivity-only kan inte kombineras med --archive-only/--snapshots-only.")

    run_archive = not bool(args.productivity_only)
    run_productivity = bool(args.with_productivity or args.productivity_only)

    if args.status and run_productivity:
        parser.error("--status visar bara arkivcache-status och kan inte kombineras med produktivitetskoring.")

    if run_archive and not store.is_enabled():
        print("ARCHIVE_CACHE_ENABLED är av. Sätt ARCHIVE_CACHE_ENABLED=1 i app/.env och kör igen.")
        return 1

    tenants: list[str] | None = None
    if args.tenant:
        tenants = []
        for item in args.tenant:
            tenants.extend(part.strip() for part in item.split(",") if part.strip())

    views: list[str] | None = None
    if args.view:
        views = []
        for item in args.view:
            views.extend(part.strip() for part in item.split(",") if part.strip())
        invalid = [view for view in views if view not in sync.SYNC_CACHE_VIEWS]
        if invalid:
            print(
                "Okänd cachevy: "
                + ", ".join(invalid)
                + ". Tillåtna: "
                + ", ".join(sync.SYNC_CACHE_VIEWS)
            )
            return 2
    elif args.archive_only:
        views = list(sync.SYNC_ARCHIVE_VIEWS)
    elif args.snapshots_only:
        views = list(sync.SYNC_SNAPSHOT_VIEWS)

    if args.status:
        print(json.dumps(sync.coverage_report(tenant=tenants[0] if tenants else None), ensure_ascii=False, indent=2, default=str))
        return 0

    if not run_archive:
        return _run_productivity(args, parser)

    ui = ProgressUI(use_ansi=bool(getattr(sys.stdout, "isatty", lambda: False)()))
    print("Fyller lokal DuckDB-cache för arkiv och snapshots — parallellt, chunkat, återupptagningsbart.\n", flush=True)
    started = time.time()
    try:
        result = sync.seed_all(tenants, max_workers=args.workers, progress=ui.on_event, view_ids=views)
    except KeyboardInterrupt:
        print("\nAvbruten. Redan hämtade chunkar är sparade – kör igen för att fortsätta.")
        return 130
    elapsed = time.time() - started

    if result.get("status") == "running":
        print("En seed/synk pågår redan i denna process.")
        return 1

    results = result.get("results", [])
    errors = [r for r in results if r.get("error")]
    covered = sum(1 for r in results if r.get("fully_covered"))
    print(
        f"\nKlar på {elapsed:,.0f}s. {covered}/{len(results)} vyer fullständigt hämtade"
        + (f", {len(errors)} fel:" if errors else ".")
    )
    for err in errors:
        print(f"  FEL {err.get('tenant')}/{err.get('view')}: {err.get('error')}")
    empty_stops = [r for r in results if r.get("empty_stopped")]
    for item in empty_stops:
        days = int(item.get("empty_stop_days") or 0)
        print(
            f"  INFO {item.get('tenant')}/{item.get('view')}: "
            f"stoppade bakatseed efter {days} tomma dagar; aldre intervall markerat som klart/tomt."
        )
    exit_code = 1 if errors else 0
    if run_productivity:
        exit_code = max(exit_code, _run_productivity(args, parser))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

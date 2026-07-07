from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

from .config import settings
from .public_dpak_service import (
    dataset_status,
    import_from_csv_directory,
    load_support_csvs,
    parse_settings_date,
    public_dpak_business_code,
    rebuild_public_dpak_facts,
    sync_public_dpak_pick_chunks,
)


def _parse_date(value: str | None, fallback: date) -> date:
    if not value:
        return fallback
    return date.fromisoformat(value[:10])


def _support_dir(value: Path | None) -> Path:
    if value is not None:
        return value
    configured = settings.PUBLIC_DPAK_SUPPORT_DIR.strip()
    if configured:
        return Path(configured)
    raise SystemExit("Ange --support-dir eller sätt PUBLIC_DPAK_SUPPORT_DIR i lokal env.")


def _normalize_legacy_args(argv: list[str]) -> list[str]:
    normalized = list(argv)
    if "--status" in normalized:
        normalized.remove("--status")
        if not normalized or normalized[0] not in {"api", "csv", "rebuild", "status"}:
            normalized.insert(0, "status")
    if "--from-api" in normalized:
        normalized.remove("--from-api")
        if not normalized or normalized[0] not in {"api", "csv", "rebuild", "status"}:
            normalized.insert(0, "api")
    return normalized


def _coerce_env_value(current: Any, value: str) -> Any:
    if isinstance(current, bool):
        return value.strip().lower() in {"1", "true", "yes", "on", "ja"}
    if isinstance(current, int) and not isinstance(current, bool):
        try:
            return int(value)
        except ValueError:
            return current
    if isinstance(current, float):
        try:
            return float(value)
        except ValueError:
            return current
    return value


def _load_env_file(path: Path | None) -> None:
    if path is None:
        return
    if not path.is_file():
        raise SystemExit(f"Env-filen finns inte: {path}")
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        os.environ[key] = value
        if hasattr(settings, key):
            setattr(settings, key, _coerce_env_value(getattr(settings, key), value))


def _fmt_int(value: Any) -> str:
    try:
        return f"{int(value):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "0"


def _fmt_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "--:--"
    seconds = int(seconds)
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"


class DpakProgressBar:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.started_at = time.perf_counter()
        self.total = 0
        self.done = 0
        self.rows = 0
        self.current = ""
        self.finished_line = True

    def __call__(self, event: dict[str, Any] | str) -> None:
        if isinstance(event, str):
            self._line(event)
            return
        event_type = str(event.get("type") or "")
        if event_type == "start":
            self.total = int(event.get("total_chunks") or 0)
            self._line(
                "Startar D-pak-sync: "
                f"{self.total} chunks, {', '.join(event.get('views') or [])}, "
                f"{event.get('start')}..{event.get('end')}"
            )
            self._render()
            return
        if event_type == "chunk_start":
            self.current = f"{event.get('view')} {event.get('start')}..{event.get('end')}"
            self._render()
            return
        if event_type in {"chunk_done", "skip"}:
            self.done = int(event.get("index") or self.done)
            self.total = int(event.get("total_chunks") or self.total)
            self.rows = int(event.get("rows_imported") or self.rows)
            label = "skip" if event_type == "skip" else "klar"
            self.current = (
                f"{label}: {event.get('view')} {event.get('start')}..{event.get('end')} "
                f"({_fmt_int(event.get('rows'))} rader)"
            )
            self._render()
            return
        if event_type == "db_insert":
            inserted = _fmt_int(event.get("inserted"))
            rows = _fmt_int(event.get("rows"))
            self.current = f"skriver till Postgres {inserted}/{rows} rader"
            self._render()
            return
        if event_type == "db_retry":
            self.current = (
                f"tappar DB-anslutning, testar igen "
                f"{event.get('attempt')}/{event.get('attempts')}"
            )
            self._render()
            return
        if event_type == "rebuild_start":
            self.done = self.total
            self.rows = int(event.get("rows_imported") or self.rows)
            self.current = "bygger faktatabeller i Postgres"
            self._render()
            self._newline()
            return
        if event_type == "rebuild_done":
            self.rows = int(event.get("pick_rows") or self.rows)
            self.current = (
                f"faktatabeller klara: {_fmt_int(event.get('order_article_rows'))} order/artikel, "
                f"{_fmt_int(event.get('order_supplier_rows'))} order/leverantor"
            )
            self._render(force_percent=100.0)
            self._newline()
            return

    def _line(self, text: str) -> None:
        self._newline()
        print(text, flush=True)

    def _newline(self) -> None:
        if self.enabled and not self.finished_line:
            print()
            self.finished_line = True

    def _render(self, force_percent: float | None = None) -> None:
        elapsed = max(0.001, time.perf_counter() - self.started_at)
        percent = force_percent if force_percent is not None else ((self.done / self.total * 100) if self.total else 0)
        eta = None
        if self.done > 0 and self.total and self.done < self.total:
            eta = (elapsed / self.done) * (self.total - self.done)
        filled = int(max(0, min(1, percent / 100)) * 28)
        bar = "#" * filled + "-" * (28 - filled)
        text = (
            f"\r[{bar}] {percent:5.1f}% "
            f"{self.done}/{self.total or '?'} chunks "
            f"rader {_fmt_int(self.rows)} "
            f"tid {_fmt_duration(elapsed)} eta {_fmt_duration(eta)} "
            f"{self.current[:70]}"
        )
        if self.enabled:
            print(text.ljust(150), end="", flush=True)
            self.finished_line = False
        else:
            print(text.strip(), flush=True)


def _print_status(status: dict) -> None:
    print(f"business: {status.get('business_code')}")
    print(f"status: {status.get('status')} ready={status.get('ready')}")
    print(f"coverage: {status.get('coverage_start') or '-'}..{status.get('coverage_end') or '-'}")
    print(f"pick rows: {status.get('pick_rows') or 0}")
    print(f"order/article facts: {status.get('order_article_rows') or 0}")
    print(f"order/supplier box facts: {status.get('order_supplier_rows') or 0}")
    chunks = status.get("chunks") or {}
    if chunks:
        print("chunks: " + ", ".join(f"{key}={value}" for key, value in sorted(chunks.items())))


def _print_build(prefix: str, build) -> None:
    print(prefix)
    print(f"business: {build.business_code}")
    print(f"pick rows: {build.pick_rows}")
    print(f"order/article facts: {build.order_article_rows}")
    print(f"order/supplier box facts: {build.order_supplier_rows}")
    print(
        "coverage: "
        f"{build.coverage_start.isoformat() if build.coverage_start else '-'}.."
        f"{build.coverage_end.isoformat() if build.coverage_end else '-'}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync and rebuild the public D-pak chat dataset.")
    business_help = "Business code. Defaults to PUBLIC_DPAK_DEFAULT_BUSINESS_CODE."
    parser.add_argument("--business-code", default=None, help=business_help)
    parser.add_argument("--env-file", type=Path, default=None, help="Load DATA_SOURCE_* values from a local env file.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    api_parser = subparsers.add_parser("api", help="Fetch pick logs from the external API in persistent chunks.")
    api_parser.add_argument("--business-code", default=argparse.SUPPRESS, help=business_help)
    api_parser.add_argument("--env-file", type=Path, default=argparse.SUPPRESS, help="Load DATA_SOURCE_* values from a local env file.")
    api_parser.add_argument("--support-dir", type=Path, help="Directory containing item_alias and item_attribute CSVs.")
    api_parser.add_argument("--start", default=None, help="Inclusive start date, YYYY-MM-DD.")
    api_parser.add_argument("--end", default=None, help="Inclusive end date, YYYY-MM-DD.")
    api_parser.add_argument("--chunk-days", type=int, default=None, help="Days per API chunk.")
    api_parser.add_argument("--archive-duckdb", type=Path, default=None, help="DuckDB archive cache for dblog pick rows.")
    api_parser.add_argument("--force", action="store_true", help="Re-fetch chunks even if they are already complete.")
    api_parser.add_argument("--no-progress", action="store_true", help="Print plain progress lines instead of a progress bar.")

    csv_parser = subparsers.add_parser("csv", help="Replace the dataset from local CSV exports.")
    csv_parser.add_argument("--business-code", default=argparse.SUPPRESS, help=business_help)
    csv_parser.add_argument("--csv-dir", required=True, type=Path, help="Directory containing pick, item_alias and item_attribute CSVs.")

    rebuild_parser = subparsers.add_parser("rebuild", help="Rebuild fact tables from already stored pick rows.")
    rebuild_parser.add_argument("--business-code", default=argparse.SUPPRESS, help=business_help)
    rebuild_parser.add_argument("--support-dir", type=Path, help="Directory containing item_alias and item_attribute CSVs.")

    status_parser = subparsers.add_parser("status", help="Print public D-pak dataset status.")
    status_parser.add_argument("--business-code", default=argparse.SUPPRESS, help=business_help)
    status_parser.add_argument("--env-file", type=Path, default=argparse.SUPPRESS, help="Load values from a local env file.")
    return parser


def main() -> None:
    args = build_parser().parse_args(_normalize_legacy_args(sys.argv[1:]))
    _load_env_file(getattr(args, "env_file", None))
    from .database import SessionLocal

    business_code = public_dpak_business_code(args.business_code)
    db = SessionLocal()
    try:
        if args.command == "status":
            _print_status(dataset_status(db, business_code))
            return

        if args.command == "csv":
            build = import_from_csv_directory(db, args.csv_dir, business_code=business_code)
            db.commit()
            _print_build("CSV import complete.", build)
            return

        if args.command == "rebuild":
            support_dir = _support_dir(args.support_dir)
            alias_rows, attribute_rows = load_support_csvs(support_dir)
            build = rebuild_public_dpak_facts(
                db,
                business_code=business_code,
                alias_rows=alias_rows,
                attribute_rows=attribute_rows,
                source_summary={"mode": "rebuild_from_stored_pick_rows", "support_directory": str(support_dir)},
            )
            db.commit()
            _print_build("Fact rebuild complete.", build)
            return

        if args.command == "api":
            if args.archive_duckdb is not None:
                settings.PUBLIC_DPAK_ARCHIVE_DUCKDB = str(args.archive_duckdb)
            start = _parse_date(
                args.start,
                parse_settings_date(settings.PUBLIC_DPAK_START_DATE, date(2025, 7, 1)),
            )
            end = _parse_date(
                args.end,
                parse_settings_date(settings.PUBLIC_DPAK_END_DATE, date(2026, 7, 1)),
            )
            result = sync_public_dpak_pick_chunks(
                db,
                _support_dir(args.support_dir),
                business_code=business_code,
                start=start,
                end=end,
                chunk_days=args.chunk_days,
                force=args.force,
                progress=DpakProgressBar(enabled=not bool(getattr(args, "no_progress", False))),
            )
            _print_build("API sync complete.", result.build)
            print(f"chunks fetched: {result.chunks_fetched}")
            print(f"chunks skipped: {result.chunks_skipped}")
            print(f"rows imported this run: {result.rows_imported}")
            return
    except KeyboardInterrupt:
        db.rollback()
        print("\nAvbruten. Klara chunks behalls; nasta korning fortsatter pa ofardiga chunks.")
        raise SystemExit(130)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .config import settings
from .database import SessionLocal
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
    if "--from-api" in normalized:
        normalized.remove("--from-api")
        if not normalized or normalized[0] not in {"api", "csv", "rebuild", "status"}:
            normalized.insert(0, "api")
    return normalized


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
    subparsers = parser.add_subparsers(dest="command", required=True)

    api_parser = subparsers.add_parser("api", help="Fetch pick logs from the external API in persistent chunks.")
    api_parser.add_argument("--business-code", default=argparse.SUPPRESS, help=business_help)
    api_parser.add_argument("--support-dir", type=Path, help="Directory containing item_alias and item_attribute CSVs.")
    api_parser.add_argument("--start", default=None, help="Inclusive start date, YYYY-MM-DD.")
    api_parser.add_argument("--end", default=None, help="Inclusive end date, YYYY-MM-DD.")
    api_parser.add_argument("--chunk-days", type=int, default=None, help="Days per API chunk.")
    api_parser.add_argument("--force", action="store_true", help="Re-fetch chunks even if they are already complete.")

    csv_parser = subparsers.add_parser("csv", help="Replace the dataset from local CSV exports.")
    csv_parser.add_argument("--business-code", default=argparse.SUPPRESS, help=business_help)
    csv_parser.add_argument("--csv-dir", required=True, type=Path, help="Directory containing pick, item_alias and item_attribute CSVs.")

    rebuild_parser = subparsers.add_parser("rebuild", help="Rebuild fact tables from already stored pick rows.")
    rebuild_parser.add_argument("--business-code", default=argparse.SUPPRESS, help=business_help)
    rebuild_parser.add_argument("--support-dir", type=Path, help="Directory containing item_alias and item_attribute CSVs.")

    status_parser = subparsers.add_parser("status", help="Print public D-pak dataset status.")
    status_parser.add_argument("--business-code", default=argparse.SUPPRESS, help=business_help)
    return parser


def main() -> None:
    args = build_parser().parse_args(_normalize_legacy_args(sys.argv[1:]))
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
                progress=print,
            )
            _print_build("API sync complete.", result.build)
            print(f"chunks fetched: {result.chunks_fetched}")
            print(f"chunks skipped: {result.chunks_skipped}")
            print(f"rows imported this run: {result.rows_imported}")
            return
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

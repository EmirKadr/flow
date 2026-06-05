"""Run queued Meta audio analyses outside the web request path."""
from __future__ import annotations

import argparse
import logging
import time

from app.backend.meta_analysis_service import run_queued_meta_analysis_once


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process queued Meta analysis jobs.")
    parser.add_argument("--limit", type=int, default=1, help="Max jobs per polling iteration.")
    parser.add_argument("--idle-sleep", type=float, default=30.0, help="Seconds to sleep when no job was processed.")
    parser.add_argument("--loop", action="store_true", help="Keep polling until the process is stopped.")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = parse_args()
    while True:
        processed = run_queued_meta_analysis_once(limit=args.limit)
        logging.info("Meta analysis worker processed %s queued job(s).", processed)
        if not args.loop:
            return
        if processed <= 0:
            time.sleep(max(1.0, float(args.idle_sleep)))


if __name__ == "__main__":
    main()

"""Prepare the local preview database before starting the dev server."""
from __future__ import annotations

import os

from .bootstrap_local import main as bootstrap_local
from .sync_live_to_local import LocalSyncError, sync_from_env


def sync_live_on_start_enabled() -> bool:
    return os.getenv("FLOW_SYNC_LIVE_ON_START", "").strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    synced = False
    if sync_live_on_start_enabled():
        try:
            synced = sync_from_env()
        except LocalSyncError as exc:
            raise SystemExit(str(exc)) from exc

    if synced:
        print("Synkar lokal schema/backfill efter live-kopia.")
    else:
        print("Snabb lokal start. Skapar/synkar lokal seed-databas utan live-kopia.")
    bootstrap_local()


if __name__ == "__main__":
    main()

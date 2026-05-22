"""Prepare the local preview database before starting the dev server."""
from __future__ import annotations

from .bootstrap_local import main as bootstrap_local
from .sync_live_to_local import LocalSyncError, sync_from_env


def main() -> None:
    synced = False
    try:
        synced = sync_from_env()
    except LocalSyncError as exc:
        raise SystemExit(str(exc)) from exc

    if synced:
        print("Synkar lokal schema/backfill efter live-kopia.")
    else:
        print("Ingen LIVE_DATABASE_URL satt. Skapar/synkar lokal seed-databas.")
    bootstrap_local()


if __name__ == "__main__":
    main()

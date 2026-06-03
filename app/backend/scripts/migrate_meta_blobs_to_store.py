"""Engångsmigrering: flytta befintliga meta-video/bild-bytea till MediaStore.

Läser varje rads ``data``-kolumn **chunkvis** via Postgres ``substring(...)`` så
att en hel blob aldrig hämtas till minnet, skriver den strömmande till
MediaStore och nollar sedan ``data`` (sätter ``storage_key``/``storage_backend``).

Kör i en låg-trafikperiod, t.ex:

    python -m backend.scripts.migrate_meta_blobs_to_store

Efter att alla rader har ``storage_key`` satt och ``data IS NULL`` kan en
separat Alembic-migration droppa ``data``-kolumnen och en ``VACUUM`` frigöra
utrymmet.
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import text

from ..database import SessionLocal
from ..media_store import get_media_store

logger = logging.getLogger(__name__)

CHUNK = 8 * 1024 * 1024


def _suffix_for(stored_filename: str | None, original_filename: str | None) -> str:
    return Path(stored_filename or original_filename or "media").suffix.lower()


def migrate_one(db, store, upload_id: int) -> bool:
    size = db.execute(
        text("SELECT length(data) FROM meta_media_uploads WHERE id = :id"),
        {"id": upload_id},
    ).scalar()
    if not size:
        return False
    meta = db.execute(
        text("SELECT stored_filename, original_filename FROM meta_media_uploads WHERE id = :id"),
        {"id": upload_id},
    ).one()
    writer = store.create_writer(suffix=_suffix_for(meta[0], meta[1]))
    try:
        offset = 1  # Postgres substring är 1-indexerad
        while offset <= size:
            chunk = db.execute(
                text("SELECT substring(data FROM :o FOR :n) FROM meta_media_uploads WHERE id = :id"),
                {"o": offset, "n": CHUNK, "id": upload_id},
            ).scalar()
            if not chunk:
                break
            buf = bytes(chunk)
            writer.write(buf)
            offset += len(buf)
        stored = writer.commit()
    except BaseException:
        writer.abort()
        raise
    db.execute(
        text(
            "UPDATE meta_media_uploads "
            "SET storage_key = :key, storage_backend = :backend, data = NULL "
            "WHERE id = :id"
        ),
        {"key": stored.key, "backend": store.backend, "id": upload_id},
    )
    db.commit()
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    store = get_media_store()
    migrated = 0
    with SessionLocal() as db:
        ids = [
            row[0]
            for row in db.execute(
                text(
                    "SELECT id FROM meta_media_uploads "
                    "WHERE data IS NOT NULL AND storage_key IS NULL ORDER BY id"
                )
            ).all()
        ]
        logger.info("Hittade %s rader att migrera.", len(ids))
        for upload_id in ids:
            try:
                if migrate_one(db, store, upload_id):
                    migrated += 1
                    logger.info("Migrerade upload %s (%s/%s).", upload_id, migrated, len(ids))
            except Exception:
                db.rollback()
                logger.exception("Misslyckades migrera upload %s.", upload_id)
    logger.info("Klart. Migrerade %s rader. Kör VACUUM för att frigöra utrymme.", migrated)


if __name__ == "__main__":
    main()

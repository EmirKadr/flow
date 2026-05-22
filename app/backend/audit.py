"""Helper för att skriva audit_log-rader."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from .models import AuditLog


def log(
    db: Session,
    entity_type: str,
    entity_id: int,
    action: str,
    old_value: dict[str, Any] | None,
    new_value: dict[str, Any] | None,
    user_id: int | None,
) -> None:
    db.add(
        AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            old_value=old_value,
            new_value=new_value,
            user_id=user_id,
        )
    )


def log_and_commit(
    db: Session,
    entity_type: str,
    entity_id: int,
    action: str,
    old_value: dict[str, Any] | None,
    new_value: dict[str, Any] | None,
    user_id: int | None,
    *,
    logger: logging.Logger | None = None,
    context: str = "audit event",
) -> bool:
    """Write a standalone audit event without breaking the user flow on failure."""
    try:
        log(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            old_value=old_value,
            new_value=new_value,
            user_id=user_id,
        )
        db.commit()
        return True
    except Exception:
        rollback = getattr(db, "rollback", None)
        if callable(rollback):
            rollback()
        if logger:
            logger.exception("Could not write %s", context)
        return False

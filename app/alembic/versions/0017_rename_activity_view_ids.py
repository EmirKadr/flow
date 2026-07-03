"""rename activity view ids

Revision ID: 0017_rename_activity_view_ids
Revises: 0016_keep_persons_active
Create Date: 2026-05-21
"""
from __future__ import annotations

import json
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "0017_rename_activity_view_ids"
down_revision: Union[str, None] = "0016_keep_persons_active"
branch_labels: Union[str, tuple[str, ...], None] = None
depends_on: Union[str, tuple[str, ...], None] = None


ALIASES = {
    "stallen": "activities",
    "stallenImport": "activityImport",
}


def _map_id(value: object, *, reverse: bool = False) -> object:
    if not isinstance(value, str):
        return value
    mapping = {v: k for k, v in ALIASES.items()} if reverse else ALIASES
    return mapping.get(value, value)


def _normalize_sidebar(value: object, *, reverse: bool = False) -> object:
    if not isinstance(value, list):
        return value
    normalized = []
    for item in value:
        if not isinstance(item, dict):
            continue
        next_item = dict(item)
        next_item["id"] = _map_id(next_item.get("id"), reverse=reverse)
        if next_item.get("parent_id"):
            next_item["parent_id"] = _map_id(next_item.get("parent_id"), reverse=reverse)
        normalized.append(next_item)
    return normalized


def _normalize_role_access(value: object, *, reverse: bool = False) -> object:
    if not isinstance(value, dict):
        return value
    normalized: dict[str, dict[str, object]] = {}
    for role, views in value.items():
        if not isinstance(views, dict):
            continue
        role_views: dict[str, object] = {}
        for view_id, level in views.items():
            role_views[str(_map_id(view_id, reverse=reverse))] = level
        normalized[str(role)] = role_views
    return normalized


def _update_json_setting(key: str, normalizer, *, reverse: bool = False) -> None:
    connection = op.get_bind()
    # "key" ar reserverat ord i T-SQL - citera sa fragan gar pa alla dialekter.
    row = connection.execute(sa.text('SELECT value FROM app_settings WHERE "key" = :key'), {"key": key}).first()
    if row is None:
        return
    try:
        before = json.loads(row.value)
    except (TypeError, json.JSONDecodeError):
        return
    after = normalizer(before, reverse=reverse)
    if after == before:
        return
    connection.execute(
        sa.text('UPDATE app_settings SET value = :value WHERE "key" = :key'),
        {"key": key, "value": json.dumps(after, ensure_ascii=False, separators=(",", ":"))},
    )


def upgrade() -> None:
    _update_json_setting("sidebar_layout", _normalize_sidebar)
    _update_json_setting("role_view_access", _normalize_role_access)


def downgrade() -> None:
    _update_json_setting("sidebar_layout", _normalize_sidebar, reverse=True)
    _update_json_setting("role_view_access", _normalize_role_access, reverse=True)

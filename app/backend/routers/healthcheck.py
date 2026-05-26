from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db, require_super_user
from ..healthcheck_service import clean_text, run_healthcheck
from ..models import User, UserWaitMetric
from ..schemas import WaitMetricBatchIn


router = APIRouter(prefix="/api/healthcheck", tags=["healthcheck"])


PERIODS = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


def period_start(period: str) -> datetime | None:
    if period == "all":
        return None
    return datetime.now(timezone.utc) - PERIODS.get(period, PERIODS["24h"])


def percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil((pct / 100) * len(ordered)) - 1))
    return int(ordered[index])


def metric_payload(row: UserWaitMetric) -> dict[str, Any]:
    return {
        "id": row.id,
        "created_at": row.created_at,
        "event_type": row.event_type,
        "view_id": row.view_id,
        "target": row.target,
        "duration_ms": row.duration_ms,
        "status": row.status,
        "detail": row.detail or {},
        "user_id": row.user_id,
        "business_id": row.business_id,
    }


def summarize_group(rows: list[UserWaitMetric], *, key_fn) -> list[dict[str, Any]]:
    buckets: dict[str, list[UserWaitMetric]] = {}
    for row in rows:
        key = clean_text(key_fn(row), limit=180) or "-"
        buckets.setdefault(key, []).append(row)
    summary: list[dict[str, Any]] = []
    for key, items in buckets.items():
        durations = [int(item.duration_ms or 0) for item in items]
        summary.append({
            "key": key,
            "count": len(items),
            "avg_ms": round(sum(durations) / len(durations), 1) if durations else 0,
            "p50_ms": percentile(durations, 50),
            "p95_ms": percentile(durations, 95),
            "max_ms": max(durations) if durations else 0,
            "error_count": sum(1 for item in items if item.status != "ok"),
        })
    return sorted(summary, key=lambda item: (item["p95_ms"], item["avg_ms"], item["count"]), reverse=True)


@router.get("")
def healthcheck_report(
    include_render: bool = Query(True),
    db: Session = Depends(get_db),
    _: User = Depends(require_super_user),
) -> dict[str, Any]:
    return run_healthcheck(db=db, include_render=include_render)


@router.post("/wait-metrics", status_code=status.HTTP_204_NO_CONTENT)
def record_wait_metrics(
    payload: WaitMetricBatchIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    rows = []
    for item in payload.items[:100]:
        rows.append(
            UserWaitMetric(
                business_id=user.business_id,
                user_id=user.id,
                event_type=clean_text(item.event_type, limit=80) or "unknown",
                view_id=clean_text(item.view_id, limit=80),
                target=clean_text(item.target, limit=160),
                duration_ms=int(item.duration_ms),
                status=(clean_text(item.status, limit=20) or "ok").lower(),
                detail=item.detail if isinstance(item.detail, dict) else None,
            )
        )
    if rows:
        db.add_all(rows)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/wait-metrics/summary")
def wait_metrics_summary(
    period: str = Query("24h"),
    limit: int = Query(5000, ge=100, le=20000),
    user_id: int | None = Query(None),
    q: str | None = Query(None, max_length=120),
    db: Session = Depends(get_db),
    _: User = Depends(require_super_user),
) -> dict[str, Any]:
    if not isinstance(user_id, int):
        user_id = None
    if not isinstance(q, str):
        q = None
    since = period_start(period)
    query = select(UserWaitMetric).order_by(UserWaitMetric.created_at.desc()).limit(limit)
    if since is not None:
        query = query.where(UserWaitMetric.created_at >= since)
    if user_id is not None:
        query = query.where(UserWaitMetric.user_id == user_id)
    query_text = clean_text(q, limit=120)
    if query_text:
        pattern = f"%{query_text}%"
        query = query.where(or_(
            UserWaitMetric.event_type.ilike(pattern),
            UserWaitMetric.view_id.ilike(pattern),
            UserWaitMetric.target.ilike(pattern),
        ))
    rows = list(
        db.execute(query).scalars()
    )
    durations = [int(row.duration_ms or 0) for row in rows]
    slow = sorted(rows, key=lambda row: int(row.duration_ms or 0), reverse=True)[:20]
    return {
        "period": period,
        "since": since.isoformat() if since is not None else None,
        "count": len(rows),
        "avg_ms": round(sum(durations) / len(durations), 1) if durations else 0,
        "p50_ms": percentile(durations, 50),
        "p95_ms": percentile(durations, 95),
        "max_ms": max(durations) if durations else 0,
        "by_view": summarize_group(rows, key_fn=lambda row: row.view_id or row.target or row.event_type)[:20],
        "by_target": summarize_group(rows, key_fn=lambda row: row.target or row.view_id or row.event_type)[:30],
        "by_event": summarize_group(rows, key_fn=lambda row: row.event_type)[:20],
        "slow_events": [metric_payload(row) for row in slow],
        "analysis": wait_analysis(rows),
    }


def wait_analysis(rows: list[UserWaitMetric]) -> list[dict[str, str]]:
    if not rows:
        return [{"severity": "info", "message": "Ingen vantedata finns for vald period annu."}]
    durations = [int(row.duration_ms or 0) for row in rows]
    p95 = percentile(durations, 95)
    analysis: list[dict[str, str]] = []
    if p95 > 3000:
        analysis.append({"severity": "warn", "message": f"P95 ar {p95} ms. Anvandare vantar ofta mer an 3 sekunder."})
    if p95 > 6000:
        analysis.append({"severity": "error", "message": f"P95 ar {p95} ms. Undersok cache, API och databas for de tyngsta stegen."})
    long_tasks = [row for row in rows if row.event_type == "client_long_task"]
    if long_tasks:
        worst_long_task = max(int(row.duration_ms or 0) for row in long_tasks)
        severity = "warn" if worst_long_task >= 250 else "info"
        analysis.append({"severity": severity, "message": f"Klientens huvudtrad hade {len(long_tasks)} langa tasks, max {worst_long_task} ms."})
    worst_target = summarize_group(rows, key_fn=lambda row: row.target or row.view_id or row.event_type)[:1]
    if worst_target:
        item = worst_target[0]
        analysis.append({"severity": "info", "message": f"Tyngsta steg: {item['key']} med p95 {item['p95_ms']} ms ({item['count']} mätningar)."})
    if not analysis:
        analysis.append({"severity": "ok", "message": "Vantetiderna ser friska ut i vald period."})
    return analysis

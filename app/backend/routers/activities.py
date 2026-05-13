from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db, require_admin
from ..models import Activity
from ..schemas import ActivityCreate, ActivityOut, ActivityUpdate

router = APIRouter(prefix="/api/activities", tags=["activities"])


def _validate_summary_activity(
    db: Session,
    *,
    activity_id: int | None,
    summary_activity_id: int | None,
) -> int | None:
    if summary_activity_id is None:
        return None
    if activity_id is not None and summary_activity_id == activity_id:
        return None

    target = db.get(Activity, summary_activity_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Summeringsaktivitet hittades inte")

    if activity_id is None:
        return summary_activity_id

    visited = {activity_id}
    current = target
    while current.summary_activity_id is not None:
        if current.summary_activity_id in visited:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Summeringskoppling skapar en loop")
        visited.add(current.id)
        current = db.get(Activity, current.summary_activity_id)
        if current is None:
            break

    return summary_activity_id


@router.get("", response_model=list[ActivityOut])
def list_activities(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
) -> list[Activity]:
    q = db.query(Activity)
    if not include_inactive:
        q = q.filter(Activity.is_active.is_(True))
    return q.order_by(Activity.sort_order, Activity.label).all()


@router.post("", response_model=ActivityOut, status_code=status.HTTP_201_CREATED)
def create_activity(
    payload: ActivityCreate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
) -> Activity:
    if db.query(Activity).filter_by(code=payload.code).first():
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Aktivitet med samma kod finns redan")
    data = payload.model_dump()
    data["summary_activity_id"] = _validate_summary_activity(
        db,
        activity_id=None,
        summary_activity_id=payload.summary_activity_id,
    )
    activity = Activity(**data)
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity


@router.put("/{activity_id}", response_model=ActivityOut)
def update_activity(
    activity_id: int,
    payload: ActivityUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
) -> Activity:
    activity = db.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Aktivitet hittades inte")
    if payload.code is not None:
        existing = db.query(Activity).filter(Activity.code == payload.code, Activity.id != activity_id).first()
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Aktivitet med samma kod finns redan")
    data = payload.model_dump(exclude_unset=True)
    if "summary_activity_id" in data:
        data["summary_activity_id"] = _validate_summary_activity(
            db,
            activity_id=activity_id,
            summary_activity_id=payload.summary_activity_id,
        )
    for key, value in data.items():
        setattr(activity, key, value)
    db.commit()
    db.refresh(activity)
    return activity


@router.delete("/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_activity(
    activity_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
) -> None:
    activity = db.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Aktivitet hittades inte")
    activity.is_active = False
    db.commit()

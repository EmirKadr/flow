from .schedule_shared import *

router = APIRouter()

@router.get("/summary", response_model=list[SummaryRow])
def get_summary(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    weekday: int = Query(..., ge=1, le=7),
    area_id: int | None = Query(None),
    business_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "view")),
) -> list[SummaryRow]:
    selected_date = _schedule_date(year, week, weekday)
    persons, scoped_business_id = _visible_schedule_persons(
        db,
        user,
        area_id,
        business_id,
        year=year,
        week=week,
        weekdays=[weekday],
    )
    person_ids = [person.id for person in persons]
    home_area_person_ids = {
        person.id
        for person in persons
        if area_id is None or person.home_area_id == area_id
    }

    activity_query = db.query(Activity)
    area_query = db.query(Area)
    if scoped_business_id is not None:
        activity_query = activity_query.filter(Activity.business_id == scoped_business_id)
        area_query = area_query.filter(Area.business_id == scoped_business_id)
    activity_rows = activity_query.all()
    activities = {activity.id: activity for activity in activity_rows}
    home_activity_for = build_home_activity_resolver(activity_rows, area_query.all())
    minutes_by_activity: dict[int, int] = {}

    if person_ids:
        explicit_rows = db.execute(
            select(
                ScheduleCell.person_id,
                ScheduleCell.hour,
                ScheduleCell.activity_id,
                ScheduleCell.empty_override,
                ScheduleCell.minute_start,
                ScheduleCell.minute_end,
            ).where(
                ScheduleCell.year == year,
                ScheduleCell.week == week,
                ScheduleCell.weekday == weekday,
                ScheduleCell.person_id.in_(person_ids),
            )
        ).all()

        covered_minutes: dict[tuple[int, int], int] = {}
        for row in explicit_rows:
            duration = int(row.minute_end - row.minute_start)
            if row.activity_id is not None:
                activity = activities.get(row.activity_id)
                count_for_area = (
                    area_id is None
                    or row.person_id in home_area_person_ids
                    or (activity is not None and activity.area_id == area_id)
                )
                if count_for_area:
                    minutes_by_activity[row.activity_id] = (
                        minutes_by_activity.get(row.activity_id, 0) + duration
                    )
            if row.activity_id is not None or row.empty_override:
                key = (row.person_id, row.hour)
                covered_minutes[key] = min(60, covered_minutes.get(key, 0) + duration)

        template_hours_map = get_template_hours_map_for_dates(db, person_ids, [selected_date])
        for person in persons:
            if area_id is not None and person.id not in home_area_person_ids:
                continue
            template_hours = template_hours_map.get((person.id, selected_date))
            home_activity_id = home_activity_for(person)
            if template_hours is None or home_activity_id is None:
                continue
            for hour in template_hours:
                remaining = 60 - covered_minutes.get((person.id, hour), 0)
                if remaining <= 0:
                    continue
                minutes_by_activity[home_activity_id] = (
                    minutes_by_activity.get(home_activity_id, 0) + remaining
                )

    def resolve_summary_target(activity_id: int) -> Activity | None:
        current = activities.get(activity_id)
        visited: set[int] = set()
        while current and current.summary_activity_id is not None and current.id not in visited:
            visited.add(current.id)
            current = activities.get(current.summary_activity_id)
        return current

    grouped: dict[int, dict] = {}
    for activity_id, minutes in minutes_by_activity.items():
        target = resolve_summary_target(activity_id) or activities.get(activity_id)
        if target is None:
            continue
        bucket = grouped.setdefault(
            target.id,
            {
                "activity_id": target.id,
                "activity_code": target.code,
                "activity_label": target.label,
                "color": target.color,
                "sort_order": target.sort_order,
                "minutes": 0,
            },
        )
        bucket["minutes"] += minutes

    return [
        SummaryRow(
            activity_id=item["activity_id"],
            activity_code=item["activity_code"],
            activity_label=item["activity_label"],
            color=item["color"],
            hours=_hours_from_minutes(item["minutes"]),
            persons_equiv=round(_hours_from_minutes(item["minutes"]) / HOURS_PER_PERSON_DAY, 1),
        )
        for item in sorted(grouped.values(), key=lambda x: (x["sort_order"], x["activity_label"]))
    ]

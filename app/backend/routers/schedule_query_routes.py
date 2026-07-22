from .schedule_shared import *

router = APIRouter(prefix="/api/schedule", tags=["schedule"])

@router.get("/revision")
def get_schedule_revision(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    weekday: int = Query(..., ge=1, le=7),
    area_id: int | None = Query(None),
    business_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "view")),
) -> dict[str, str | int | None]:
    if not isinstance(area_id, int):
        area_id = None
    if not isinstance(business_id, int):
        business_id = None
    persons, _scoped_business_id = _visible_schedule_persons(
        db,
        user,
        area_id,
        business_id,
        year=year,
        week=week,
        weekdays=[weekday],
    )

    return {
        "year": year,
        "week": week,
        "weekday": weekday,
        "area_id": area_id,
        "revision_key": _schedule_revision_for_persons(
            db,
            year=year,
            week=week,
            weekdays=[weekday],
            persons=persons,
        ),
    }


@router.get("/presence", response_model=PresenceOut)
def get_schedule_presence(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    weekday: int = Query(..., ge=1, le=7),
    hour: int = Query(..., ge=0, le=23),
    area_id: int | None = Query(None),
    business_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "view")),
) -> PresenceOut:
    selected_date = _schedule_date(year, week, weekday)
    scoped_business_id = visible_business_id(db, user, business_id)

    historical_ids = historical_person_ids_subquery(db, [(year, week, weekday)])
    if historical_ids is not None:
        persons_q = select(Person).where(or_(Person.is_active, Person.id.in_(historical_ids)))
    else:
        persons_q = select(Person).where(Person.is_active)
    if scoped_business_id is not None:
        persons_q = persons_q.where(Person.business_id == scoped_business_id)
    if area_id is not None:
        area = scoped_get(db, Area, area_id, user, detail="Område hittades inte")
        if area.is_active is not True:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Område hittades inte")
        if scoped_business_id is not None and area.business_id != scoped_business_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Område hittades inte")
        persons_q = persons_q.where(Person.home_area_id == area_id)
    persons_q = persons_q.order_by(Person.sort_order, Person.name)
    persons = db.execute(persons_q).scalars().all()
    person_ids = [person.id for person in persons]

    rest_hours = [candidate for candidate in HOURS if candidate >= hour]
    near_hours = [candidate for candidate in (hour, hour + 1) if candidate in HOURS]
    cells_by_person_hour: dict[tuple[int, int], list[ScheduleCell]] = defaultdict(list)
    if person_ids and rest_hours:
        rows = db.execute(
            select(ScheduleCell).where(
                ScheduleCell.year == year,
                ScheduleCell.week == week,
                ScheduleCell.weekday == weekday,
                ScheduleCell.person_id.in_(person_ids),
                ScheduleCell.hour.in_(rest_hours),
            )
        ).scalars().all()
        for cell in rows:
            cells_by_person_hour[(cell.person_id, cell.hour)].append(cell)

    activity_query = db.query(Activity)
    area_query = db.query(Area)
    business_query = db.query(Business)
    if scoped_business_id is not None:
        activity_query = activity_query.filter(Activity.business_id == scoped_business_id)
        area_query = area_query.filter(Area.business_id == scoped_business_id)
        business_query = business_query.filter(Business.id == scoped_business_id)
    activities = activity_query.all()
    areas = area_query.all()
    businesses = business_query.all()
    activities_by_id = {activity.id: activity for activity in activities}
    areas_by_id = {area.id: area for area in areas}
    businesses_by_id = {business.id: business for business in businesses}
    home_activity_for = build_home_activity_resolver(activities, areas)
    home_activity_by_person_id = {person.id: home_activity_for(person) for person in persons}
    template_hours_map = get_template_hours_map_for_dates(db, person_ids, [selected_date])

    groups_by_business_id: dict[int | None, PresenceBusinessGroup] = {}
    for person in persons:
        template_hours = template_hours_map.get((person.id, selected_date))
        home_activity_id = home_activity_by_person_id.get(person.id)

        effective_by_hour = {
            candidate: _effective_activity_ids_for_hour(
                cells_by_person_hour.get((person.id, candidate), []),
                is_scheduled=template_hours is not None and candidate in template_hours,
                home_activity_id=home_activity_id,
            )
            for candidate in set(rest_hours + near_hours)
        }
        has_non_absence_rest = any(
            _has_non_absence_activity(effective_by_hour.get(candidate, []), activities_by_id)
            for candidate in rest_hours
        )
        has_work_now_or_next = any(
            _has_activity_category(effective_by_hour.get(candidate, []), activities_by_id, "work")
            for candidate in near_hours
        )
        if not has_non_absence_rest or not has_work_now_or_next:
            continue

        current_activity_id, current_activity, current_category = _presence_current_activity(
            effective_by_hour.get(hour, []),
            activities_by_id,
        )
        group = groups_by_business_id.setdefault(
            person.business_id,
            _presence_business_group(person.business_id, businesses_by_id),
        )
        home_area = areas_by_id.get(person.home_area_id)
        group.rows.append(
            PresenceRow(
                person_id=person.id,
                name=person.name,
                home_area_id=person.home_area_id,
                home_area=home_area.name if home_area is not None else None,
                current_activity_id=current_activity_id,
                current_activity=current_activity,
                current_activity_category=current_category,
            )
        )

    groups = sorted(groups_by_business_id.values(), key=lambda group: _presence_business_sort_key(group, businesses_by_id))
    return PresenceOut(
        date=selected_date.isoformat(),
        year=year,
        week=week,
        weekday=weekday,
        hour=hour,
        generated_at=datetime.now(timezone.utc),
        area_id=area_id,
        groups=groups,
    )


@router.get("", response_model=ScheduleOut)
def get_schedule(
    year: int = Query(..., ge=2000, le=2100),
    week: int = Query(..., ge=1, le=53),
    weekday: int = Query(..., ge=1, le=7),
    area_id: int | None = Query(None),
    business_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "view")),
) -> ScheduleOut:
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
    person_ids = [p.id for p in persons]

    cells: list[ScheduleCell] = []
    if person_ids:
        cells = (
            db.execute(
                select(ScheduleCell).where(
                    ScheduleCell.year == year,
                    ScheduleCell.week == week,
                    ScheduleCell.weekday == weekday,
                    ScheduleCell.person_id.in_(person_ids),
                )
            )
            .scalars()
            .all()
        )

    template_hours_map = get_template_hours_map_for_dates(db, person_ids, [selected_date])
    activity_query = db.query(Activity)
    area_query = db.query(Area)
    if scoped_business_id is not None:
        activity_query = activity_query.filter(Activity.business_id == scoped_business_id)
        area_query = area_query.filter(Area.business_id == scoped_business_id)
    home_activity_for = build_home_activity_resolver(activity_query.all(), area_query.all())
    home_activity_by_person_id = {p.id: home_activity_for(p) for p in persons}

    scheduled_hours: dict[int, list[int]] = {}
    scheduled_defaults: dict[int, dict[int, int]] = {}
    for p in persons:
        hrs = template_hours_map.get((p.id, selected_date))
        if hrs:
            sorted_hours = sorted(hrs)
            scheduled_hours[p.id] = sorted_hours
            home_activity_id = home_activity_by_person_id.get(p.id)
            if home_activity_id is not None:
                scheduled_defaults[p.id] = {hour: home_activity_id for hour in sorted_hours}

    if is_date_frozen(db, selected_date):
        # Fryst datum: mallen appliceras inte (template_hours_map är tom), så
        # vilka timmar som var schemalagda härleds ur cellerna i stället —
        # timmar med aktivitet eller uttryckligt tom markering. Utan det tappar
        # Bemanning den diskreta schemalagd-markeringen på hela historiken.
        hours_by_person: dict[int, set[int]] = {}
        for cell in cells:
            if cell.activity_id is not None or cell.empty_override or cell.is_template_fill:
                hours_by_person.setdefault(cell.person_id, set()).add(cell.hour)
        for person_id, hours in hours_by_person.items():
            scheduled_hours[person_id] = sorted(set(scheduled_hours.get(person_id, [])) | hours)

    return ScheduleOut(
        year=year,
        week=week,
        weekday=weekday,
        area_id=area_id,
        revision_key=_schedule_revision_key(persons, cells),
        persons=[person_out_with_home_activity(p, home_activity_by_person_id.get(p.id)) for p in persons],
        cells=[CellOut(**_cell_to_dict(c)) for c in sorted(cells, key=lambda c: (c.person_id, c.hour, c.minute_start))],
        scheduled_hours=scheduled_hours,
        scheduled_defaults=scheduled_defaults,
        lock_foreign_schedule_cells=foreign_schedule_cell_lock_applies(db, user),
    )



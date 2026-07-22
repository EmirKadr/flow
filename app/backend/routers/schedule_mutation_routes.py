from .schedule_shared import *

router = APIRouter()

@router.put("/cell")
def update_cell(
    payload: CellUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "edit")),
):
    _validate_segment(payload.hour, payload.minute_start, payload.minute_end)

    person = scoped_get(db, Person, payload.person_id, user, detail="Person hittades inte")
    activity = None
    if payload.activity_id is not None:
        activity = scoped_get(db, Activity, payload.activity_id, user, detail="Aktivitet hittades inte")
        if activity.business_id != person.business_id:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Person och aktivitet tillhör olika verksamheter")

    hour_segments = _load_hour_segments(
        db,
        year=payload.year,
        week=payload.week,
        weekday=payload.weekday,
        hour=payload.hour,
        person_id=payload.person_id,
        lock=True,
    )
    owner_lock_enabled = foreign_schedule_cell_lock_applies(db, user)
    matching = next(
        (
            cell
            for cell in hour_segments
            if cell.minute_start == payload.minute_start and cell.minute_end == payload.minute_end
        ),
        None,
    )

    current_version = matching.version if matching else 0
    if current_version != payload.expected_version:
        return _conflict_response(person_id=payload.person_id, hour=payload.hour, current=hour_segments)

    if matching is None and hour_segments:
        return _conflict_response(person_id=payload.person_id, hour=payload.hour, current=hour_segments)

    if matching is None:
        cell = ScheduleCell(
            year=payload.year,
            week=payload.week,
            weekday=payload.weekday,
            hour=payload.hour,
            minute_start=payload.minute_start,
            minute_end=payload.minute_end,
            person_id=payload.person_id,
            activity_id=payload.activity_id,
            loan_area_id=None,
            empty_override=_empty_override_for(
                db,
                person_id=payload.person_id,
                year=payload.year,
                week=payload.week,
                weekday=payload.weekday,
                hour=payload.hour,
                activity_id=payload.activity_id,
            ),
            version=1,
            updated_by=user.id,
        )
        db.add(cell)
        db.flush()
        audit_log(
            db,
            entity_type="schedule_cell",
            entity_id=cell.id,
            action="create",
            old_value=None,
            new_value=_cell_audit_dict(cell),
            user_id=user.id,
            business_id=person.business_id,
        )
    else:
        cell = matching
        desired_empty_override = _empty_override_for(
            db,
            person_id=payload.person_id,
            year=payload.year,
            week=payload.week,
            weekday=payload.weekday,
            hour=payload.hour,
            activity_id=payload.activity_id,
        )
        if (
            cell.activity_id == payload.activity_id
            and cell.loan_area_id is None
            and cell.empty_override == desired_empty_override
        ):
            return {"cell": _cell_to_dict(cell)}
        assert_can_modify_schedule_cells([cell], user, owner_lock_enabled)
        old = _cell_audit_dict(cell)
        cell.activity_id = payload.activity_id
        cell.loan_area_id = None
        cell.empty_override = desired_empty_override
        cell.version += 1
        cell.updated_by = user.id
        db.flush()
        audit_log(
            db,
            entity_type="schedule_cell",
            entity_id=cell.id,
            action="update",
            old_value=old,
            new_value=_cell_audit_dict(cell),
            user_id=user.id,
            business_id=person.business_id,
        )

    db.commit()
    db.refresh(cell)
    return {"cell": _cell_to_dict(cell)}


@router.put("/cell/remark")
def update_cell_remark(
    payload: CellRemarkUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "edit")),
):
    _validate_segment(payload.hour, payload.minute_start, payload.minute_end)
    person = scoped_get(db, Person, payload.person_id, user, detail="Person hittades inte")
    remark = _normalize_cell_remark(payload.remark)

    hour_segments = _load_hour_segments(
        db,
        year=payload.year,
        week=payload.week,
        weekday=payload.weekday,
        hour=payload.hour,
        person_id=payload.person_id,
        lock=True,
    )
    owner_lock_enabled = foreign_schedule_cell_lock_applies(db, user)
    matching = next(
        (
            cell
            for cell in hour_segments
            if cell.minute_start == payload.minute_start and cell.minute_end == payload.minute_end
        ),
        None,
    )

    current_version = matching.version if matching else 0
    if current_version != payload.expected_version:
        return _conflict_response(person_id=payload.person_id, hour=payload.hour, current=hour_segments)
    if matching is None and hour_segments:
        return _conflict_response(person_id=payload.person_id, hour=payload.hour, current=hour_segments)

    if matching is None:
        if remark is None:
            return {"cell": _empty_segment_dict(payload.person_id, payload.hour, payload.minute_start, payload.minute_end)}
        cell = ScheduleCell(
            year=payload.year,
            week=payload.week,
            weekday=payload.weekday,
            hour=payload.hour,
            minute_start=payload.minute_start,
            minute_end=payload.minute_end,
            person_id=payload.person_id,
            activity_id=None,
            loan_area_id=None,
            remark=remark,
            empty_override=False,
            version=1,
            updated_by=user.id,
        )
        db.add(cell)
        db.flush()
        audit_log(
            db,
            entity_type="schedule_cell",
            entity_id=cell.id,
            action="remark_create",
            old_value=None,
            new_value=_cell_audit_dict(cell),
            user_id=user.id,
            business_id=person.business_id,
        )
        db.commit()
        db.refresh(cell)
        return {"cell": _cell_to_dict(cell)}

    if _normalize_cell_remark(matching.remark) == remark:
        return {"cell": _cell_to_dict(matching)}

    assert_can_modify_schedule_cells([matching], user, owner_lock_enabled)
    old = _cell_audit_dict(matching)
    if (
        remark is None
        and len(hour_segments) == 1
        and matching.activity_id is None
        and matching.loan_area_id is None
        and not matching.empty_override
    ):
        audit_log(
            db,
            entity_type="schedule_cell",
            entity_id=matching.id,
            action="remark_delete",
            old_value=old,
            new_value=None,
            user_id=user.id,
            business_id=person.business_id,
        )
        db.delete(matching)
        db.commit()
        return {"cell": _empty_segment_dict(payload.person_id, payload.hour, payload.minute_start, payload.minute_end)}

    matching.remark = remark
    matching.version += 1
    matching.updated_by = user.id
    db.flush()
    audit_log(
        db,
        entity_type="schedule_cell",
        entity_id=matching.id,
        action="remark_update",
        old_value=old,
        new_value=_cell_audit_dict(matching),
        user_id=user.id,
        business_id=person.business_id,
    )
    db.commit()
    db.refresh(matching)
    return {"cell": _cell_to_dict(matching)}


@router.put("/cell/split")
def split_cell(
    payload: SplitCellRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "edit")),
):
    if payload.hour not in HOURS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Timme måste vara {HOURS[0]}-{HOURS[-1]}")
    split_ranges = _split_ranges_from_payload(payload)
    person = scoped_get(db, Person, payload.person_id, user, detail="Person hittades inte")

    hour_segments = _load_hour_segments(
        db,
        year=payload.year,
        week=payload.week,
        weekday=payload.weekday,
        hour=payload.hour,
        person_id=payload.person_id,
        lock=True,
    )
    owner_lock_enabled = foreign_schedule_cell_lock_applies(db, user)
    if _segment_signature(hour_segments) != _expected_signature(payload.segments):
        return _conflict_response(person_id=payload.person_id, hour=payload.hour, current=hour_segments)

    if len(hour_segments) >= MIN_SPLIT_PARTS and _is_split_cells(hour_segments):
        assert_can_modify_schedule_cells(hour_segments, user, owner_lock_enabled)
        preferred = next(
            (
                cell
                for cell in hour_segments
                if cell.minute_start == payload.merge_minute_start
            ),
            None,
        )
        if preferred is None:
            preferred = next((cell for cell in hour_segments if cell.activity_id is not None), None) or hour_segments[0]
        other_segments = [cell for cell in hour_segments if cell.id != preferred.id]

        old_preferred = _cell_audit_dict(preferred)
        old_others = [(other, _cell_audit_dict(other)) for other in other_segments]
        merged_loan_area_id = preferred.loan_area_id
        if preferred.activity_id is None:
            merged_loan_area_id = preferred.loan_area_id or next(
                (cell.loan_area_id for cell in other_segments if cell.loan_area_id is not None),
                None,
            )
        merged_empty_override = any(cell.empty_override for cell in hour_segments)
        merged_remark = _merged_cell_remark(hour_segments)

        for other, old_other in old_others:
            audit_log(
                db,
                entity_type="schedule_cell",
                entity_id=other.id,
                action="split_merge_delete",
                old_value=old_other,
                new_value=None,
                user_id=user.id,
            )
            db.delete(other)
        db.flush()

        preferred.minute_start = 0
        preferred.minute_end = 60
        preferred.loan_area_id = None if preferred.activity_id is not None else merged_loan_area_id
        preferred.remark = merged_remark
        preferred.empty_override = merged_empty_override
        preferred.version += 1
        preferred.updated_by = user.id
        db.flush()
        audit_log(
            db,
            entity_type="schedule_cell",
            entity_id=preferred.id,
            action="split_merge_update",
            old_value=old_preferred,
            new_value=_cell_audit_dict(preferred),
            user_id=user.id,
        )
        db.commit()
        db.refresh(preferred)
        return {"segments": [_cell_to_dict(preferred)]}

    if len(hour_segments) > 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Kan bara dela en tom timme eller en hel timcell.")

    if not hour_segments:
        created: list[ScheduleCell] = []
        for minute_start, minute_end in split_ranges:
            cell = ScheduleCell(
                year=payload.year,
                week=payload.week,
                weekday=payload.weekday,
                hour=payload.hour,
                minute_start=minute_start,
                minute_end=minute_end,
                person_id=payload.person_id,
                activity_id=None,
                loan_area_id=None,
                empty_override=False,
                version=1,
                updated_by=user.id,
            )
            db.add(cell)
            db.flush()
            audit_log(
                db,
                entity_type="schedule_cell",
                entity_id=cell.id,
                action="split_create",
                old_value=None,
                new_value=_cell_audit_dict(cell),
                user_id=user.id,
            )
            created.append(cell)
        db.commit()
        return {"segments": _serialize_segments(created)}

    source = hour_segments[0]
    if (source.minute_start, source.minute_end) != FULL_SEGMENT:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cellen är redan delad eller har ogiltigt segmentformat.")

    assert_can_modify_schedule_cells([source], user, owner_lock_enabled)
    old = _cell_audit_dict(source)
    original_activity_id = source.activity_id
    original_loan_area_id = source.loan_area_id
    original_remark = source.remark
    original_empty_override = source.empty_override
    first_start, first_end = split_ranges[0]
    source.minute_start = first_start
    source.minute_end = first_end
    source.version += 1
    source.updated_by = user.id
    db.flush()
    audit_log(
        db,
        entity_type="schedule_cell",
        entity_id=source.id,
        action="split_update",
        old_value=old,
        new_value=_cell_audit_dict(source),
        user_id=user.id,
    )

    created_segments = [source]
    for minute_start, minute_end in split_ranges[1:]:
        segment = ScheduleCell(
            year=source.year,
            week=source.week,
            weekday=source.weekday,
            hour=source.hour,
            minute_start=minute_start,
            minute_end=minute_end,
            person_id=source.person_id,
            activity_id=original_activity_id,
            loan_area_id=original_loan_area_id,
            remark=original_remark,
            empty_override=original_empty_override,
            version=1,
            updated_by=user.id,
        )
        db.add(segment)
        db.flush()
        audit_log(
            db,
            entity_type="schedule_cell",
            entity_id=segment.id,
            action="split_create",
            old_value=None,
            new_value=_cell_audit_dict(segment),
            user_id=user.id,
        )
        created_segments.append(segment)

    db.commit()
    return {"segments": _serialize_segments(created_segments)}


@router.post("/cells")
def bulk_update_cells(
    payload: BulkCellRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "edit")),
):
    if not payload.cells:
        return {"applied": [], "conflicts": []}
    if len(payload.cells) > 200:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="För många celler (max 200)")

    applied: list[dict] = []
    conflicts: list[dict] = []
    grouped_items: dict[tuple[int, int, int, int, int], list] = defaultdict(list)
    person_ids: set[int] = set()
    activity_ids: set[int] = set()
    loan_area_ids: set[int] = set()
    dates_by_ywd: dict[tuple[int, int, int], date] = {}

    for item in payload.cells:
        _validate_segment(item.hour, item.minute_start, item.minute_end)
        if item.activity_id is not None and item.loan_area_id is not None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Aktivitet och låneområde kan inte sättas samtidigt.",
            )
        grouped_items[(item.person_id, item.year, item.week, item.weekday, item.hour)].append(item)
        person_ids.add(item.person_id)
        dates_by_ywd.setdefault(
            (item.year, item.week, item.weekday),
            _schedule_date(item.year, item.week, item.weekday),
        )
        if item.activity_id is not None:
            activity_ids.add(item.activity_id)
        if item.loan_area_id is not None:
            loan_area_ids.add(item.loan_area_id)

    scoped_business_id = visible_business_id(db, user)
    person_query = select(Person).where(Person.id.in_(person_ids))
    if scoped_business_id is not None:
        person_query = person_query.where(Person.business_id == scoped_business_id)
    persons_by_id = {person.id: person for person in db.execute(person_query).scalars().all()}
    existing_person_ids = set(persons_by_id)
    missing_person_ids = sorted(person_ids - existing_person_ids)
    if missing_person_ids:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"Person {missing_person_ids[0]} hittades inte",
        )

    if activity_ids:
        activity_query = select(Activity).where(Activity.id.in_(activity_ids))
        if scoped_business_id is not None:
            activity_query = activity_query.where(Activity.business_id == scoped_business_id)
        activities_by_id = {activity.id: activity for activity in db.execute(activity_query).scalars().all()}
        existing_activity_ids = set(activities_by_id)
        missing_activity_ids = sorted(activity_ids - existing_activity_ids)
        if missing_activity_ids:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"Aktivitet {missing_activity_ids[0]} hittades inte",
            )
        for item in payload.cells:
            if item.activity_id is None:
                continue
            if activities_by_id[item.activity_id].business_id != persons_by_id[item.person_id].business_id:
                raise HTTPException(status.HTTP_409_CONFLICT, detail="Person och aktivitet tillhör olika verksamheter")

    if loan_area_ids:
        area_query = select(Area).where(Area.id.in_(loan_area_ids))
        if scoped_business_id is not None:
            area_query = area_query.where(Area.business_id == scoped_business_id)
        areas_by_id = {area.id: area for area in db.execute(area_query).scalars().all()}
        existing_area_ids = set(areas_by_id)
        missing_area_ids = sorted(loan_area_ids - existing_area_ids)
        if missing_area_ids:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"Område {missing_area_ids[0]} hittades inte",
            )
        for item in payload.cells:
            if item.loan_area_id is None:
                continue
            loan_area = areas_by_id[item.loan_area_id]
            if loan_area.is_active is not True:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Område hittades inte")
            if loan_area.business_id != persons_by_id[item.person_id].business_id:
                raise HTTPException(status.HTTP_409_CONFLICT, detail="Person och område tillhör olika verksamheter")

    template_hours_map = get_template_hours_map_for_dates(db, person_ids, dates_by_ywd.values())
    owner_lock_enabled = foreign_schedule_cell_lock_applies(db, user)
    hour_segments_by_key = _load_hour_segments_for_keys(db, set(grouped_items), lock=True)

    try:
        for (person_id, year, week, weekday, hour), group_items in grouped_items.items():
            item_business_id = persons_by_id[person_id].business_id
            group_items = sorted(group_items, key=lambda item: (item.minute_start, item.minute_end))
            seen_ranges: set[tuple[int, int]] = set()
            for item in group_items:
                range_key = (item.minute_start, item.minute_end)
                if range_key in seen_ranges:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail="Duplicerade segment i samma timme.",
                    )
                seen_ranges.add(range_key)

            selected_date = dates_by_ywd[(year, week, weekday)]
            template_hours = template_hours_map.get((person_id, selected_date))
            hour_segments = list(hour_segments_by_key.get((person_id, year, week, weekday, hour), []))
            # Pa ett fryst datum svarar mallen inte; timmens egna celler far da
            # avgora om den var schemalagd, sa en historisk rattning inte
            # tappar schemalagd-markeringen.
            frozen_segments = hour_segments if is_date_frozen(db, selected_date) else None
            item_by_range = {
                (item.minute_start, item.minute_end): item
                for item in group_items
            }
            version_checked_ranges: set[tuple[int, int]] = set()
            split_ranges = _split_ranges_for_items(group_items)
            wants_split_segments = split_ranges is not None

            if wants_split_segments:
                full_segment = (
                    hour_segments[0]
                    if len(hour_segments) == 1
                    and (hour_segments[0].minute_start, hour_segments[0].minute_end) == FULL_SEGMENT
                    else None
                )

                if full_segment is not None:
                    if any(item.expected_version != full_segment.version for item in group_items):
                        conflicts.append(_bulk_conflict_dict(group_items[0], hour_segments))
                        if payload.atomic:
                            db.rollback()
                            return JSONResponse(
                                status_code=status.HTTP_409_CONFLICT,
                                content={"error": "version_conflict", "conflicts": conflicts},
                            )
                        continue

                    assert_can_modify_schedule_cells([full_segment], user, owner_lock_enabled)
                    old_full = _cell_audit_dict(full_segment)
                    original_activity_id = full_segment.activity_id
                    original_loan_area_id = full_segment.loan_area_id
                    original_remark = full_segment.remark
                    original_empty_override = full_segment.empty_override
                    first_start, first_end = split_ranges[0]
                    full_segment.minute_start = first_start
                    full_segment.minute_end = first_end
                    full_segment.version += 1
                    full_segment.updated_by = user.id

                    created_split_segments: list[ScheduleCell] = []
                    for minute_start, minute_end in split_ranges[1:]:
                        segment = ScheduleCell(
                            year=year,
                            week=week,
                            weekday=weekday,
                            hour=hour,
                            minute_start=minute_start,
                            minute_end=minute_end,
                            person_id=person_id,
                            activity_id=original_activity_id,
                            loan_area_id=original_loan_area_id,
                            remark=original_remark,
                            empty_override=original_empty_override,
                            version=1,
                            updated_by=user.id,
                        )
                        db.add(segment)
                        created_split_segments.append(segment)
                    db.flush()
                    audit_log(
                        db,
                        entity_type="schedule_cell",
                        entity_id=full_segment.id,
                        action=f"{payload.action}_split_update",
                        old_value=old_full,
                        new_value=_cell_audit_dict(full_segment),
                        user_id=user.id,
                        business_id=item_business_id,
                    )
                    for segment in created_split_segments:
                        audit_log(
                            db,
                            entity_type="schedule_cell",
                            entity_id=segment.id,
                            action=f"{payload.action}_split_create",
                            old_value=None,
                            new_value=_cell_audit_dict(segment),
                            user_id=user.id,
                            business_id=item_business_id,
                        )
                    hour_segments = sorted(
                        [full_segment, *created_split_segments],
                        key=lambda cell: (cell.minute_start, cell.minute_end),
                    )
                    version_checked_ranges = set(item_by_range.keys())
                elif not hour_segments:
                    if any(item.expected_version != 0 for item in group_items):
                        conflicts.append(_bulk_conflict_dict(group_items[0], hour_segments))
                        if payload.atomic:
                            db.rollback()
                            return JSONResponse(
                                status_code=status.HTTP_409_CONFLICT,
                                content={"error": "version_conflict", "conflicts": conflicts},
                            )
                        continue

                    created: list[ScheduleCell] = []
                    for minute_start, minute_end in split_ranges:
                        desired_item = item_by_range.get((minute_start, minute_end))
                        desired_activity_id = (
                            desired_item.activity_id if desired_item is not None else None
                        )
                        desired_loan_area_id = (
                            desired_item.loan_area_id if desired_item is not None else None
                        )
                        cell = ScheduleCell(
                            year=year,
                            week=week,
                            weekday=weekday,
                            hour=hour,
                            minute_start=minute_start,
                            minute_end=minute_end,
                            person_id=person_id,
                            activity_id=desired_activity_id,
                            loan_area_id=desired_loan_area_id,
                            empty_override=_empty_override_for_template(
                                template_hours,
                                hour=hour,
                                activity_id=desired_activity_id,
                                frozen_segments=frozen_segments,
                            ),
                            version=1,
                            updated_by=user.id,
                        )
                        db.add(cell)
                        created.append(cell)

                    db.flush()
                    for cell in created:
                        audit_log(
                            db,
                            entity_type="schedule_cell",
                            entity_id=cell.id,
                            action=payload.action,
                            old_value=None,
                            new_value=_cell_audit_dict(cell),
                            user_id=user.id,
                            business_id=item_business_id,
                        )
                    applied.extend(_serialize_segments(created))
                    continue

            current_by_range = {
                (cell.minute_start, cell.minute_end): cell for cell in hour_segments
            }
            created_cells: list[ScheduleCell] = []
            updated_cells: list[tuple[ScheduleCell, dict]] = []
            group_conflict = False

            for item in group_items:
                range_key = (item.minute_start, item.minute_end)
                matching = current_by_range.get(range_key)
                if matching is None and hour_segments:
                    conflicts.append(_bulk_conflict_dict(item, hour_segments))
                    group_conflict = True
                    break

                current_version = matching.version if matching else 0
                if range_key not in version_checked_ranges and current_version != item.expected_version:
                    conflicts.append(_bulk_conflict_dict(item, hour_segments))
                    group_conflict = True
                    break

                desired_empty_override = _empty_override_for_template(
                    template_hours,
                    hour=hour,
                    activity_id=item.activity_id,
                    frozen_segments=frozen_segments,
                )

                if matching is None:
                    cell = ScheduleCell(
                        year=year,
                        week=week,
                        weekday=weekday,
                        hour=hour,
                        minute_start=item.minute_start,
                        minute_end=item.minute_end,
                        person_id=person_id,
                        activity_id=item.activity_id,
                        loan_area_id=item.loan_area_id,
                        empty_override=desired_empty_override,
                        version=1,
                        updated_by=user.id,
                    )
                    db.add(cell)
                    hour_segments.append(cell)
                    current_by_range[range_key] = cell
                    created_cells.append(cell)
                    continue

                if (
                    matching.activity_id == item.activity_id
                    and matching.loan_area_id == item.loan_area_id
                    and matching.empty_override == desired_empty_override
                ):
                    continue

                assert_can_modify_schedule_cells([matching], user, owner_lock_enabled)
                old = _cell_audit_dict(matching)
                matching.activity_id = item.activity_id
                matching.loan_area_id = item.loan_area_id
                matching.empty_override = desired_empty_override
                matching.version += 1
                matching.updated_by = user.id
                updated_cells.append((matching, old))

            if group_conflict:
                if payload.atomic:
                    db.rollback()
                    return JSONResponse(
                        status_code=status.HTTP_409_CONFLICT,
                        content={"error": "version_conflict", "conflicts": conflicts},
                    )
                continue

            if created_cells or updated_cells:
                db.flush()
                for cell in created_cells:
                    audit_log(
                        db,
                        entity_type="schedule_cell",
                        entity_id=cell.id,
                        action=payload.action,
                        old_value=None,
                        new_value=_cell_audit_dict(cell),
                        user_id=user.id,
                        business_id=item_business_id,
                    )
                for cell, old in updated_cells:
                    audit_log(
                        db,
                        entity_type="schedule_cell",
                        entity_id=cell.id,
                        action=payload.action,
                        old_value=old,
                        new_value=_cell_audit_dict(cell),
                        user_id=user.id,
                        business_id=item_business_id,
                    )

            applied.extend(_serialize_segments(hour_segments))

        db.commit()
        return {"applied": applied, "conflicts": conflicts}
    except HTTPException:
        db.rollback()
        raise


@router.put("/hours/restore")
def restore_hours(
    payload: RestoreHoursRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_view_access("schedule", "edit")),
):
    if not payload.hours:
        return {"hours": []}
    if len(payload.hours) > 200:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="För många timmar (max 200)")

    seen_hours: set[tuple[int, int, int, int, int]] = set()
    person_ids: set[int] = set()
    activity_ids: set[int] = set()
    loan_area_ids: set[int] = set()
    for item in payload.hours:
        _validate_segment(item.hour, 0, 60)
        _validate_restore_segments(item)
        key = (item.person_id, item.year, item.week, item.weekday, item.hour)
        if key in seen_hours:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Duplicerade timmar i undo.")
        seen_hours.add(key)
        person_ids.add(item.person_id)
        for segment in item.segments:
            if segment.activity_id is not None and segment.loan_area_id is not None:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail="Aktivitet och låneområde kan inte sättas samtidigt.",
                )
            if segment.activity_id is not None:
                activity_ids.add(segment.activity_id)
            if segment.loan_area_id is not None:
                loan_area_ids.add(segment.loan_area_id)

    scoped_business_id = visible_business_id(db, user)
    person_query = select(Person).where(Person.id.in_(person_ids))
    if scoped_business_id is not None:
        person_query = person_query.where(Person.business_id == scoped_business_id)
    persons_by_id = {person.id: person for person in db.execute(person_query).scalars().all()}
    existing_person_ids = set(persons_by_id)
    missing_person_ids = sorted(person_ids - existing_person_ids)
    if missing_person_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Person {missing_person_ids[0]} hittades inte")

    if activity_ids:
        activity_query = select(Activity).where(Activity.id.in_(activity_ids))
        if scoped_business_id is not None:
            activity_query = activity_query.where(Activity.business_id == scoped_business_id)
        activities_by_id = {activity.id: activity for activity in db.execute(activity_query).scalars().all()}
        existing_activity_ids = set(activities_by_id)
        missing_activity_ids = sorted(activity_ids - existing_activity_ids)
        if missing_activity_ids:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Aktivitet {missing_activity_ids[0]} hittades inte")
        for item in payload.hours:
            for segment in item.segments:
                if segment.activity_id is None:
                    continue
                if activities_by_id[segment.activity_id].business_id != persons_by_id[item.person_id].business_id:
                    raise HTTPException(status.HTTP_409_CONFLICT, detail="Person och aktivitet tillhör olika verksamheter")

    if loan_area_ids:
        area_query = select(Area).where(Area.id.in_(loan_area_ids))
        if scoped_business_id is not None:
            area_query = area_query.where(Area.business_id == scoped_business_id)
        areas_by_id = {area.id: area for area in db.execute(area_query).scalars().all()}
        existing_area_ids = set(areas_by_id)
        missing_area_ids = sorted(loan_area_ids - existing_area_ids)
        if missing_area_ids:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Område {missing_area_ids[0]} hittades inte")
        for item in payload.hours:
            for segment in item.segments:
                if segment.loan_area_id is None:
                    continue
                loan_area = areas_by_id[segment.loan_area_id]
                if loan_area.is_active is not True:
                    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Område hittades inte")
                if loan_area.business_id != persons_by_id[item.person_id].business_id:
                    raise HTTPException(status.HTTP_409_CONFLICT, detail="Person och område tillhör olika verksamheter")

    restored: list[dict] = []
    owner_lock_enabled = foreign_schedule_cell_lock_applies(db, user)
    hour_segments_by_key = _load_hour_segments_for_keys(db, seen_hours, lock=True)
    try:
        current_by_key: dict[tuple[int, int, int, int, int], list[ScheduleCell]] = {}
        for item in payload.hours:
            key = (item.person_id, item.year, item.week, item.weekday, item.hour)
            current = list(hour_segments_by_key.get(key, []))
            if _segment_signature(current) != _expected_signature(item.expected_segments):
                db.rollback()
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content={
                        "error": "version_conflict",
                        "conflicts": [
                            {
                                "person_id": item.person_id,
                                "hour": item.hour,
                                "current": _serialize_segments(current)
                                or [_empty_segment_dict(item.person_id, item.hour, 0, 60)],
                            }
                        ],
                    },
                )

            assert_can_modify_schedule_cells(current, user, owner_lock_enabled)
            current_by_key[key] = current

        for item in payload.hours:
            key = (item.person_id, item.year, item.week, item.weekday, item.hour)
            item_business_id = persons_by_id[item.person_id].business_id
            for cell in current_by_key.get(key, []):
                audit_log(
                    db,
                    entity_type="schedule_cell",
                    entity_id=cell.id,
                    action=f"{payload.action}_delete",
                    old_value=_cell_audit_dict(cell),
                    new_value=None,
                    user_id=user.id,
                    business_id=item_business_id,
                )
                db.delete(cell)
        if any(current_by_key.values()):
            db.flush()

        created_by_key: dict[tuple[int, int, int, int, int], list[ScheduleCell]] = {}
        for item in payload.hours:
            key = (item.person_id, item.year, item.week, item.weekday, item.hour)
            created: list[ScheduleCell] = []
            for segment in sorted(item.segments, key=lambda s: (s.minute_start, s.minute_end)):
                cell = ScheduleCell(
                    year=item.year,
                    week=item.week,
                    weekday=item.weekday,
                    hour=item.hour,
                    minute_start=segment.minute_start,
                    minute_end=segment.minute_end,
                    person_id=item.person_id,
                    activity_id=segment.activity_id,
                    loan_area_id=segment.loan_area_id,
                    remark=_normalize_cell_remark(segment.remark),
                    empty_override=segment.empty_override,
                    version=1,
                    updated_by=user.id,
                )
                db.add(cell)
                created.append(cell)
            created_by_key[key] = created

        if any(created_by_key.values()):
            db.flush()
            for item in payload.hours:
                key = (item.person_id, item.year, item.week, item.weekday, item.hour)
                item_business_id = persons_by_id[item.person_id].business_id
                for cell in created_by_key.get(key, []):
                    audit_log(
                        db,
                        entity_type="schedule_cell",
                        entity_id=cell.id,
                        action=f"{payload.action}_create",
                        old_value=None,
                        new_value=_cell_audit_dict(cell),
                        user_id=user.id,
                        business_id=item_business_id,
                    )

        for item in payload.hours:
            key = (item.person_id, item.year, item.week, item.weekday, item.hour)
            restored.append({
                "person_id": item.person_id,
                "hour": item.hour,
                "segments": _serialize_segments(created_by_key.get(key, [])),
            })

        db.commit()
        return {"hours": restored}
    except HTTPException:
        db.rollback()
        raise



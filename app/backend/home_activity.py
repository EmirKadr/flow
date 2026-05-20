from collections.abc import Iterable

from .models import Activity, Area, Person
from .schemas import PersonOut


def build_home_activity_resolver(
    activities: Iterable[Activity],
    areas: Iterable[Area],
):
    activities_by_code = {activity.code: activity for activity in activities}
    areas_by_id = {area.id: area for area in areas}
    activities_by_area: dict[int | None, list[Activity]] = {}

    for activity in activities:
        activities_by_area.setdefault(activity.area_id, []).append(activity)

    for area_activities in activities_by_area.values():
        area_activities.sort(key=lambda activity: (activity.sort_order, activity.label))

    def resolve(person: Person) -> int | None:
        if person.home_activity_id is not None:
            return person.home_activity_id

        home_area = areas_by_id.get(person.home_area_id)
        preferred = activities_by_code.get(f"{home_area.code}_VM") if home_area else None
        if preferred is not None:
            return preferred.id

        fallback = next(
            (
                activity
                for activity in activities_by_area.get(person.home_area_id, [])
                if activity.category != "absence"
            ),
            None,
        )
        return fallback.id if fallback is not None else None

    return resolve


def person_out_with_home_activity(person: Person, home_activity_id: int | None) -> PersonOut:
    data = PersonOut.model_validate(person).model_dump()
    data["home_activity_id"] = home_activity_id
    return PersonOut(**data)

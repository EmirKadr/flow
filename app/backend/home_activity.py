from collections.abc import Iterable

from .models import Activity, Area, Person
from .schemas import PersonOut


def build_home_activity_resolver(
    activities: Iterable[Activity],
    areas: Iterable[Area],
):
    """Resolve only the explicit person home activity; do not infer one from area."""
    _ = (activities, areas)

    def resolve(person: Person) -> int | None:
        return person.home_activity_id

    return resolve


def person_out_with_home_activity(person: Person, home_activity_id: int | None) -> PersonOut:
    data = PersonOut.model_validate(person).model_dump()
    data["home_activity_id"] = home_activity_id
    return PersonOut(**data)

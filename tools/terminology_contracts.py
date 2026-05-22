"""Shared terminology contracts for UI, tools, and tests.

When a product word changes, add one rule here instead of writing one-off
assertions in individual tests. Tests can then protect source contracts and
rendered user flows from the same list.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class TerminologyRule:
    key: str
    canonical_terms: tuple[str, ...]
    forbidden_terms: tuple[str, ...]
    role_access_terms: tuple[str, ...] = ()
    compatibility_paths: tuple[str, ...] = ()


TERMINOLOGY_RULES: tuple[TerminologyRule, ...] = (
    TerminologyRule(
        key="schedule_view",
        canonical_terms=("Bemanning",),
        role_access_terms=("Bemanning",),
        forbidden_terms=(
            'label: "flow"',
            "flow (`schedule`)",
            "flow: dagsschema",
            "flow dagsschema",
        ),
        compatibility_paths=(
            "tools/terminology_contracts.py",
        ),
    ),
    TerminologyRule(
        key="activities",
        canonical_terms=("Aktiviteter", "Aktivitetsimport"),
        role_access_terms=("Aktiviteter", "Aktivitetsimport"),
        forbidden_terms=(
            "Ställen",
            "Ställen / aktiviteter",
            "Ställe",
            "Ställenimport",
            "Ställeimport",
            "ställen",
            "ställe",
            "Huvudställe",
            "huvudställe",
            "huvudstalle",
            "Stallen",
            "Stalle",
            "stallen",
            "stalle",
            "stallenImport",
        ),
        compatibility_paths=(
            "app/alembic/versions/0017_rename_activity_view_ids.py",
            "app/backend/main.py",
            "app/backend/routers/activities.py",
            "app/backend/routers/persons.py",
            "app/backend/user_access.py",
            "app/frontend/js/common.js",
            "app/frontend/stallen.html",
            "tools/terminology_contracts.py",
        ),
    ),
    TerminologyRule(
        key="areas",
        canonical_terms=("Område", "Områden"),
        role_access_terms=("Områden",),
        forbidden_terms=(
            "Avdelning",
            "Avdelningar",
            "avdelning",
            "avdelningar",
        ),
        compatibility_paths=(
            "app/backend/routers/activities.py",
            "app/backend/routers/users.py",
            "tools/terminology_contracts.py",
        ),
    ),
    TerminologyRule(
        key="businesses",
        canonical_terms=("Verksamhet", "Verksamheter"),
        role_access_terms=("Verksamheter",),
        forbidden_terms=("Affärsenheter", "Affärsenhet"),
        compatibility_paths=(
            "app/backend/user_access.py",
            "app/frontend/js/common.js",
            "app/frontend/js/users.js",
            "tools/terminology_contracts.py",
        ),
    ),
)


def forbidden_terms() -> tuple[str, ...]:
    terms: list[str] = []
    for rule in TERMINOLOGY_RULES:
        terms.extend(rule.forbidden_terms)
    return tuple(dict.fromkeys(terms))


def role_access_required_terms() -> tuple[str, ...]:
    terms: list[str] = []
    for rule in TERMINOLOGY_RULES:
        terms.extend(rule.role_access_terms)
    return tuple(dict.fromkeys(terms))


def terminology_compatibility_paths() -> set[str]:
    paths: set[str] = set()
    for rule in TERMINOLOGY_RULES:
        paths.update(rule.compatibility_paths)
    return paths


_TERM_BOUNDARY = r"A-Za-z0-9_ÅÄÖåäö"


def _term_pattern(term: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![{_TERM_BOUNDARY}]){re.escape(term)}(?![{_TERM_BOUNDARY}])")


def forbidden_terms_in_text(text: str) -> list[str]:
    return [term for term in forbidden_terms() if _term_pattern(term).search(text)]


def assert_no_forbidden_terms_in_text(text: str, *, context: str = "rendered UI") -> None:
    matches = forbidden_terms_in_text(text)
    if matches:
        terms = ", ".join(matches)
        raise AssertionError(f"{context} contains forbidden legacy terminology: {terms}")

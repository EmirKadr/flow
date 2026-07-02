"""Kanoniska fillistor för frontendens skriptgrupper.

När en JS-fil splittas i moduler (mönstret js/schedule/, js/allocation/) ska
den nya filen läggas till i rätt lista här - då följer alla statiska
kontraktstester med automatiskt i stället för att läsa enskilda filer.
Ordningen ska spegla `<script>`-taggarnas ordning i HTML.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "app" / "frontend"

PERSONS_SCRIPT_FILES = [
    "js/persons.js",
]
OVERVIEW_SCRIPT_FILES = [
    "js/overview.js",
]
PRODUCTIVITY_OVERVIEW_SCRIPT_FILES = [
    "js/productivity_overview.js",
]
SANKEY_INBOUND_SCRIPT_FILES = [
    "js/sankey_inbound.js",
]


def read_sources(paths: list[str]) -> str:
    return "\n".join((FRONTEND / path).read_text(encoding="utf-8") for path in paths)


def read_persons_frontend() -> str:
    return read_sources(PERSONS_SCRIPT_FILES)


def read_overview_frontend() -> str:
    return read_sources(OVERVIEW_SCRIPT_FILES)


def read_productivity_overview_frontend() -> str:
    return read_sources(PRODUCTIVITY_OVERVIEW_SCRIPT_FILES)


def read_sankey_inbound_frontend() -> str:
    return read_sources(SANKEY_INBOUND_SCRIPT_FILES)

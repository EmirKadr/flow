"""Trace-cachens tvåskiktslagring (nattpass 2026-07-07).

Kontraktet som öppnar för --workers 2: en trace-token som skapats i en
process ska kunna hämtas i en annan. Här simuleras processbytet genom att
tömma L1 (_TRACE_CACHE) och kräva att disk-spillet levererar raderna.
"""
from __future__ import annotations

import os
import time

import pytest

from app.backend.config import settings
from app.backend.sankey_inbound import trace


ROWS = [
    {"company": "GG", "item": "1234", "picked_qty": 7, "path": "mottag>plock"},
    {"company": "MG", "item": "9999", "picked_qty": 1, "path": "mottag>öppen"},
]


@pytest.fixture(autouse=True)
def isolated_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_STORE_ROOT", str(tmp_path))
    trace._TRACE_CACHE.clear()
    yield
    trace._TRACE_CACHE.clear()


def test_roundtrip_via_l1():
    token = trace.store_trace_rows(ROWS)
    assert trace.get_trace_rows(token) == ROWS


def test_token_survives_process_switch_via_disk(tmp_path):
    token = trace.store_trace_rows(ROWS)
    trace._TRACE_CACHE.clear()  # "ny process": tomt processminne
    assert trace.get_trace_rows(token) == ROWS
    # och hydrerar L1 igen för nästa anrop
    assert token in trace._TRACE_CACHE


def test_expired_disk_entry_returns_none(tmp_path):
    token = trace.store_trace_rows(ROWS)
    trace._TRACE_CACHE.clear()
    path = trace._trace_disk_dir() / f"{token}.json.gz"
    assert path.is_file()
    old = time.time() - trace._TRACE_CACHE_TTL_SECONDS - 60
    os.utime(path, (old, old))
    assert trace.get_trace_rows(token) is None
    assert not path.exists()  # utgången fil städas vid läsning


def test_malicious_token_never_touches_disk(tmp_path):
    trace.store_trace_rows(ROWS)
    trace._TRACE_CACHE.clear()
    assert trace.get_trace_rows("../../../etc/passwd") is None
    assert trace.get_trace_rows("skräp") is None
    assert trace.get_trace_rows("") is None


def test_disk_prune_keeps_at_most_max_items(tmp_path):
    tokens = [trace.store_trace_rows(ROWS) for _ in range(trace._TRACE_DISK_MAX_ITEMS + 3)]
    files = list(trace._trace_disk_dir().glob("*.json.gz"))
    assert len(files) <= trace._TRACE_DISK_MAX_ITEMS
    # Den senaste tokenen finns alltid kvar på disk.
    assert (trace._trace_disk_dir() / f"{tokens[-1]}.json.gz").is_file()

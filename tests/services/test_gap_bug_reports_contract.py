"""Kontraktsluckor för buggrapporter (W11).

Täcker tre kontraktsdetaljer i routers/bug_reports.py som referenssviten
inte prövar direkt:

* GET-listans ``status_filter`` — giltigt värde filtrerar, okänt värde
  ignoreras (alla rapporter returneras).
* PATCH ``/status`` — inkommande status trimmas/normaliseras (" Done " → done)
  och sätter ``handled_at``/``handled_by``; en återgång till "new" nollställer
  dem igen.
* Skapande — ``context`` större än teckentaket ersätts med ``{truncated: true}``,
  och ``view_id``/``page_path``/``note`` kapas till kolumngränserna.

Återanvänder in-memory-fixturen (db_session/client/login/create_report/EVENTS)
från test_bug_reports.py — ingen egen seed behövs.
"""
from __future__ import annotations

from app.backend.models import BugReport, User

# Fixturen ligger i samma katalog; pytest (prepend-import utan __init__.py)
# lägger tests/services på sys.path så modulnamnet räcker.
from test_bug_reports import (  # noqa: F401 - db_session/client är pytest-fixturer
    EVENTS,
    client,
    create_report,
    db_session,
    login,
)


def test_status_filter_done_returns_only_done_and_unknown_is_ignored(client, db_session):
    """?status_filter=done → bara done-rapporter; okänt värde → alla."""
    login(client, "anna")
    done_id = create_report(client, note="A").json()["id"]
    seen_id = create_report(client, note="B").json()["id"]
    new_id = create_report(client, note="C").json()["id"]

    login(client, "root")  # super_user ser globalt och får ändra status
    assert client.patch(f"/api/bug-reports/{done_id}/status", json={"status": "done"}).status_code == 200
    assert client.patch(f"/api/bug-reports/{seen_id}/status", json={"status": "seen"}).status_code == 200

    only_done = client.get("/api/bug-reports?status_filter=done").json()["reports"]
    assert {row["id"] for row in only_done} == {done_id}
    assert all(row["status"] == "done" for row in only_done)

    # Okänt filtervärde matchar inte _ALLOWED_STATUSES → filtret hoppas över helt.
    ignored = client.get("/api/bug-reports?status_filter=bogus").json()["reports"]
    assert {row["id"] for row in ignored} == {done_id, seen_id, new_id}

    # Inget filter alls → också alla.
    no_filter = client.get("/api/bug-reports").json()["reports"]
    assert {row["id"] for row in no_filter} == {done_id, seen_id, new_id}


def test_status_patch_normalizes_then_sets_and_resets_handled(client, db_session):
    """' Done ' → 200 done med handled_at/by satt; 'new' nollställer dem."""
    login(client, "anna")
    report_id = create_report(client).json()["id"]

    login(client, "root")
    root_id = db_session.query(User).filter_by(username="root").one().id

    handled = client.patch(f"/api/bug-reports/{report_id}/status", json={"status": " Done "})
    assert handled.status_code == 200
    assert handled.json()["status"] == "done"  # trim + lower

    detail = client.get(f"/api/bug-reports/{report_id}").json()
    assert detail["status"] == "done"
    assert detail["handled_at"] is not None
    row = db_session.get(BugReport, report_id)
    db_session.refresh(row)
    assert row.handled_by == root_id
    assert row.handled_at is not None

    # Återgång till "new" ska nollställa både handled_at och handled_by.
    reset = client.patch(f"/api/bug-reports/{report_id}/status", json={"status": "new"})
    assert reset.status_code == 200
    assert reset.json()["status"] == "new"

    detail_after = client.get(f"/api/bug-reports/{report_id}").json()
    assert detail_after["handled_at"] is None
    row_after = db_session.get(BugReport, report_id)
    db_session.refresh(row_after)
    assert row_after.handled_by is None
    assert row_after.handled_at is None


def test_create_truncates_oversized_context_and_caps_string_fields(client, db_session):
    """context > 20000 tecken → {truncated: true}; view_id/page_path/note kapas."""
    login(client, "anna")

    oversized_context = {"blob": "x" * 21000}
    long_view = "v" * 200          # kolumn/kap: 80
    long_path = "/p/" + "a" * 500  # kolumn/kap: 300
    long_note = "n" * 3000         # kolumn/kap: 2000

    created = client.post(
        "/api/bug-reports",
        json={
            "events_json": EVENTS,
            "note": long_note,
            "view_id": long_view,
            "page_path": long_path,
            "context": oversized_context,
        },
    )
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]

    login(client, "root")
    detail = client.get(f"/api/bug-reports/{report_id}").json()

    assert detail["context"] == {
        "truncated": True,
        "note": "Kontexten var för stor och utelämnades.",
    }
    assert len(detail["view_id"]) == 80
    assert len(detail["page_path"]) == 300
    assert len(detail["note"]) == 2000


def test_create_keeps_small_context_verbatim(client, db_session):
    """Kontext under taket lagras oförändrad (kontroll mot trunkeringsgrenen)."""
    login(client, "anna")
    small_context = {"console_errors": ["boom"], "last_click": "#save"}
    created = client.post(
        "/api/bug-reports",
        json={"events_json": EVENTS, "note": "liten", "context": small_context},
    )
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]

    login(client, "root")
    detail = client.get(f"/api/bug-reports/{report_id}").json()
    assert detail["context"] == small_context

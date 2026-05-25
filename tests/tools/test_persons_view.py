from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]


def _function_body(source: str, name: str) -> str:
    match = re.search(rf"function {name}\([^)]*\) {{(?P<body>.*?)\n}}\n", source, re.S)
    assert match, f"Missing function {name}"
    return match.group("body")


def test_persons_view_uses_delete_button_without_active_toggle():
    frontend = ROOT / "app" / "frontend"
    persons_js = (frontend / "js" / "persons.js").read_text(encoding="utf-8")
    styles = (frontend / "css" / "styles.css").read_text(encoding="utf-8")

    assert "person-active-toggle" not in persons_js
    assert "data-active-toggle" not in persons_js
    assert "person-active-toggle.is-active" not in styles
    assert "person-active-toggle.is-inactive" not in styles
    assert "data-delete" in persons_js
    assert "Ta bort personen permanent?" in persons_js
    assert "Inaktivera" not in persons_js
    assert "api.del(`/api/persons/" in persons_js


def test_persons_view_has_ctrl_z_undo_for_person_changes():
    persons_js = (ROOT / "app" / "frontend" / "js" / "persons.js").read_text(encoding="utf-8")

    assert "personUndoStack" in persons_js
    assert "pushPersonUndo" in persons_js
    assert "undoLastPersonAction" in persons_js
    assert "installPersonUndoShortcut()" in persons_js
    assert 'e.key.toLowerCase() !== "z"' in persons_js
    assert "personPayloadFromSnapshot(action.before)" in persons_js


def test_persons_view_has_no_active_inactive_modes():
    frontend = ROOT / "app" / "frontend"
    persons_html = (frontend / "personer.html").read_text(encoding="utf-8")
    persons_js = (frontend / "js" / "persons.js").read_text(encoding="utf-8")
    styles = (frontend / "css" / "styles.css").read_text(encoding="utf-8")

    assert 'data-person-status="active"' not in persons_html
    assert 'data-person-status="inactive"' not in persons_html
    assert 'data-person-status="all"' not in persons_html
    assert 'id="show-inactive"' not in persons_html
    assert "statusMode" not in persons_js
    assert 'api.get(`/api/persons${query ? `?${query}` : ""}`)' in persons_js
    assert ".person-status-tabs" not in styles


def test_persons_view_exposes_optional_noman_field():
    frontend = ROOT / "app" / "frontend"
    persons_html = (frontend / "personer.html").read_text(encoding="utf-8")
    persons_js = (frontend / "js" / "persons.js").read_text(encoding="utf-8")

    assert '<th data-sort="noman">NoMan' in persons_html
    assert 'data-filter="noman"' in persons_html
    assert 'const filters = { name: "", noman: "", home_area: "", home_activity: "", sort_order: "" }' in persons_js
    assert 'case "noman": return (p.noman || "").toLowerCase();' in persons_js
    assert 'editText(tdNoman, p, "noman", p.noman || "", "NoMan")' in persons_js
    assert '{ key: "noman", label: "NoMan", required: false }' in persons_js
    assert 'noman: document.getElementById("m-noman").value.trim() || null' in persons_js


def test_persons_view_refetches_with_area_focus_to_prevent_super_user_leaks():
    persons_js = (ROOT / "app" / "frontend" / "js" / "persons.js").read_text(encoding="utf-8")

    load_body = _function_body(persons_js, "loadPersons")
    render_body = _function_body(persons_js, "renderRows")
    matches_body = _function_body(persons_js, "matchesAreaFocus")

    assert "const areaId = focusedAreaId();" in load_body
    assert 'params.set("area_id", String(areaId))' in load_body
    assert 'api.get(`/api/persons${query ? `?${query}` : ""}`)' in load_body
    assert 'api.get("/api/persons")' not in load_body
    assert "persons.filter(matchesAreaFocus).filter(passesFilter)" in render_body
    assert "Number(person?.home_area_id) === Number(areaId)" in matches_body
    assert 'window.addEventListener("flow:areaFocusChanged", () => loadPersons())' in persons_js
    assert 'window.addEventListener("flow:areaFocusChanged", () => renderRows())' not in persons_js


def test_planning_views_drag_person_names_to_persist_sort_order():
    frontend = ROOT / "app" / "frontend"
    schedule_js = (frontend / "js" / "schedule.js").read_text(encoding="utf-8")
    overview_js = (frontend / "js" / "overview.js").read_text(encoding="utf-8")
    styles = (frontend / "css" / "styles.css").read_text(encoding="utf-8")

    for source in (schedule_js, overview_js):
        assert "setupPersonOrderDrag()" in source
        assert "setupPersonOrderNameCell" in source
        assert 'canEditPage(user, "personSortOrder")' in source
        assert 'api.put("/api/persons/sort-order"' in source
        assert "Number(person?.home_area_id) === Number(state.currentUser?.area_id)" in source
        assert "Rensa personfiltret innan du sorterar personer." in source

    assert "person-order-draggable" in styles
    assert "person-order-drop-before" in styles
    assert "person-order-drop-after" in styles

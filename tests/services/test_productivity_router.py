from types import SimpleNamespace

from app.backend.routers import productivity as productivity_router
from app.backend.workflow_data import WorkflowResolution, WorkflowSourceEntry


def route_user():
    return SimpleNamespace(id=7, username="productivity-user", business_id=1)


def test_productivity_files_status_is_api_first_when_sources_are_available(monkeypatch):
    monkeypatch.setattr(productivity_router, "_productivity_business_code", lambda _db, _user: "STIGAMO")
    monkeypatch.setattr(productivity_router, "sources_available", lambda _keys: True)
    monkeypatch.setattr(
        productivity_router,
        "build_productivity_session_file_status",
        lambda *_args, **_kwargs: {
            "ready": False,
            "missing": ["pick", "trans", "pallet"],
            "kpi_loaded": False,
            "files": {
                "pick": {"key": "pick", "label": "Plocklogg Full", "required": True, "visible": True, "uploaded": False},
                "trans": {"key": "trans", "label": "Translogg", "required": True, "visible": True, "uploaded": False},
                "pallet": {"key": "pallet", "label": "Pallastningslogg", "required": True, "visible": True, "uploaded": False},
            },
        },
    )

    status = productivity_router.get_productivity_files(SimpleNamespace(session={}), user=route_user(), db=object())

    assert status["api_first"] is True
    assert status["ready"] is True
    assert status["missing"] == []
    assert status["kpi_loaded"] is True
    assert all(item["source"] == "api" for item in status["files"].values())


def test_productivity_report_uses_resolved_api_sources_and_audits(monkeypatch, tmp_path):
    source_files = {
        key: tmp_path / f"{key}.csv"
        for key in ("pick", "trans", "pallet", "kpi")
    }
    for key, path in source_files.items():
        path.write_text(f"{key}\n", encoding="utf-8")
    audits = []

    def fake_resolve(source_map, files, *, required_keys):
        assert source_map == {"pick": "pick", "trans": "trans", "pallet": "pallet", "kpi": "kpi"}
        assert required_keys == {"pick", "trans", "pallet", "kpi"}
        assert files == {}
        return WorkflowResolution(
            files=source_files,
            entries=[
                WorkflowSourceEntry(key=key, label=key, view=f"v_{key}", status="api", row_count=1)
                for key in source_files
            ],
        )

    monkeypatch.setattr(productivity_router, "_productivity_business_code", lambda _db, _user: "STIGAMO")
    monkeypatch.setattr(productivity_router, "find_kpi_file", lambda **_kwargs: (_ for _ in ()).throw(productivity_router.ProductivitySourceError("saknas")))
    monkeypatch.setattr(productivity_router, "resolve_sources", fake_resolve)
    monkeypatch.setattr(
        productivity_router,
        "build_productivity_report_from_files",
        lambda files, report_date=None: {"sources": {}, "summary": {"total_rows": len(files)}, "date": str(report_date or "")},
    )
    monkeypatch.setattr(productivity_router.audit, "log_and_commit", lambda *args, **kwargs: audits.append(kwargs["new_value"]))

    report = productivity_router.get_productivity(SimpleNamespace(session={}), user=route_user(), db=object())

    assert report["summary"]["total_rows"] == 4
    assert {entry["status"] for entry in report["source_status"]} == {"api"}
    assert audits == [
        {
            "status": "ok",
            "source_status": report["source_status"],
        }
    ]

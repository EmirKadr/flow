"""Regression: item_alias-hämtningen för förpacknings-uppdelningen ska smalnas av till
plockradernas item_num (batchat) så datakällans radtak aldrig kapar bort faktorer."""
from app.backend.routers import data_fetch as df


def test_distinct_item_nums_dedup_case_insensitive_and_skips_empty():
    rows = [
        {"item_num": "A"},
        {"item_num": "B"},
        {"item_num": "A"},        # dublett
        {"ITEM_NUM": "C"},         # annan casing
        {"item_num": ""},          # tom
        {"item_num": None},        # None
        {"other": "X"},            # saknar item_num
    ]
    assert df._distinct_item_nums(rows) == ["A", "B", "C"]


def _capture_fetch(monkeypatch, return_matching=True):
    captured = []

    def fake_fetch_rows(plan, error_id, tenant):
        captured.append(plan)
        terms = next((f for f in plan["filters"] if f["operator"] == "Terms"), None)
        if not return_matching or terms is None:
            return []
        return [{"item_num": i, "company": "GG", "conversion_factor": "10", "unit": "KRT"} for i in terms["value"]]

    monkeypatch.setattr(df, "_fetch_rows", fake_fetch_rows)
    return captured


def test_alias_fetch_scopes_by_company_and_item_terms(monkeypatch):
    captured = _capture_fetch(monkeypatch)
    plan = {"filters": [{"id": "company", "operator": "EQ", "value": "GG"}]}
    rows = [{"item_num": f"I{n}"} for n in range(3)]

    out = df._fetch_package_alias_rows(plan, rows, "e", "frey")

    assert len(out) == 3
    assert len(captured) == 1
    fields = {f["id"]: f for f in captured[0]["filters"]}
    assert fields["company"]["operator"] == "EQ" and fields["company"]["value"] == "GG"
    assert fields["item_num"]["operator"] == "Terms"
    assert set(fields["item_num"]["value"]) == {"I0", "I1", "I2"}
    assert captured[0]["view"] == df.PACKAGE_ALIAS_VIEW


def test_alias_fetch_batches_large_item_sets(monkeypatch):
    captured = _capture_fetch(monkeypatch, return_matching=False)
    total = df.PACKAGE_ALIAS_ITEM_BATCH * 2 + 5
    rows = [{"item_num": f"I{i}"} for i in range(total)]

    df._fetch_package_alias_rows({"filters": []}, rows, "e", "t")

    assert len(captured) == 3  # 400 + 400 + 5
    sizes = sorted(len(next(f for f in p["filters"] if f["operator"] == "Terms")["value"]) for p in captured)
    assert sizes == [5, df.PACKAGE_ALIAS_ITEM_BATCH, df.PACKAGE_ALIAS_ITEM_BATCH]


def test_alias_fetch_no_items_skips_api_entirely(monkeypatch):
    called = []
    monkeypatch.setattr(df, "_fetch_rows", lambda *a, **k: called.append(1) or [])
    assert df._fetch_package_alias_rows({"filters": []}, [], "e", "t") == []
    assert called == []  # drar aldrig hela item_alias

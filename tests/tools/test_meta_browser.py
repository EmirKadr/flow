"""Browsertest for observations-ID i Super User-vyn Meta."""

import json

import pytest

from tools import visual_smoke


playwright_api = pytest.importorskip("playwright.sync_api")
PlaywrightError = playwright_api.Error
expect = playwright_api.expect
sync_playwright = playwright_api.sync_playwright

pytestmark = pytest.mark.browser


@pytest.fixture(scope="module")
def local_server(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("meta-browser")
    base_url, server = visual_smoke.start_local_server(output_dir)
    try:
        yield base_url
    finally:
        server.close()


@pytest.fixture(scope="module")
def chromium_browser():
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except PlaywrightError as exc:
            message = str(exc)
            if "Executable doesn't exist" in message or "playwright install" in message:
                pytest.skip("Playwright Chromium is not installed")
            raise
        try:
            yield browser
        finally:
            browser.close()


def _fulfill_json(route, body):
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


def _shipment(observation_id, updated_at):
    return {
        "id": observation_id,
        "media_upload_id": observation_id + 100,
        "order_number": "ORDER",
        "shipment_number": "SHIPMENT",
        "username": "test-user",
        "customer_name": "Testkund",
        "pallet_id": "PALLET",
        "deviations": [],
        "uncertainty_notes": None,
        "analysis_status": "queued",
        "created_at": updated_at,
        "updated_at": updated_at,
        "video_filename": "video.mp4",
        "video_original_filename": "video.mp4",
        "video_duration_seconds": 10,
        "video_size_bytes": None,
        "video_size_label": "-",
        "video_hash": "video-hash",
        "record_hash": "record-hash",
        "video_url": f"/api/meta/uploads/{observation_id + 100}/content",
    }


def test_meta_shows_and_sorts_numeric_observation_id(local_server, chromium_browser):
    context = chromium_browser.new_context(locale="sv-SE")
    page = context.new_page()
    try:
        page.goto(f"{local_server}/login.html", wait_until="load")
        page.fill("#username", "admin")
        page.fill("#password", "admin123")
        page.click("button.primary")
        page.wait_for_url("**/index.html", timeout=15000)

        page.route(
            "**/api/meta/uploads?*",
            lambda route: _fulfill_json(route, {"items": []}),
        )
        page.route(
            "**/api/meta/shipment-observations?*",
            lambda route: _fulfill_json(
                route,
                {
                    "items": [
                        _shipment(10, "2026-07-10T10:00:00Z"),
                        _shipment(2, "2026-07-10T09:00:00Z"),
                    ]
                },
            ),
        )

        page.goto(f"{local_server}/meta.html", wait_until="load")
        page.wait_for_selector("#metaShipmentRows tr", timeout=15000)
        assert page.url.endswith("/meta.html")

        id_sort_button = page.locator('[data-sort-key="id"]')
        expect(id_sort_button).to_be_visible()
        expect(id_sort_button).to_contain_text("ID")

        id_column_index = id_sort_button.evaluate(
            "button => Array.from(button.closest('tr').children).indexOf(button.closest('th'))"
        )

        def visible_ids():
            return page.locator("#metaShipmentRows tr").evaluate_all(
                """(rows, columnIndex) => rows.map(
                    (row) => row.children[columnIndex].textContent.trim()
                )""",
                id_column_index,
            )

        assert visible_ids() == ["#10", "#2"]

        id_sort_button.click()
        assert visible_ids() == ["#2", "#10"]

        id_sort_button.click()
        assert visible_ids() == ["#10", "#2"]

        page.fill("#metaSearch", "2")
        assert visible_ids() == ["#2"]
    finally:
        context.close()

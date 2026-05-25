"""Measure perceived speed for flow's most important browser workflows.

The tool starts the same disposable local app stack as visual smoke tests,
drives the UI with Playwright, and writes a JSON report that can be kept as a
before/after baseline for future changes.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from openpyxl import Workbook

from tools import visual_smoke


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "performance"


@dataclass(frozen=True)
class BenchPage:
    name: str
    path: str
    ready_selector: str


@dataclass
class Measurement:
    name: str
    duration_ms: float
    ok: bool = True
    detail: dict[str, Any] = field(default_factory=dict)


BENCHMARK_PAGES: tuple[BenchPage, ...] = (
    BenchPage("bemanning", "/index.html", "#scheduleBody tr"),
    BenchPage("oversikt", "/overblick.html", "#overviewBody tr"),
    BenchPage("produktivitet", "/produktivitet.html", "#productivityStatus"),
    BenchPage("personer", "/personer.html", "#persons-body tr"),
    BenchPage("aktiviteter", "/aktiviteter.html", "#acts-body tr"),
    BenchPage("historik", "/historik.html", "#auditBody"),
    BenchPage("anvandare", "/anvandare.html", "#users-body tr"),
    BenchPage("verksamheter", "/verksamheter.html", "#businesses-body tr"),
    BenchPage("hamta-data", "/hamta-data.html", "#dataFetchPrompt"),
    BenchPage("uppladdningar", "/uppladdningar.html", ".allocation-file-slot"),
    BenchPage("bearbeta", "/bearbeta.html", ".allocation-flow-run"),
    BenchPage("dela", "/dela.html", '[data-flow-field="values"]'),
)


class PerformanceRun:
    def __init__(
        self,
        page,
        base_url: str,
        output_dir: Path,
        run_index: int,
        *,
        upload_entries: int = 18,
        upload_kb: int = 64,
    ) -> None:
        self.page = page
        self.base_url = base_url.rstrip("/")
        self.output_dir = output_dir
        self.run_index = run_index
        self.upload_entries = upload_entries
        self.upload_kb = upload_kb
        self.measurements: list[Measurement] = []
        self.console_errors: list[str] = []
        self.run_id = f"perf{int(time.time() * 1000)}_{run_index}"
        self.page.on("console", self._on_console)

    def _on_console(self, message) -> None:
        if message.type == "error":
            self.console_errors.append(message.text)

    def url(self, path: str) -> str:
        return self.base_url + path

    def measure(self, name: str, fn: Callable[[], Any], **detail: Any) -> Any:
        start = time.perf_counter()
        try:
            result = fn()
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            self.measurements.append(
                Measurement(
                    name=f"run{self.run_index}.{name}",
                    duration_ms=duration_ms,
                    ok=False,
                    detail={**detail, "error": str(exc), "console_errors": list(self.console_errors[-3:])},
                )
            )
            raise
        duration_ms = (time.perf_counter() - start) * 1000
        self.measurements.append(
            Measurement(
                name=f"run{self.run_index}.{name}",
                duration_ms=duration_ms,
                ok=True,
                detail={**detail, "session_cache_keys": self.session_api_cache_count()},
            )
        )
        return result

    def session_api_cache_count(self) -> int:
        try:
            return int(
                self.page.evaluate(
                    """() => Object.keys(sessionStorage)
                      .filter((key) => key.startsWith('flow-api-get-cache-v1:')).length"""
                )
            )
        except Exception:
            return 0

    def login_admin(self) -> None:
        self.page.goto(self.url("/login.html"), wait_until="domcontentloaded")
        self.page.fill("#username", "admin")
        self.page.fill("#password", "admin123")
        self.page.click("button.primary")
        self.page.wait_for_url("**/index.html", timeout=15000)
        self.page.wait_for_selector("#scheduleBody tr", timeout=15000)

    def goto_ready(self, page_def: BenchPage, phase: str) -> None:
        def run() -> None:
            self.page.goto(self.url(page_def.path), wait_until="domcontentloaded")
            self.page.wait_for_selector(page_def.ready_selector, timeout=20000)
            self.page.wait_for_timeout(50)

        self.measure(
            f"{phase}.nav.{page_def.name}",
            run,
            path=page_def.path,
            ready_selector=page_def.ready_selector,
        )

    def wait_for_background_prefetch(self, phase: str) -> None:
        def run() -> dict[str, Any]:
            try:
                self.page.wait_for_function("Boolean(window.flowBackgroundPrefetch?.waitForIdle)", timeout=3000)
                return self.page.evaluate("() => window.flowBackgroundPrefetch.waitForIdle(20000)")
            except Exception:
                return {"available": False}

        status = self.measure(f"{phase}.background_prefetch_idle", run)
        if isinstance(status, dict):
            self.measurements[-1].detail["prefetch_status"] = status

    def seed_allocation_upload_cache(self) -> None:
        content = "x" * max(1, self.upload_kb * 1024)
        base_entries = [
            "orders",
            "buffer",
            "overview",
            "dispatch",
            "saldo",
            "items",
            "not_putaway",
            "campaign",
            "prognos",
            "wms_booking",
            "wms_trans",
            "wms_pick",
            "productivity_pallet",
            "max_csv",
            "item_option",
        ]
        entries = [
            {
                "key": key if index < len(base_entries) else f"extra_{index}",
                "name": f"{key if index < len(base_entries) else f'extra_{index}'}-perf.csv",
                "content": content,
                "type": "text/csv",
                "lastModified": index + 1,
            }
            for index, key in enumerate(base_entries[: self.upload_entries])
        ]
        self.page.evaluate(
            """async ({ entries }) => {
              const db = await new Promise((resolve, reject) => {
                const request = indexedDB.open("flow-allokering-files", 1);
                request.onupgradeneeded = () => {
                  const db = request.result;
                  if (!db.objectStoreNames.contains("files")) {
                    db.createObjectStore("files", { keyPath: "key" });
                  }
                };
                request.onsuccess = () => resolve(request.result);
                request.onerror = () => reject(request.error);
              });
              await new Promise((resolve, reject) => {
                const tx = db.transaction("files", "readwrite");
                const store = tx.objectStore("files");
                for (const entry of entries) {
                  const blob = new Blob([entry.content], { type: entry.type });
                  store.put({
                    key: entry.key,
                    name: entry.name,
                    size: blob.size,
                    type: blob.type,
                    lastModified: entry.lastModified,
                    blob,
                  });
                }
                tx.oncomplete = () => resolve();
                tx.onerror = () => reject(tx.error);
              });
              db.close();
              localStorage.setItem("flow-allocation-file-metadata-v1", JSON.stringify({
                version: 1,
                at: Date.now(),
                files: entries.map((entry) => ({
                  key: entry.key,
                  name: entry.name,
                  size: entry.content.length,
                  type: entry.type,
                  lastModified: entry.lastModified,
                })),
              }));
            }""",
            {"entries": entries},
        )

    def run_navigation_sequence(self, phase: str, *, warm_first: bool) -> None:
        self.measure(f"{phase}.login_to_bemanning", self.login_admin)
        if warm_first:
            self.seed_allocation_upload_cache()
            self.wait_for_background_prefetch(phase)
        for page_def in BENCHMARK_PAGES:
            self.goto_ready(page_def, phase)

    def measure_area_toggle(self) -> None:
        self.page.goto(self.url("/index.html"), wait_until="domcontentloaded")
        self.page.wait_for_selector("#scheduleBody tr", timeout=15000)

        for index in range(4):
            def run() -> None:
                self.page.click("#area-focus-toggle")
                self.page.wait_for_selector("#scheduleTable", timeout=15000)
                self.page.wait_for_load_state("networkidle", timeout=8000)
                self.page.wait_for_timeout(50)

            self.measure(f"interaction.area_toggle.{index + 1}", run)

    def schedule_row(self):
        return self.page.locator("#scheduleBody tr", has_text="Visual MG VM")

    def schedule_cell(self, hour: int):
        return self.schedule_row().locator(f"td[data-hour='{hour}']")

    def drag_schedule_cell(self, source_hour: int, target_hour: int) -> None:
        source = self.schedule_cell(source_hour)
        target = self.schedule_cell(target_hour)
        source.scroll_into_view_if_needed()
        target.scroll_into_view_if_needed()
        source_handle = source.element_handle()
        target_handle = target.element_handle()
        if not source_handle or not target_handle:
            raise AssertionError("Could not locate schedule cells for drag fill")
        self.page.evaluate(
            """([source, target]) => {
              const sourceBox = source.getBoundingClientRect();
              const targetBox = target.getBoundingClientRect();
              const sourceX = sourceBox.left + 4;
              const sourceY = sourceBox.top + 4;
              const targetX = targetBox.left + targetBox.width / 2;
              const targetY = targetBox.top + targetBox.height / 2;
              source.dispatchEvent(new MouseEvent('mousedown', {
                bubbles: true,
                button: 0,
                clientX: sourceX,
                clientY: sourceY,
              }));
              document.dispatchEvent(new MouseEvent('mousemove', {
                bubbles: true,
                clientX: targetX,
                clientY: targetY,
              }));
              document.dispatchEvent(new MouseEvent('mouseup', {
                bubbles: true,
                button: 0,
                clientX: targetX,
                clientY: targetY,
              }));
            }""",
            [source_handle, target_handle],
        )

    def measure_schedule_editing(self) -> None:
        self.page.goto(self.url("/index.html"), wait_until="domcontentloaded")
        self.page.wait_for_selector("#scheduleTable", timeout=15000)
        self.page.evaluate("() => window.writeAreaFocus?.('MG')")
        self.page.fill("#nameFilter", "Visual MG VM")
        self.page.wait_for_selector("#scheduleBody tr:has-text('Visual MG VM')", timeout=15000)

        def select_activity() -> None:
            with self.page.expect_response(
                lambda response: "/api/schedule/cell" in response.url and response.request.method == "PUT",
                timeout=15000,
            ) as response_info:
                self.schedule_cell(8).locator("select").first.select_option(label="MG Plock")
            if not response_info.value.ok:
                raise RuntimeError(f"schedule cell update failed with {response_info.value.status}")
            self.page.wait_for_timeout(50)

        self.measure("interaction.schedule_select_activity", select_activity)

        def drag_fill() -> None:
            with self.page.expect_response(
                lambda response: "/api/schedule/cells" in response.url and response.request.method == "POST",
                timeout=15000,
            ) as response_info:
                self.drag_schedule_cell(8, 7)
            if not response_info.value.ok:
                raise RuntimeError(f"schedule drag-fill failed with {response_info.value.status}")
            self.page.wait_for_timeout(100)

        self.measure("interaction.schedule_drag_fill", drag_fill)

        def copy_paste() -> None:
            self.schedule_cell(8).click(position={"x": 8, "y": 8})
            self.page.keyboard.press("Control+C")
            with self.page.expect_response(
                lambda response: "/api/schedule/cell" in response.url and response.request.method == "PUT",
                timeout=15000,
            ) as response_info:
                self.schedule_cell(10).click(position={"x": 8, "y": 8})
                self.page.keyboard.press("Control+V")
            if not response_info.value.ok:
                raise RuntimeError(f"schedule copy-paste failed with {response_info.value.status}")
            self.page.wait_for_timeout(100)

        self.measure("interaction.schedule_copy_paste", copy_paste)

    def measure_split_run_and_copy(self) -> None:
        self.page.goto(self.url("/dela.html"), wait_until="domcontentloaded")
        self.page.wait_for_selector('[data-flow-field="values"]', timeout=15000)
        self.page.fill('[data-flow-field="values"]', "A\nB\nC\nD\nE\nF")
        self.page.fill('[data-flow-field="chunk_size"]', "2")

        def run_split() -> None:
            self.page.click('[data-run-flow="split-values"]')
            self.page.wait_for_selector(".allocation-result [data-copy-column]", timeout=15000)

        self.measure("interaction.split_values_run", run_split)

        def copy_column() -> None:
            self.page.locator(".allocation-result [data-copy-column]").nth(1).click()
            self.page.wait_for_selector(".toast.success", timeout=15000)

        self.measure("interaction.copy_result_column", copy_column)

    def _write_workbook(self, name: str, rows: list[list[Any]]) -> Path:
        workbook = Workbook()
        sheet = workbook.active
        for row in rows:
            sheet.append(row)
        path = self.output_dir / f"{name}-{self.run_id}.xlsx"
        workbook.save(path)
        return path

    def measure_imports(self) -> None:
        user_name = f"perf_user_{self.run_id}"
        activity_name = f"Perf Aktivitet {self.run_id}"
        person_name = f"Perf Person {self.run_id}"

        self.page.goto(self.url("/anvandare.html"), wait_until="domcontentloaded")
        self.page.wait_for_selector("#user-import-file", state="attached", timeout=15000)
        user_xlsx = self._write_workbook(
            "user-import",
            [["anvandarnamn", "namn", "roller", "omrade"], [user_name, "Perf User", "Visning", "Mestergruppen"]],
        )
        self.measure(
            "import.users_excel",
            lambda: (
                self.page.set_input_files("#user-import-file", str(user_xlsx)),
                self.page.get_by_text(user_name, exact=False).first.wait_for(timeout=15000),
            ),
        )

        self.page.goto(self.url("/aktiviteter.html"), wait_until="domcontentloaded")
        self.page.wait_for_selector("#activity-import-file", state="attached", timeout=15000)
        activity_xlsx = self._write_workbook(
            "activity-import",
            [["etikett", "omrade", "summeras som", "kategori", "farg", "sortering"], [activity_name, "Mestergruppen", None, "arbete", "#dbeafe", 92]],
        )
        self.measure(
            "import.activities_excel",
            lambda: (
                self.page.set_input_files("#activity-import-file", str(activity_xlsx)),
                self.page.get_by_text(activity_name, exact=False).first.wait_for(timeout=15000),
            ),
        )

        self.page.goto(self.url("/personer.html"), wait_until="domcontentloaded")
        self.page.wait_for_selector("#person-import-file", state="attached", timeout=15000)
        person_xlsx = self._write_workbook(
            "person-import",
            [["namn", "hemomrade", "huvudaktivitet", "sortering"], [person_name, "Mestergruppen", "MG VM", 993]],
        )
        self.measure(
            "import.persons_excel",
            lambda: (
                self.page.set_input_files("#person-import-file", str(person_xlsx)),
                self.page.get_by_text(person_name, exact=False).first.wait_for(timeout=15000),
            ),
        )

    def run_interactions(self) -> None:
        self.measure_area_toggle()
        self.measure_schedule_editing()
        self.measure_split_run_and_copy()
        self.measure_imports()


def summarize(measurements: list[Measurement]) -> dict[str, Any]:
    grouped: dict[str, list[float]] = {}
    failures = [asdict(item) for item in measurements if not item.ok]
    for item in measurements:
        if not item.ok:
            continue
        normalized = item.name.split(".", 1)[1] if item.name.startswith("run") else item.name
        grouped.setdefault(normalized, []).append(item.duration_ms)
    summary: dict[str, Any] = {}
    for name, values in sorted(grouped.items()):
        sorted_values = sorted(values)
        p95_index = min(len(sorted_values) - 1, int(round((len(sorted_values) - 1) * 0.95)))
        summary[name] = {
            "count": len(values),
            "median_ms": round(statistics.median(values), 1),
            "avg_ms": round(statistics.mean(values), 1),
            "min_ms": round(min(values), 1),
            "max_ms": round(max(values), 1),
            "p95_ms": round(sorted_values[p95_index], 1),
        }
    return {"measurements": summary, "failures": failures}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="Use an already running flow server instead of starting a disposable one.")
    parser.add_argument("--output", type=Path, default=None, help="Directory for report.json.")
    parser.add_argument("--runs", type=int, default=2, help="Number of repeated browser runs.")
    parser.add_argument("--headful", action="store_true", help="Show Chromium while measuring.")
    parser.add_argument("--upload-entries", type=int, default=18, help="IndexedDB upload entries seeded for upload-view benchmarks.")
    parser.add_argument("--upload-kb", type=int, default=64, help="Approximate size per seeded upload entry.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = args.output or DEFAULT_OUTPUT_ROOT / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    server = None
    if args.base_url:
      base_url = args.base_url.rstrip("/")
    else:
      base_url, server = visual_smoke.start_local_server(output_dir)

    sync_playwright, _timeout_error = visual_smoke._load_playwright()
    all_measurements: list[Measurement] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not args.headful)
            try:
                for run_index in range(1, max(1, args.runs) + 1):
                    context = browser.new_context(locale="sv-SE", viewport={"width": 1440, "height": 1000})
                    context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base_url)
                    page = context.new_page()
                    try:
                        cold = PerformanceRun(page, base_url, output_dir, run_index, upload_entries=args.upload_entries, upload_kb=args.upload_kb)
                        cold.run_navigation_sequence("cold", warm_first=False)
                        all_measurements.extend(cold.measurements)
                    finally:
                        context.close()

                    context = browser.new_context(locale="sv-SE", viewport={"width": 1440, "height": 1000})
                    context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base_url)
                    page = context.new_page()
                    try:
                        warm = PerformanceRun(page, base_url, output_dir, run_index, upload_entries=args.upload_entries, upload_kb=args.upload_kb)
                        warm.run_navigation_sequence("warm", warm_first=True)
                        warm.run_interactions()
                        all_measurements.extend(warm.measurements)
                    finally:
                        context.close()
            finally:
                browser.close()
    finally:
        if server:
            server.close()

    report = {
        "tool": "tools.performance_benchmark",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "base_url": base_url,
        "runs": max(1, args.runs),
        "upload_entries": args.upload_entries,
        "upload_kb": args.upload_kb,
        "raw": [asdict(item) for item in all_measurements],
        "summary": summarize(all_measurements),
    }
    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Performance report: {report_path}")
    if report["summary"]["failures"]:
        print(f"Failures: {len(report['summary']['failures'])}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

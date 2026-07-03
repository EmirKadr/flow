from pathlib import Path

from app.backend.models import PersonProductivityDaily, ScheduleCell, UserWaitMetric
from tools.frontend_sources import read_overview_frontend, read_persons_frontend, read_productivity_overview_frontend


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "app" / "frontend"


COMMON_SCRIPT_FILES = [
    "js/common/foundation.js",
    "js/common/telemetry.js",
    "js/common/demo_prefetch_init.js",
    "js/common.js",
]
ALLOCATION_SCRIPT_FILES = [
    "js/allocation/state.js",
    "js/allocation/state_carrier_clusters.js",
    "js/allocation/state_filters.js",
    "js/allocation/api.js",
    "js/allocation/boot.js",
    "js/allocation/map_settings.js",
    "js/allocation/map_settings_layout.js",
    "js/allocation/settings_view.js",
    "js/allocation/settings_staffing.js",
    "js/allocation/settings_finance.js",
    "js/allocation/settings_finance_check.js",
]
SCHEDULE_SCRIPT_FILES = [
    "js/schedule/state.js",
    "js/schedule/ui_core.js",
    "js/schedule/data.js",
    "js/schedule/summary.js",
    "js/schedule/calculator.js",
]


def read_frontend(relative: str) -> str:
    return (FRONTEND / relative).read_text(encoding="utf-8")


def read_sources(paths: list[str]) -> str:
    return "\n".join(read_frontend(path) for path in paths)


def index_columns(model) -> dict[str, tuple[str, ...]]:
    return {
        index.name: tuple(column.name for column in index.columns)
        for index in model.__table__.indexes
    }


def test_wait_metric_pipeline_measures_views_api_cache_hits_and_main_thread():
    common = read_sources(COMMON_SCRIPT_FILES)
    api_js = read_frontend("js/api.js")
    healthcheck = (ROOT / "app" / "backend" / "routers" / "healthcheck.py").read_text(encoding="utf-8")
    analytics = read_frontend("js/analytics.js")

    assert 'COMMON_WAIT_METRIC_REPORT_PATH = "/api/healthcheck/wait-metrics"' in common
    assert "recordWaitMetric(metric = {})" in common
    assert 'event_type: "view_load"' in common
    assert "reportPageLoadWaitMetric(activePage)" in common
    assert 'event_type: "client_long_task"' in common
    assert "PerformanceObserver" in common
    assert "fetch(COMMON_WAIT_METRIC_REPORT_PATH" in common
    assert "Telemetri far aldrig sega ner anvandaren" in common

    assert "reportApiWaitMetric(path, method, requestStartedAt" in api_js
    assert "cache_hit: true" in api_js
    assert "shared_in_flight: true" in api_js
    assert "WAIT_METRIC_REPORT_PATH" in api_js
    assert "shouldLogApiUserEvent" in api_js

    assert '"by_view": summarize_group' in healthcheck
    assert '"by_target": summarize_group' in healthcheck
    assert '"by_event": summarize_group' in healthcheck
    assert '"slow_events": [metric_payload(row) for row in slow]' in healthcheck
    assert "/api/healthcheck/wait-metrics/summary" in analytics


def test_critical_user_waits_are_cached_prefetched_or_backgrounded():
    common = read_sources(COMMON_SCRIPT_FILES)
    personal = read_frontend("js/personal_views.js")
    schedule = read_sources(SCHEDULE_SCRIPT_FILES)
    allocation = read_sources(ALLOCATION_SCRIPT_FILES)
    persons = read_persons_frontend()
    productivity_overview = read_productivity_overview_frontend()
    personal_router = (ROOT / "app" / "backend" / "routers" / "personal.py").read_text(encoding="utf-8")

    assert "PERSONAL_PRODUCTIVITY_CACHE_TTL_MS = 25 * 1000" in personal
    assert "/api/personal/productivity" in personal
    assert "cacheTtlMs: PERSONAL_PRODUCTIVITY_CACHE_TTL_MS" in personal
    assert "PERSONAL_SCHEDULE_CACHE_TTL_MS = 25 * 1000" in personal
    assert "cacheTtlMs: PERSONAL_SCHEDULE_CACHE_TTL_MS" in personal
    assert "person_productivity_daily_report_if_current" in personal_router
    assert "person_productivity_period_stats_if_current" in personal_router
    assert "_PERSONAL_PRODUCTIVITY_REPORT_CACHE_TTL_SECONDS = 2 * 60" in personal_router
    assert "_build_cached_personal_productivity_report" in personal_router
    assert "enqueueBackgroundPrefetch(`/api/personal/productivity?date=${dateValue}`, 25 * 1000)" not in common
    assert "/api/personal/persons" in common
    assert "`/api/personal/schedule?year=${year}&week=${week}`" in common

    assert "/api/schedule/productivity-summary" in schedule
    assert "cacheTtlMs: 60 * 1000" in schedule
    assert "api.get(scheduleUrl(null), { signal: controller.signal, cacheTtlMs: 25 * 1000 })" in schedule

    assert "function allocationDefaultGetCacheTtlMs" in allocation
    assert 'text.includes("/api/allokering/process-matrix")' in allocation
    assert 'text.includes("/api/allokering/ytgenerering-map-layout")' in allocation
    assert 'text.includes("/api/allokering/ytgenerering-location-options")' in allocation
    assert 'text.includes("/api/allokering/flows")' in allocation
    assert 'text.includes("/api/coredata/files")' in allocation
    assert "cacheTtlMs ? { ...options, cacheTtlMs } : options" in allocation
    assert "enqueueBackgroundPrefetch(\"/api/allokering/process-matrix\", 30 * 1000)" in common
    assert "enqueueBackgroundPrefetch(\"/api/allokering/ytgenerering-map-layout?include_options=false\", 30 * 1000)" in common

    assert "PERSON_PRODUCTIVITY_CACHE_TTL_MS" in persons
    assert "cacheTtlMs: PERSON_PRODUCTIVITY_CACHE_TTL_MS" in persons
    assert "PRODUCTIVITY_OVERVIEW_CACHE_TTL_MS" in productivity_overview
    assert "cacheTtlMs: PRODUCTIVITY_OVERVIEW_CACHE_TTL_MS" in productivity_overview


def test_heavy_views_render_incrementally_and_cancel_stale_work():
    common = read_sources(COMMON_SCRIPT_FILES)
    schedule = read_sources(SCHEDULE_SCRIPT_FILES)
    allocation = read_sources(ALLOCATION_SCRIPT_FILES)
    overview = read_overview_frontend()
    productivity_overview = read_productivity_overview_frontend()

    assert "requestIdleCallback" in common
    assert "BACKGROUND_PREFETCH_INITIAL_DELAY_MS" in common
    assert "setTimeout(scheduleNextBackgroundPrefetch, BACKGROUND_PREFETCH_INITIAL_DELAY_MS)" in common

    assert "function renderScheduleFromCache" in schedule
    assert "if (renderScheduleFromCache())" in schedule
    assert "AbortController" in schedule
    assert "requestSeq" in schedule
    assert "Promise.all([" in schedule
    assert "scheduleNextScheduleRevalidate" in schedule

    assert "restoreAllocationBootData()" in allocation
    assert "if (restoredFromCache) renderAllocationPage()" in allocation
    assert "Promise.allSettled([" in allocation
    assert "preloadAllocationUploadsData" in allocation

    assert "document.createDocumentFragment()" in overview
    assert "AbortController" in overview

    assert "renderProductivityOverviewShell" in productivity_overview
    assert "waitForProductivityOverviewPaint" in productivity_overview
    assert "productivityOverviewLoadToken" in productivity_overview
    assert "setProductivityOverviewLoading(\"Hämtar produktivitetsöversikt" in productivity_overview
    assert "setProductivityOverviewLoading(\"Beräknar och ritar produktivitet" in productivity_overview
    assert "  void loadProductivityOverview();\n}" in productivity_overview


def test_same_server_heavy_external_work_is_offloaded_from_async_routes():
    # Routern ar splittad: endpoints i allocation.py, hjalpare/cachar i
    # allocation_helpers.py. Kontraktet galler helheten.
    allocation = (ROOT / "app" / "backend" / "routers" / "allocation.py").read_text(encoding="utf-8")
    allocation += (ROOT / "app" / "backend" / "routers" / "allocation_helpers.py").read_text(encoding="utf-8")
    data_fetch = (ROOT / "app" / "backend" / "routers" / "data_fetch.py").read_text(encoding="utf-8")
    assistant = (ROOT / "app" / "backend" / "routers" / "assistant.py").read_text(encoding="utf-8")
    audit_logs = (ROOT / "app" / "backend" / "routers" / "audit_logs.py").read_text(encoding="utf-8")
    meta_uploads = (ROOT / "app" / "backend" / "routers" / "meta_uploads.py").read_text(encoding="utf-8")

    assert "from starlette.concurrency import run_in_threadpool" in allocation
    assert "async def run_flow" in allocation
    assert "await run_in_threadpool(" in allocation
    assert "bridge.run_flow_handler" in allocation
    assert "_cached_ytgenerering_location_option_rows" in allocation
    assert "_YTGENERERING_LOCATION_OPTIONS_CACHE" in allocation
    assert "_YTGENERERING_LOCATION_OPTIONS_MISSING_CACHE" in allocation
    assert "from starlette.concurrency import run_in_threadpool" in data_fetch
    assert "await run_in_threadpool(_call_minimax" in data_fetch
    assert "await run_in_threadpool(_fetch_rows" in data_fetch
    assert "from starlette.concurrency import run_in_threadpool" in assistant
    assert "await run_in_threadpool(_call_minimax" in assistant
    assert "from starlette.concurrency import run_in_threadpool" in audit_logs
    assert "await run_in_threadpool(_call_minimax" in audit_logs
    assert "BackgroundTasks" in meta_uploads
    assert "background_tasks.add_task(run_meta_analysis_background" in meta_uploads


def test_database_indexes_support_wait_metrics_and_snapshot_reads():
    wait_indexes = index_columns(UserWaitMetric)
    productivity_indexes = index_columns(PersonProductivityDaily)
    schedule_indexes = index_columns(ScheduleCell)
    migration = (ROOT / "app" / "alembic" / "versions" / "0040_wait_metric_indexes.py").read_text(encoding="utf-8")

    assert wait_indexes["ix_user_wait_metrics_created_at"] == ("created_at",)
    assert wait_indexes["ix_user_wait_metrics_business_created"] == ("business_id", "created_at")
    assert wait_indexes["ix_user_wait_metrics_user_created"] == ("user_id", "created_at")
    assert wait_indexes["ix_user_wait_metrics_event_created"] == ("event_type", "created_at")
    assert wait_indexes["ix_user_wait_metrics_view_target"] == ("view_id", "target")

    assert productivity_indexes["ix_person_productivity_daily_lookup"] == (
        "business_id",
        "snapshot_date",
        "person_id",
        "row_type",
    )
    assert productivity_indexes["ix_person_productivity_daily_process"] == (
        "business_id",
        "process_key",
        "snapshot_date",
    )
    assert schedule_indexes["ix_schedule_cells_ywd_person_hour"] == ("year", "week", "weekday", "person_id", "hour")

    assert "0040_wait_metric_indexes" in migration
    assert '"ix_user_wait_metrics_business_created"' in migration
    assert '"ix_user_wait_metrics_user_created"' in migration
    assert '"ix_user_wait_metrics_event_created"' in migration

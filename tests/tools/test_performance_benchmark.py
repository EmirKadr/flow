from tools import performance_benchmark


def test_performance_benchmark_covers_navigation_uploads_imports_and_interactions():
    page_names = {page.name for page in performance_benchmark.BENCHMARK_PAGES}

    assert {
        "bemanning",
        "oversikt",
        "produktivitet",
        "personer",
        "aktiviteter",
        "historik",
        "anvandare",
        "verksamheter",
        "hamta-data",
        "uppladdningar",
        "bearbeta",
        "dela",
    } <= page_names

    source = performance_benchmark.PerformanceRun
    assert hasattr(source, "wait_for_background_prefetch")
    assert hasattr(source, "measure_area_toggle")
    assert hasattr(source, "measure_schedule_editing")
    assert hasattr(source, "measure_split_run_and_copy")
    assert hasattr(source, "measure_imports")


def test_performance_benchmark_default_args_are_repeatable_and_not_one_shot():
    args = performance_benchmark.parse_args([])

    assert args.runs >= 2
    assert args.upload_entries >= 10
    assert args.upload_kb >= 32

from tools import healthcheck


def test_healthcheck_cli_supports_report_and_waits_commands():
    report_args = healthcheck.parse_args(["report", "--local", "--no-render", "--skip-db"])
    waits_args = healthcheck.parse_args(["waits", "--local", "--period", "7d", "--query", "api"])

    assert report_args.command == "report"
    assert report_args.local is True
    assert report_args.include_render is False
    assert report_args.skip_db is True
    assert waits_args.command == "waits"
    assert waits_args.period == "7d"
    assert waits_args.query == "api"


def test_healthcheck_cli_prints_wait_summary(capsys):
    healthcheck.print_waits({
        "count": 2,
        "avg_ms": 150,
        "p95_ms": 300,
        "by_target": [{"key": "GET /api/audit", "p95_ms": 300, "count": 2}],
        "analysis": [{"severity": "ok", "message": "Friskt"}],
    })

    output = capsys.readouterr().out
    assert "Matningar: 2" in output
    assert "GET /api/audit" in output

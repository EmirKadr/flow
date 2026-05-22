import json
from pathlib import Path

import pytest


pytest.importorskip("pandas")

from warehouse_tools import cli as warehouse_cli  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
WAREHOUSE_TESTDATA = ROOT / "testdata" / "warehouse_tools"


def test_warehouse_cli_lists_flows(capsys):
    result = warehouse_cli.main(["list-flows"])
    output = capsys.readouterr().out

    assert result == 0
    assert "allocate | Allokering | Allokering" in output
    assert "split-values | Dela" in output


def test_warehouse_cli_runs_split_values_and_writes_outputs(tmp_path, capsys):
    pytest.importorskip("openpyxl")
    out_dir = tmp_path / "split"

    result = warehouse_cli.main(
        [
            "split-values",
            "--values",
            "A\nB\nC\nD\nE",
            "--chunk-size",
            "2",
            "--out",
            str(out_dir),
            "--format",
            "both",
            "--json",
        ]
    )
    output = capsys.readouterr().out

    payload = json.loads(output)
    assert result == 0
    assert payload["summary"] == {"Antal v\u00e4rden": 5, "Antal kolumner": 3, "Per kolumn": 2}
    assert payload["tables"][0]["key"] == "report"
    assert (out_dir / "report.csv").read_text(encoding="utf-8-sig").splitlines() == [
        "Kolumn 1,Kolumn 2,Kolumn 3",
        "A,C,E",
        "B,D,",
    ]
    assert (out_dir / "split-values.xlsx").is_file()
    assert (out_dir / "summary.json").is_file()


def test_warehouse_cli_validates_scenarios_with_relative_paths(tmp_path, capsys):
    values = tmp_path / "values.txt"
    values.write_text("A\nB\nC\n", encoding="utf-8")
    scenario = tmp_path / "scenario.json"
    scenario.write_text(
        json.dumps(
            {
                "flow": "split-values",
                "files": {"values_file": "values.txt"},
                "params": {"chunk_size": "2"},
            }
        ),
        encoding="utf-8",
    )

    result = warehouse_cli.main(["validate-scenario", str(scenario)])

    assert result == 0
    assert capsys.readouterr().out.strip() == "OK"


def test_warehouse_cli_can_auto_match_file_input(tmp_path):
    orders = next(WAREHOUSE_TESTDATA.glob("v_ask_customer_order_details_all-*.csv"), None)
    if orders is None:
        pytest.skip("Warehouse orderfixture saknas.")

    args = warehouse_cli.parse_args(["ordersaldo", "--auto-file", str(orders), "--out", str(tmp_path)])
    files, params = warehouse_cli._files_params_from_dynamic_args(  # noqa: SLF001
        warehouse_cli._flow_by_id("ordersaldo"),  # noqa: SLF001
        args,
    )
    warehouse_cli._apply_auto_files(warehouse_cli._flow_by_id("ordersaldo"), files, args.auto_file)  # noqa: SLF001

    assert files == {"orders": orders}
    assert params == {}


def test_warehouse_cli_validate_scenario_reports_missing_required_file(tmp_path, capsys):
    scenario = tmp_path / "scenario.json"
    scenario.write_text(json.dumps({"flow": "allocate", "files": {"orders": "saknas.csv"}}), encoding="utf-8")

    result = warehouse_cli.main(["validate-scenario", str(scenario)])
    captured = capsys.readouterr()

    assert result == 1
    assert "Filen finns inte for orders" in captured.err
    assert "Saknar fil: buffer" in captured.err

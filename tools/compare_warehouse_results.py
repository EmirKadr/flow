"""Compare warehouse result tables from CSV/XLSX exports.

The tool is built for Flow-vs-Allokera parity checks. It normalizes the common
export noise first: empty NaN-like values become blank strings and integer-like
numbers such as 1.0 compare equal to 1.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


_PANDAS = None


def _require_pandas():
    global _PANDAS
    if _PANDAS is not None:
        return _PANDAS
    try:
        import pandas as pd  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise SystemExit("pandas saknas. Installera app/requirements.txt for att jamfora tabeller.") from exc
    _PANDAS = pd
    return pd


def _read_csv(path: Path):
    pd = _require_pandas()
    errors: list[str] = []
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return pd.read_csv(path, sep=None, engine="python", dtype=object, keep_default_na=False, encoding=encoding)
        except UnicodeDecodeError as exc:
            errors.append(str(exc))
    raise SystemExit(f"Kunde inte lasa CSV: {path}\n" + "\n".join(errors[-2:]))


def _read_excel(path: Path, sheet: str | int | None):
    pd = _require_pandas()
    selected_sheet: str | int = 0 if sheet is None else sheet
    return pd.read_excel(path, sheet_name=selected_sheet, dtype=object, keep_default_na=False)


def read_table(path: str | Path, *, sheet: str | int | None = None):
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        return _read_excel(source, sheet)
    return _read_csv(source)


def _decimal_text(value: str) -> str | None:
    text = value.strip()
    if not text:
        return ""
    numeric = text.replace(",", ".") if "," in text and "." not in text else text
    if not re.fullmatch(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", numeric):
        return None
    if "." not in numeric and "e" not in numeric.lower():
        return text
    try:
        decimal = Decimal(numeric)
    except InvalidOperation:
        return None
    if decimal == decimal.to_integral_value():
        return str(decimal.quantize(Decimal(1)))
    normalized = format(decimal.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def normalize_cell(value: object) -> str:
    pd = _require_pandas()
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        return str(int(value)) if value.is_integer() else f"{value:g}"
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if hasattr(pd, "Timestamp") and isinstance(value, pd.Timestamp):
        return "" if pd.isna(value) else value.isoformat(sep=" ")
    text = str(value).strip()
    if text.lower() in {"nan", "nat", "none"}:
        return ""
    decimal_text = _decimal_text(text)
    return text if decimal_text is None else decimal_text


def _split_names(items: list[str] | None) -> list[str]:
    names: list[str] = []
    for item in items or []:
        names.extend(part.strip() for part in item.split(",") if part.strip())
    return names


def _drop_ignored_columns(frame, ignored: list[str]):
    if not ignored:
        return frame
    existing = [column for column in ignored if column in frame.columns]
    return frame.drop(columns=existing)


def _sort_frame(frame, sort_by: list[str], side: str):
    if not sort_by:
        return frame.reset_index(drop=True)
    missing = [column for column in sort_by if column not in frame.columns]
    if missing:
        raise SystemExit(f"{side} saknar sorteringskolumn: {', '.join(missing)}")
    sorted_frame = frame.copy()
    temp_columns = []
    for index, column in enumerate(sort_by):
        temp_column = f"__flow_compare_sort_{index}"
        sorted_frame[temp_column] = sorted_frame[column].map(normalize_cell)
        temp_columns.append(temp_column)
    sorted_frame = sorted_frame.sort_values(temp_columns, kind="mergesort").drop(columns=temp_columns)
    return sorted_frame.reset_index(drop=True)


def _normalized_rows(frame) -> list[list[str]]:
    return [
        [normalize_cell(value) for value in row]
        for row in frame.itertuples(index=False, name=None)
    ]


def compare_tables(left, right, *, sort_by: list[str] | None = None, ignore_columns: list[str] | None = None, sample: int = 20) -> dict[str, Any]:
    sort_by = sort_by or []
    ignore_columns = ignore_columns or []
    left = _sort_frame(_drop_ignored_columns(left, ignore_columns), sort_by, "left")
    right = _sort_frame(_drop_ignored_columns(right, ignore_columns), sort_by, "right")

    left_columns = [str(column) for column in left.columns]
    right_columns = [str(column) for column in right.columns]
    left_rows = _normalized_rows(left)
    right_rows = _normalized_rows(right)

    differences: list[dict[str, Any]] = []
    max_rows = min(len(left_rows), len(right_rows))
    max_cols = min(len(left_columns), len(right_columns))
    diff_count = 0
    diff_by_column: dict[str, int] = {}
    for row_index in range(max_rows):
        for column_index in range(max_cols):
            left_value = left_rows[row_index][column_index]
            right_value = right_rows[row_index][column_index]
            if left_value == right_value:
                continue
            diff_count += 1
            column = left_columns[column_index] if column_index < len(left_columns) else str(column_index)
            diff_by_column[column] = diff_by_column.get(column, 0) + 1
            if len(differences) < sample:
                differences.append({
                    "row": row_index + 2,
                    "column": column,
                    "left": left_value,
                    "right": right_value,
                })

    shape_equal = left.shape == right.shape
    columns_equal = left_columns == right_columns
    equal = shape_equal and columns_equal and diff_count == 0
    return {
        "equal": equal,
        "left_shape": [int(left.shape[0]), int(left.shape[1])],
        "right_shape": [int(right.shape[0]), int(right.shape[1])],
        "shape_equal": shape_equal,
        "columns_equal": columns_equal,
        "left_columns": left_columns,
        "right_columns": right_columns,
        "cell_differences": diff_count,
        "differences_by_column": dict(sorted(diff_by_column.items(), key=lambda item: (-item[1], item[0]))),
        "sample_differences": differences,
    }


def compare_files(
    left_path: str | Path,
    right_path: str | Path,
    *,
    left_sheet: str | int | None = None,
    right_sheet: str | int | None = None,
    sort_by: list[str] | None = None,
    ignore_columns: list[str] | None = None,
    sample: int = 20,
) -> dict[str, Any]:
    left = read_table(left_path, sheet=left_sheet)
    right = read_table(right_path, sheet=right_sheet)
    result = compare_tables(left, right, sort_by=sort_by, ignore_columns=ignore_columns, sample=sample)
    result["left_path"] = str(left_path)
    result["right_path"] = str(right_path)
    return result


def _print_text(result: dict[str, Any]) -> None:
    if result["equal"]:
        print("OK: tabellerna ar identiska efter exportnormalisering.")
        print(f"Rader/kolumner: {result['left_shape'][0]} x {result['left_shape'][1]}")
        return
    print("Skillnader hittades.")
    print(f"Left:  {result['left_shape'][0]} rader x {result['left_shape'][1]} kolumner")
    print(f"Right: {result['right_shape'][0]} rader x {result['right_shape'][1]} kolumner")
    if not result["columns_equal"]:
        print("Kolumner skiljer sig.")
    if result["cell_differences"]:
        print(f"Cellskillnader: {result['cell_differences']}")
        for column, count in list(result["differences_by_column"].items())[:10]:
            print(f"- {column}: {count}")
    for item in result["sample_differences"]:
        print(f"rad {item['row']} / {item['column']}: left={item['left']!r} right={item['right']!r}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", required=True, help="Flow-resultat, CSV/XLSX.")
    parser.add_argument("--right", required=True, help="Sanningsfil/jamforelsefil, CSV/XLSX.")
    parser.add_argument("--left-sheet", help="Excelblad for --left. Default ar forsta bladet.")
    parser.add_argument("--right-sheet", help="Excelblad for --right. Default ar forsta bladet.")
    parser.add_argument("--sort-by", action="append", help="Kolumn(er) att sortera pa fore jamforelse, komma-separerat.")
    parser.add_argument("--ignore-column", action="append", help="Kolumn(er) att ignorera, komma-separerat.")
    parser.add_argument("--sample", type=int, default=20, help="Antal exempelrader att visa.")
    parser.add_argument("--json", action="store_true", help="Skriv maskinlasbar JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = compare_files(
        args.left,
        args.right,
        left_sheet=args.left_sheet,
        right_sheet=args.right_sheet,
        sort_by=_split_names(args.sort_by),
        ignore_columns=_split_names(args.ignore_column),
        sample=args.sample,
    )
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print_text(result)
    return 0 if result["equal"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

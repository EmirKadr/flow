def open_path(path: str) -> None:
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Kunde inte öppna filen automatiskt: {exc}") from exc


def excel_writer_engine() -> str:
    if importlib.util.find_spec("openpyxl"):
        return "openpyxl"
    if importlib.util.find_spec("xlsxwriter"):
        return "xlsxwriter"
    raise RuntimeError("Saknar Excel-skrivare (installera openpyxl eller xlsxwriter).")


def _safe_excel_sheet_name(label: str) -> str:
    cleaned = re.sub(r"[\[\]:*?/\\]+", " ", str(label or "Sheet1"))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:31] or "Sheet1"


def _safe_excel_file_label(label: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(label or "excel"))
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._")
    return (cleaned or "excel")[:80]


def write_table_to_excel(table, label: str, *, include_header: bool = True) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{_safe_excel_file_label(label)}.xlsx")
    path = tmp.name
    tmp.close()
    sheet_name = _safe_excel_sheet_name(label)

    if _is_simple_table(table):
        try:
            from openpyxl import Workbook
        except Exception as exc:  # noqa: BLE001
            raise AllocationBridgeUnavailable("Openpyxl saknas for Excel-export.") from exc

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = sheet_name
        if include_header:
            sheet.append([_cell(column) for column in table.columns])
        for row in table.rows:
            sheet.append([_cell(value) for value in row])
        workbook.save(path)
        return path

    import pandas as pd  # type: ignore

    df = table if isinstance(table, pd.DataFrame) else pd.DataFrame(table)
    with pd.ExcelWriter(path, engine=excel_writer_engine()) as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False, header=include_header)
    return path


def open_df_in_excel_without_header(df, label: str) -> str:
    path = write_table_to_excel(df, label, include_header=False)
    open_path(path)
    return path


def open_simple_table_in_excel_without_header(table, label: str) -> str:
    path = write_table_to_excel(table, label, include_header=False)
    open_path(path)
    return path



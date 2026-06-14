async def form_to_flow_payload(form, *, cache_scope: str | None = None) -> tuple[dict[str, Path], dict[str, str], list[Path]]:
    files: dict[str, Path] = {}
    params: dict[str, str] = {}
    temp_paths: list[Path] = []
    for key, value in form.multi_items():
        if isinstance(value, StarletteUploadFile):
            if value.filename:
                upload_cache_key = f"{cache_scope or 'global'}:{key}:{value.filename}"
                path = await save_upload(value, cache=True, cache_key=upload_cache_key)
                files[key] = path
        elif isinstance(value, str) and value.strip() != "":
            params[key] = value
    return files, params, temp_paths


def _friendly_flow_error_message(exc: Exception) -> str:
    raw = str(exc).strip()
    if raw == "No objects to concatenate":
        return (
            "Flödet fick inga rader att sammanställa. Kontrollera att rätt filer är inlagda "
            "och att vald toggle/filter inte filtrerar bort allt."
        )
    return raw or "Flödet kunde inte köras."


def run_flow_handler(
    flow_id: str,
    files: dict,
    params: dict,
    *,
    default_max_csv_path: str | Path | None = None,
) -> dict:
    flow = _native_flows().FLOW_BY_ID.get(flow_id)
    if flow is None:
        if flow_id not in _catalog().FLOW_BY_ID:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Okänt flöde: {flow_id}")
        _engine_module, flows_module = require_available()
        flow = flows_module.FLOW_BY_ID.get(flow_id)
    if flow is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Okänt flöde: {flow_id}")
    handler_params = dict(params or {})
    if default_max_csv_path and "max_csv" not in files:
        handler_params[DEFAULT_MAX_CSV_PARAM] = str(default_max_csv_path)
    try:
        result = flow["handler"](files, handler_params)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Allocation flow failed flow_id=%s", flow_id)
        message = _friendly_flow_error_message(exc)
        raw_message = str(exc).strip()
        detail = {
            "message": message,
            "error_code": "allocation_flow_failed",
            "error_type": type(exc).__name__,
        }
        if raw_message and raw_message != message:
            detail["technical_message"] = raw_message
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=detail,
        ) from exc

    tables = result.get("tables", [])
    artifacts = result.get("artifacts", {}) or {}
    download_files = result.get("download_files", {}) or {}
    _cleanup_sessions()
    session_id = uuid.uuid4().hex
    table_files = {key: _write_session_table(session_id, key, df) for key, _label, df in tables}
    SESSIONS[session_id] = {
        "flow_id": flow_id,
        "created_at": time.time(),
        "tables": table_files,
        "labels": {key: label for key, label, _df in tables},
        "artifacts": _store_session_artifacts(session_id, artifacts),
        "download_files": _store_session_download_files(session_id, download_files),
        "size_bytes": sum(int(ref.get("size_bytes") or 0) for ref in table_files.values()),
    }
    _cleanup_sessions()
    return {
        "flow_id": flow_id,
        "session_id": session_id,
        "summary": result.get("summary", {}),
        "display_summary": result.get("display_summary"),
        "tables": [
            {"key": key, "label": label, "table": df_to_table(df)}
            for key, label, df in tables
        ],
        "text": result.get("text"),
        "maps": result.get("maps") or [],
        "carrier_clusters": result.get("carrier_clusters"),
        "log": result.get("log", []),
        "artifact_keys": sorted(artifacts),
        "auto_downloads": result.get("auto_downloads") or [],
    }


def open_excel_result(req: OpenAllocationExcelRequest) -> dict:
    session = SESSIONS.get(req.session_id)
    table = session_table(session, req.key)
    if session is None or table is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resultatet hittades inte (kör flödet igen).")
    label = session["labels"].get(req.key, req.key)
    include_header = session.get("flow_id") != "split-values"
    try:
        path = write_table_to_excel(table, label, include_header=include_header)
        open_path(path)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Kunde inte öppna Excel-filen automatiskt. {exc}",
        ) from exc
    return {"opened": True, "path": path}


def table_column_text(session_id: str, key: str, column_index: int) -> dict:
    session = SESSIONS.get(session_id)
    table = session_table(session, key)
    if session is None or table is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resultatet hittades inte.")
    if column_index < 0 or column_index >= len(table.columns):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kolumnen hittades inte.")
    if _is_simple_table(table):
        values = [_cell(value) for value in table.column_values(column_index)]
    else:
        values = [_cell(value) for value in table.iloc[:, column_index].tolist()]
    while values and values[-1] == "":
        values.pop()
    return {"text": "\n".join(values)}


def _download_file_response(payload: dict) -> FileResponse:
    filename = str(payload.get("filename") or "download.csv")
    suffix = Path(filename).suffix or ".csv"
    media_type = str(payload.get("media_type") or "text/csv")
    path = payload.get("path")
    if path:
        return FileResponse(str(path), filename=filename, media_type=media_type)
    encoding = str(payload.get("encoding") or "utf-8-sig")
    content = payload.get("content", "")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        if isinstance(content, bytes):
            tmp.write(content)
        else:
            tmp.write(str(content).encode(encoding))
    finally:
        tmp.close()
    return FileResponse(tmp.name, filename=filename, media_type=media_type)


def download_result(session_id: str, key: str):
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resultatet hittades inte.")
    download_file = (session.get("download_files") or {}).get(key)
    if download_file is not None:
        return _download_file_response(download_file)
    table = session_table(session, key)
    if table is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resultatet hittades inte.")
    label = session["labels"].get(key, key)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    if _is_simple_table(table):
        table.write_csv(tmp.name)
    else:
        with open(tmp.name, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow([str(column) for column in table.columns])
            for row in table.itertuples(index=False, name=None):
                writer.writerow([_cell(value) for value in row])
    tmp.close()
    return FileResponse(tmp.name, filename=f"{label}.csv", media_type="text/csv")

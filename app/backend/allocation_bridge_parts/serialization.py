def _cell(value: object) -> str:
    try:
        import pandas as pd  # type: ignore
    except Exception:  # noqa: BLE001
        pd = None

    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        return str(int(value)) if value.is_integer() else f"{value:g}"
    if pd is not None and isinstance(value, pd.Timestamp):
        return "" if pd.isna(value) else value.isoformat(sep=" ")
    text = str(value)
    return "" if text.lower() in ("nan", "nat", "none") else text


def _is_simple_table(value: object) -> bool:
    try:
        return bool(_native_tables().is_simple_table(value))
    except Exception:
        return False


def df_to_table(df, preview_limit: int = 1000) -> dict:
    if _is_simple_table(df):
        columns = [str(column) for column in df.columns]
        rows = [[_cell(value) for value in row] for row in df.preview_rows(preview_limit)]
        return {
            "columns": columns,
            "rows": rows,
            "row_count": int(len(df)),
            "truncated": len(df) > preview_limit,
        }

    try:
        import pandas as pd  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise AllocationBridgeUnavailable("Pandas saknas för lagerverktygsresultat.") from exc

    if not isinstance(df, pd.DataFrame) or df.empty:
        cols = [str(c) for c in df.columns] if isinstance(df, pd.DataFrame) else []
        return {"columns": cols, "rows": [], "row_count": 0, "truncated": False}
    columns = [str(c) for c in df.columns]
    preview = df.head(preview_limit)
    rows = [[_cell(v) for v in rec] for rec in preview.itertuples(index=False, name=None)]
    return {
        "columns": columns,
        "rows": rows,
        "row_count": int(len(df)),
        "truncated": len(df) > preview_limit,
    }


def _safe_session_key(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "table")).strip("._-")
    return (safe or "table")[:80]


def _session_file_path(session_id: str, key: str, suffix: str) -> Path:
    return _active_session_cache_dir() / f"{session_id}_{_safe_session_key(key)}{suffix}"


def _table_to_dataframe(table):
    try:
        import pandas as pd  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise AllocationBridgeUnavailable("Pandas saknas for lagerverktygsresultat.") from exc

    if isinstance(table, pd.DataFrame):
        return table
    if _is_simple_table(table):
        return pd.DataFrame(list(table.rows), columns=[str(column) for column in table.columns])
    return pd.DataFrame(table)


def _write_session_table(session_id: str, key: str, table) -> dict:
    cache_dir = _active_session_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _session_file_path(session_id, key, ".pkl")
    df = _table_to_dataframe(table)
    df.to_pickle(path)
    return {
        "__allocation_table_file__": True,
        "format": "pickle",
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "columns": [str(column) for column in df.columns],
        "row_count": int(len(df)),
    }


def _read_session_table(value):
    if isinstance(value, dict) and value.get("__allocation_table_file__"):
        path = Path(str(value.get("path") or ""))
        if not path.is_file():
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resultatet hittades inte (kör flödet igen).")
        try:
            import pandas as pd  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise AllocationBridgeUnavailable("Pandas saknas for lagerverktygsresultat.") from exc
        return pd.read_pickle(path)
    return value


def session_table(session: dict | None, key: str):
    if not session:
        return None
    tables = session.get("tables") or {}
    if key not in tables:
        return None
    return _read_session_table(tables[key])


def _json_payload_size(value: object) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))
    except (TypeError, ValueError):
        return 0


def _write_session_json(session_id: str, key: str, payload: object) -> dict:
    cache_dir = _active_session_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _session_file_path(session_id, key, ".json")
    tmp = tempfile.NamedTemporaryFile(delete=False, dir=cache_dir, prefix="pending_", suffix=".json", mode="w", encoding="utf-8")
    try:
        json.dump(payload, tmp, ensure_ascii=False, default=str)
        tmp.close()
        Path(tmp.name).replace(path)
    except Exception:
        Path(tmp.name).unlink(missing_ok=True)
        raise
    return {
        "__allocation_json_file__": True,
        "path": str(path),
        "size_bytes": path.stat().st_size,
    }


def _read_session_json(value: object) -> object:
    if isinstance(value, dict) and value.get("__allocation_json_file__"):
        path = Path(str(value.get("path") or ""))
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    return value


def _store_session_artifacts(session_id: str, artifacts: dict) -> dict:
    stored: dict[str, object] = {}
    for key, value in (artifacts or {}).items():
        if _json_payload_size(value) > SESSION_ARTIFACT_INLINE_MAX_BYTES:
            stored[key] = _write_session_json(session_id, f"artifact_{key}", value)
        else:
            stored[key] = value
    return stored


def session_artifacts(session: dict | None) -> dict:
    artifacts = (session or {}).get("artifacts") or {}
    return {key: _read_session_json(value) for key, value in artifacts.items()}


def _store_session_download_files(session_id: str, download_files: dict) -> dict:
    _active_session_cache_dir().mkdir(parents=True, exist_ok=True)
    stored: dict[str, dict] = {}
    for key, payload in (download_files or {}).items():
        item = dict(payload or {})
        content = item.pop("content", "")
        filename = str(item.get("filename") or f"{key}.csv")
        suffix = Path(filename).suffix or ".csv"
        path = _session_file_path(session_id, f"download_{key}", suffix)
        encoding = str(item.get("encoding") or "utf-8-sig")
        with open(path, "wb") as handle:
            if isinstance(content, bytes):
                handle.write(content)
            else:
                handle.write(str(content).encode(encoding))
        item["path"] = str(path)
        item["size_bytes"] = path.stat().st_size
        stored[key] = item
    return stored


def _session_file_paths(session: dict | None) -> list[Path]:
    paths: list[Path] = []
    for value in ((session or {}).get("tables") or {}).values():
        if isinstance(value, dict) and value.get("path"):
            paths.append(Path(str(value["path"])))
    for value in ((session or {}).get("artifacts") or {}).values():
        if isinstance(value, dict) and value.get("path"):
            paths.append(Path(str(value["path"])))
    for value in ((session or {}).get("download_files") or {}).values():
        if isinstance(value, dict) and value.get("path"):
            paths.append(Path(str(value["path"])))
    return paths


def _remove_session(session: dict | None) -> None:
    for path in _session_file_paths(session):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            continue


def _session_size_bytes(session: dict | None) -> int:
    total = 0
    for path in _session_file_paths(session):
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total



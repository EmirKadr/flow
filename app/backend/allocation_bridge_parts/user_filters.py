def _normalize_user_filter_operator(value: object) -> str:
    key = str(value or "").strip()
    return USER_FILTER_OPERATORS.get(key) or USER_FILTER_OPERATORS.get(key.lower()) or "EQ"


def _split_user_filter_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        raw_values = re.split(r"[\n,;]+", str(value))
    result: list[str] = []
    for item in raw_values:
        text = _process_filter_text(item)
        if text:
            result.append(text)
    return result


def _normalize_user_filter_condition(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    column = str(raw.get("column") or raw.get("id") or raw.get("field") or "").strip()
    column_label = str(raw.get("columnLabel") or raw.get("label") or "").strip()
    if not column and not column_label:
        return None
    operator = _normalize_user_filter_operator(raw.get("operator"))
    value = raw.get("value")
    if operator in {"In", "NotIn"}:
        normalized_value = _split_user_filter_values(value)
        if not normalized_value:
            return None
    elif operator == "Between":
        normalized_value = _split_user_filter_values(value)
        if len(normalized_value) < 2:
            return None
        normalized_value = normalized_value[:2]
    else:
        normalized_value = _process_filter_text(value)
        if not normalized_value:
            return None
    return {
        "column": column[:160],
        "columnLabel": column_label[:160],
        "operator": operator,
        "value": normalized_value,
    }


def _normalize_user_source_mode(value: object) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"api", "external", "hamta", "hämta"}:
        return "api"
    if text in {"upload", "uploaded", "file", "local", "uppladdning", "fil"}:
        return "upload"
    return None


def _normalize_user_source_modes(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    modes: dict[str, str] = {}
    for raw_file_key, raw_mode in value.items():
        file_key = str(raw_file_key or "").strip()
        if not file_key or not re.fullmatch(r"[A-Za-z0-9_:-]{1,80}", file_key):
            continue
        mode = _normalize_user_source_mode(raw_mode)
        if mode:
            modes[file_key] = mode
    return modes


def _ytgenerering_default_area_rule(code: object) -> dict[str, int]:
    area_code = normalize_process_area_focus(code) or "DEFAULT"
    defaults = YTGENERERING_DEFAULT_AREA_RULES.get(area_code) or YTGENERERING_DEFAULT_AREA_RULES["DEFAULT"]
    return {
        "utlMin": _process_utl_number(defaults.get("utlMin"), YTGENERERING_UTL_DEFAULT_MIN),
        "utlMax": _process_utl_number(defaults.get("utlMax"), YTGENERERING_UTL_DEFAULT_MAX),
    }


def default_ytgenerering_area_settings(area_options: object = None) -> dict[str, dict[str, int]]:
    areas = {"DEFAULT": _ytgenerering_default_area_rule("DEFAULT")}
    for code in YTGENERERING_DEFAULT_AREA_RULES:
        if code != "DEFAULT":
            areas[code] = _ytgenerering_default_area_rule(code)
    for area in normalize_process_area_options(area_options):
        code = normalize_process_area_focus(area.get("code"))
        if code:
            areas[code] = _ytgenerering_default_area_rule(code)
    return areas


def _normalize_ytgenerering_area_settings(value: object, area_options: object = None) -> dict[str, dict[str, int]]:
    areas = default_ytgenerering_area_settings(area_options)
    raw_areas = value.get("areas") if isinstance(value, dict) and isinstance(value.get("areas"), dict) else value
    if not isinstance(raw_areas, dict):
        return areas

    for raw_code, raw_rule in raw_areas.items():
        code = normalize_process_area_focus(raw_code)
        if code != "DEFAULT" and not _valid_process_matrix_code(code):
            continue
        base = areas.get(code) or _ytgenerering_default_area_rule(code)
        if isinstance(raw_rule, dict):
            utl_min, utl_max = _process_utl_range(raw_rule, base)
        else:
            utl_min, utl_max = base["utlMin"], base["utlMax"]
        areas[code] = {"utlMin": utl_min, "utlMax": utl_max}
    return areas


def _carrier_cluster_text(value: object, *, max_length: int = 160) -> str:
    text = _process_filter_text(value)
    return text[:max_length]


def _carrier_cluster_sequence(value: object) -> str:
    text = _carrier_cluster_text(value, max_length=20).replace(",", ".")
    if not text:
        return ""
    try:
        number = int(float(text))
    except (TypeError, ValueError):
        return ""
    return str(max(YTGENERERING_UTL_DEFAULT_MIN, min(YTGENERERING_UTL_DEFAULT_MAX, number)))


def _carrier_cluster_order(value: object, fallback: int) -> str:
    text = _carrier_cluster_text(value, max_length=20).replace(",", ".")
    if not text:
        return str(fallback)
    try:
        number = int(float(text))
    except (TypeError, ValueError):
        number = fallback
    return str(max(0, min(10000, number)))


def _normalize_user_carrier_cluster_row(raw: object, index: int) -> dict | None:
    if not isinstance(raw, dict):
        return None
    carrier_num = _carrier_cluster_text(
        raw.get("carrierNum")
        or raw.get("carrier_num")
        or raw.get("agencyNum")
        or raw.get("agency_num")
        or raw.get("AGENCY_NUM"),
        max_length=80,
    )
    if carrier_num.endswith(".0"):
        carrier_num = carrier_num[:-2]
    description = _carrier_cluster_text(
        raw.get("description")
        or raw.get("agencyDesc")
        or raw.get("agency_desc")
        or raw.get("AGENCY_DESC")
        or raw.get("carrier")
        or raw.get("transportor")
    )
    alias = _carrier_cluster_text(raw.get("alias") or raw.get("agencyAlias") or raw.get("agency_alias") or raw.get("AGENCY_ALIAS"))
    if not (carrier_num or description or alias):
        return None
    row = {
        "id": _carrier_cluster_text(raw.get("id"), max_length=100) or carrier_num or f"row-{index + 1}",
        "carrierNum": carrier_num,
        "description": description,
        "alias": alias,
        "clusterGroup": _carrier_cluster_text(raw.get("clusterGroup") or raw.get("cluster_group") or raw.get("CLUSTER_GROUP") or raw.get("cluster")),
        "assignmentOrder": _carrier_cluster_order(raw.get("assignmentOrder") or raw.get("assignment_order") or raw.get("ASSIGNMENT_ORDER"), index + 1),
        "startSeq": _carrier_cluster_sequence(raw.get("startSeq") or raw.get("start_seq") or raw.get("START_SEQ") or raw.get("from") or raw.get("utlFrom")),
        "endSeq": _carrier_cluster_sequence(raw.get("endSeq") or raw.get("end_seq") or raw.get("END_SEQ") or raw.get("to") or raw.get("utlTo")),
        "asn": _carrier_cluster_text(raw.get("asn") or raw.get("agency_asn") or raw.get("agencyAsn") or raw.get("ASN"), max_length=40),
        "arrive": _carrier_cluster_text(raw.get("arrive") or raw.get("agency_arrive") or raw.get("agencyArrive") or raw.get("ARRIVE"), max_length=40),
        "depart": _carrier_cluster_text(raw.get("depart") or raw.get("agency_depart") or raw.get("agencyDepart") or raw.get("DEPART"), max_length=40),
        "color": _carrier_cluster_text(raw.get("color") or raw.get("colour"), max_length=24),
    }
    return row


def _normalize_user_carrier_clusters(value: object) -> dict | None:
    if value is None:
        return None
    rows = value if isinstance(value, list) else value.get("rows") if isinstance(value, dict) else None
    if not isinstance(rows, list):
        return None
    normalized_rows = [
        row
        for row in (_normalize_user_carrier_cluster_row(item, index) for index, item in enumerate(rows[:200]))
        if row is not None
    ]
    if not normalized_rows:
        return None
    source = value.get("source") if isinstance(value, dict) and isinstance(value.get("source"), dict) else {}
    return {
        "version": 1,
        "source": {
            "name": _carrier_cluster_text(source.get("name"), max_length=120) or "Transportorer",
            "rowCount": len(normalized_rows),
        },
        "rows": normalized_rows,
    }


def _normalize_user_ytgenerering_settings(value: object) -> dict | None:
    raw = value if isinstance(value, dict) else {}
    if not raw:
        return None
    areas = _normalize_ytgenerering_area_settings(raw.get("areas") if isinstance(raw.get("areas"), dict) else raw)
    carrier_clusters = _normalize_user_carrier_clusters(raw.get("carrierClusters") or raw.get("carrier_clusters"))
    settings: dict[str, object] = {"areas": areas}
    if carrier_clusters:
        settings["carrierClusters"] = carrier_clusters
    return settings


def normalize_user_filter_profile(value: object, *, flows: list[dict] | None = None) -> dict:
    allowed_flow_ids = _process_matrix_flow_ids(flows)
    raw_profile = value if isinstance(value, dict) else {}
    raw_flows = raw_profile.get("flows")
    if not isinstance(raw_flows, dict):
        raw_flows = {}
    profile_flows: dict[str, dict] = {}
    for raw_flow_id, raw_flow in raw_flows.items():
        flow_id = str(raw_flow_id or "").strip()
        if not flow_id or not re.fullmatch(r"[A-Za-z0-9_:-]{1,80}", flow_id):
            continue
        if allowed_flow_ids is not None and flow_id not in allowed_flow_ids:
            continue
        if not isinstance(raw_flow, dict):
            continue
        raw_files = raw_flow.get("files") if isinstance(raw_flow, dict) else None
        files_payload: dict[str, list[dict]] = {}
        if isinstance(raw_files, dict):
            for raw_file_key, raw_conditions in raw_files.items():
                file_key = str(raw_file_key or "").strip()
                if not file_key or not re.fullmatch(r"[A-Za-z0-9_:-]{1,80}", file_key):
                    continue
                conditions = [
                    condition
                    for condition in (_normalize_user_filter_condition(item) for item in (raw_conditions or []))
                    if condition is not None
                ]
                if conditions:
                    files_payload[file_key] = conditions[:20]
        flow_payload: dict[str, object] = {}
        source_modes = _normalize_user_source_modes(raw_flow.get("sources") or raw_flow.get("sourceModes"))
        if source_modes:
            flow_payload["sources"] = source_modes
        if files_payload:
            flow_payload["files"] = files_payload
        raw_settings = raw_flow.get("settings") if isinstance(raw_flow.get("settings"), dict) else {}
        raw_ytgenerering_settings = raw_settings.get("ytgenerering") if isinstance(raw_settings, dict) else None
        if raw_ytgenerering_settings is None:
            raw_ytgenerering_settings = raw_flow.get("ytgenerering")
        if flow_id == "ytgenerering":
            ytgenerering_settings = _normalize_user_ytgenerering_settings(raw_ytgenerering_settings)
            if ytgenerering_settings:
                flow_payload["settings"] = {"ytgenerering": ytgenerering_settings}
        if flow_payload:
            profile_flows[flow_id] = flow_payload
    return {"version": USER_FILTER_PROFILE_VERSION, "flows": profile_flows}


def user_filter_profile_count(profile: object) -> int:
    normalized = normalize_user_filter_profile(profile)
    file_count = sum(
        len(conditions)
        for flow in normalized.get("flows", {}).values()
        for conditions in flow.get("files", {}).values()
    )
    source_count = sum(
        len(flow.get("sources", {}))
        for flow in normalized.get("flows", {}).values()
        if isinstance(flow, dict)
    )
    settings_count = 0
    for flow in normalized.get("flows", {}).values():
        ytgenerering = ((flow.get("settings") or {}).get("ytgenerering") or {}) if isinstance(flow, dict) else {}
        if not isinstance(ytgenerering, dict):
            continue
        if ytgenerering.get("areas"):
            settings_count += 1
        carrier_clusters = ytgenerering.get("carrierClusters") if isinstance(ytgenerering.get("carrierClusters"), dict) else None
        settings_count += len(carrier_clusters.get("rows") or []) if carrier_clusters else 0
    return file_count + source_count + settings_count


def user_source_modes(profile: object, flow_id: str) -> dict[str, str]:
    normalized = normalize_user_filter_profile(profile)
    flow = normalized.get("flows", {}).get(str(flow_id or ""), {})
    sources = flow.get("sources") if isinstance(flow, dict) else None
    return dict(sources) if isinstance(sources, dict) else {}


def api_source_map_for_user_profile(source_map: dict[str, str], flow_id: str, profile: object) -> dict[str, str]:
    modes = user_source_modes(profile, flow_id)
    if not modes:
        return dict(source_map)
    return {
        file_key: source_key
        for file_key, source_key in source_map.items()
        if modes.get(str(file_key)) != "upload"
    }


def ytgenerering_user_settings(profile: object, *, area_focus: object = None) -> dict[str, object]:
    normalized = normalize_user_filter_profile(profile)
    settings = (
        normalized.get("flows", {})
        .get("ytgenerering", {})
        .get("settings", {})
        .get("ytgenerering")
    )
    settings = settings if isinstance(settings, dict) else {}
    areas = _normalize_ytgenerering_area_settings(settings.get("areas") if isinstance(settings.get("areas"), dict) else {})
    focus_code = normalize_process_area_focus(area_focus) or "ALLT"
    rule = areas.get(focus_code) or areas.get("DEFAULT") or _ytgenerering_default_area_rule("DEFAULT")
    carrier_clusters = settings.get("carrierClusters") if isinstance(settings.get("carrierClusters"), dict) else None
    rows = carrier_clusters.get("rows") if isinstance(carrier_clusters, dict) else None
    return {
        "areas": areas,
        "utlRange": (int(rule["utlMin"]), int(rule["utlMax"])),
        "carrierClusters": carrier_clusters if rows else None,
    }


def apply_ytgenerering_user_settings(
    params: dict[str, str],
    profile: object,
    *,
    area_focus: object = None,
) -> dict[str, object]:
    settings = ytgenerering_user_settings(profile, area_focus=area_focus)
    utl_min, utl_max = settings["utlRange"]
    params[YTGENERERING_UTL_MIN_PARAM] = str(utl_min)
    params[YTGENERERING_UTL_MAX_PARAM] = str(utl_max)
    carrier_clusters = settings.get("carrierClusters")
    if isinstance(carrier_clusters, dict) and carrier_clusters.get("rows"):
        params["__carrier_clusters_json"] = json.dumps(carrier_clusters, ensure_ascii=False)
    return settings


def _user_filter_column(df, condition: dict) -> str | None:
    candidates = {
        _process_column_key(value)
        for value in (condition.get("column"), condition.get("columnLabel"))
        if _process_column_key(value)
    }
    if not candidates:
        return None
    for column in df.columns:
        if _process_column_key(column) in candidates:
            return column
    return None


def _user_filter_text_series(series):
    return series.map(_process_filter_text)


def _user_filter_casefold(value: object) -> str:
    return _process_filter_text(value).casefold()


def _user_filter_number(value: object) -> float | None:
    text = _process_filter_text(value).replace(",", ".")
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _user_filter_numeric_mask(series, operator: str, values: list[str] | str):
    import pandas as pd  # type: ignore

    if isinstance(values, str):
        compare_values = [values]
    else:
        compare_values = list(values)
    numbers = [_user_filter_number(value) for value in compare_values]
    if any(number is None for number in numbers):
        return None
    numeric_series = pd.to_numeric(
        _user_filter_text_series(series).map(lambda value: str(value).replace(",", ".")),
        errors="coerce",
    )
    first = numbers[0]
    if first is None:
        return None
    if operator == "GT":
        return numeric_series > first
    if operator == "GTE":
        return numeric_series >= first
    if operator == "LT":
        return numeric_series < first
    if operator == "LTE":
        return numeric_series <= first
    if operator == "Between" and len(numbers) >= 2 and numbers[1] is not None:
        low, high = sorted((first, numbers[1]))
        return numeric_series.between(low, high, inclusive="both")
    return None


def _user_filter_condition_mask(series, condition: dict):
    operator = str(condition.get("operator") or "EQ")
    value = condition.get("value")
    text_series = _user_filter_text_series(series).map(lambda item: str(item).casefold())
    if operator == "EQ":
        return text_series.eq(_user_filter_casefold(value))
    if operator == "NE":
        return ~text_series.eq(_user_filter_casefold(value))
    if operator in {"GT", "GTE", "LT", "LTE"}:
        numeric = _user_filter_numeric_mask(series, operator, _process_filter_text(value))
        if numeric is not None:
            return numeric.fillna(False)
        compare = _user_filter_casefold(value)
        if operator == "GT":
            return text_series.gt(compare)
        if operator == "GTE":
            return text_series.ge(compare)
        if operator == "LT":
            return text_series.lt(compare)
        return text_series.le(compare)
    if operator == "Between":
        values = value if isinstance(value, list) else _split_user_filter_values(value)
        numeric = _user_filter_numeric_mask(series, operator, values[:2])
        if numeric is not None:
            return numeric.fillna(False)
        if len(values) < 2:
            return text_series.eq("")
        low, high = sorted((_user_filter_casefold(values[0]), _user_filter_casefold(values[1])))
        return text_series.between(low, high, inclusive="both")
    if operator in {"In", "NotIn"}:
        values = {_user_filter_casefold(item) for item in _split_user_filter_values(value)}
        mask = text_series.isin(values)
        return ~mask if operator == "NotIn" else mask
    return text_series.eq(_user_filter_casefold(value))


def apply_user_flow_filters(
    files: dict[str, Path],
    flow_id: str,
    profile: object,
) -> tuple[dict[str, Path], list[Path], list[str]]:
    normalized = normalize_user_filter_profile(profile)
    flow_filters = (normalized.get("flows") or {}).get(str(flow_id or ""), {}).get("files") or {}
    if not flow_filters:
        return files, [], []

    filtered_files = dict(files)
    temp_paths: list[Path] = []
    log_lines: list[str] = []
    for file_key, conditions in flow_filters.items():
        if file_key not in files or not conditions:
            continue
        path = Path(files[file_key])
        try:
            df = _read_process_filter_table(path)
        except Exception as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Filtret for {file_key} kunde inte lasa tabellen.",
            ) from exc
        mask = None
        missing_columns: list[str] = []
        for condition in conditions:
            column = _user_filter_column(df, condition)
            if column is None:
                missing_columns.append(str(condition.get("columnLabel") or condition.get("column") or "kolumn"))
                continue
            condition_mask = _user_filter_condition_mask(df[column], condition)
            mask = condition_mask if mask is None else (mask & condition_mask)
        if missing_columns:
            missing = ", ".join(sorted(set(missing_columns))[:5])
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Filtret for {file_key} saknar kolumn: {missing}.",
            )
        if mask is None:
            continue
        before = int(len(df))
        filtered_df = df.loc[mask].copy()
        filtered_path = _write_process_filter_table(filtered_df, source_key=file_key, area_focus="userfilter")
        filtered_files[file_key] = filtered_path
        temp_paths.append(filtered_path)
        log_lines.append(f"Anvandarfilter {file_key}: {before} -> {int(len(filtered_df))} rader ({len(conditions)} villkor).")
    return filtered_files, temp_paths, log_lines



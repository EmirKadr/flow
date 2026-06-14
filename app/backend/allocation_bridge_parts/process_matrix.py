def normalize_process_area_focus(value: object) -> str:
    return str(value or "").strip().upper()


def _valid_process_matrix_code(code: str) -> bool:
    return bool(code and re.fullmatch(r"[A-Z0-9_:-]{1,40}", code))


def normalize_process_area_options(
    area_options: object = None,
    *,
    include_all: bool = True,
) -> tuple[dict[str, str], ...]:
    if isinstance(area_options, dict):
        raw_options = area_options.get("areas")
    else:
        raw_options = area_options
    if raw_options is None:
        raw_options = []
    if not isinstance(raw_options, (list, tuple)):
        raw_options = []

    options: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in raw_options:
        if isinstance(raw, dict):
            code = normalize_process_area_focus(raw.get("code") or raw.get("value"))
            label = str(raw.get("label") or raw.get("name") or raw.get("title") or code).strip()
        else:
            code = normalize_process_area_focus(raw)
            label = code
        if not _valid_process_matrix_code(code) or code == "DEFAULT":
            continue
        if code in seen:
            continue
        seen.add(code)
        option = {"code": code, "label": label or code}
        if isinstance(raw, dict):
            for source_key, target_key in (("title", "title"), ("areaId", "areaId"), ("businessId", "businessId")):
                value = raw.get(source_key)
                if value is not None:
                    option[target_key] = str(value)
        options.append(option)

    if include_all and PROCESS_MATRIX_ALL_CODE not in seen:
        options.append(dict(PROCESS_MATRIX_ALL_AREA_OPTION))
    return tuple(options)


def _process_matrix_flow_ids(flows: list[dict] | None) -> set[str] | None:
    if flows is None:
        return None
    ids: set[str] = set()
    for flow in flows:
        flow_id = str(flow.get("id") or "").strip()
        if flow_id:
            ids.add(flow_id)
    return ids


def _process_rule_values(raw: dict | None, *keys: str):
    if not isinstance(raw, dict):
        return None
    for key in keys:
        if key in raw:
            return raw.get(key)
    return None


def _process_visible_flow_ids(value: object, allowed_flow_ids: set[str] | None = None) -> set[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        raw_values = re.split(r"[,;\s]+", value)
    elif isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        raw_values = [value]
    ids = {str(item or "").strip() for item in raw_values if str(item or "").strip()}
    if allowed_flow_ids is not None:
        ids &= allowed_flow_ids
    return ids


def _process_utl_number(value: object, fallback: int) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        number = fallback
    return max(YTGENERERING_UTL_DEFAULT_MIN, min(YTGENERERING_UTL_DEFAULT_MAX, number))


def _process_utl_range(raw: dict, defaults: dict | None = None) -> tuple[int, int]:
    defaults = defaults or YTGENERERING_DEFAULT_AREA_RULES["DEFAULT"]
    default_min = _process_utl_number(defaults.get("utlMin") or defaults.get("ytgenerering_utl_min"), YTGENERERING_UTL_DEFAULT_MIN)
    default_max = _process_utl_number(defaults.get("utlMax") or defaults.get("ytgenerering_utl_max"), YTGENERERING_UTL_DEFAULT_MAX)
    raw_min = _process_rule_values(
        raw,
        "ytgenerering_utl_min",
        "ytgenereringUtlMin",
        "ytgenereringUtlFrom",
        "utl_min",
        "utlMin",
        "utlFrom",
    )
    raw_max = _process_rule_values(
        raw,
        "ytgenerering_utl_max",
        "ytgenereringUtlMax",
        "ytgenereringUtlTo",
        "utl_max",
        "utlMax",
        "utlTo",
    )
    min_number = _process_utl_number(raw_min, default_min)
    max_number = _process_utl_number(raw_max, default_max)
    if min_number > max_number:
        min_number, max_number = max_number, min_number
    return min_number, max_number


def _normalize_process_area_rule(
    raw: dict | None,
    allowed_flow_ids: set[str] | None = None,
    defaults: dict | None = None,
) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    visible_flow_ids = _process_visible_flow_ids(
        _process_rule_values(raw, "visible_flow_ids", "visibleFlowIds", "flow_ids", "flowIds"),
        allowed_flow_ids=allowed_flow_ids,
    )
    return {
        "visible_flow_ids": visible_flow_ids,
    }


def default_process_matrix(
    flows: list[dict] | None = None,
    *,
    area_options: object = None,
) -> dict[str, dict]:
    allowed_flow_ids = _process_matrix_flow_ids(flows)
    matrix: dict[str, dict] = {
        "DEFAULT": _normalize_process_area_rule(PROCESS_DEFAULT_AREA_RULE, allowed_flow_ids=allowed_flow_ids)
    }
    for code, rule in PROCESS_AREA_RULES.items():
        area_code = normalize_process_area_focus(code)
        if _valid_process_matrix_code(area_code):
            matrix[area_code] = _normalize_process_area_rule(rule, allowed_flow_ids=allowed_flow_ids)
    for area in normalize_process_area_options(area_options):
        code = normalize_process_area_focus(area.get("code"))
        matrix[code] = _normalize_process_area_rule(
            PROCESS_AREA_RULES.get(code),
            allowed_flow_ids=allowed_flow_ids,
            defaults=matrix.get(code) or matrix.get("DEFAULT"),
        )
    return matrix


def normalize_process_matrix(
    value: object = None,
    *,
    flows: list[dict] | None = None,
    area_options: object = None,
) -> dict[str, dict]:
    allowed_flow_ids = _process_matrix_flow_ids(flows)
    matrix = default_process_matrix(flows=flows, area_options=area_options)
    raw_matrix = value.get("matrix") if isinstance(value, dict) and isinstance(value.get("matrix"), dict) else value
    if not isinstance(raw_matrix, dict):
        return matrix

    for raw_code, raw_rule in raw_matrix.items():
        code = normalize_process_area_focus(raw_code)
        if code != "DEFAULT" and not _valid_process_matrix_code(code):
            continue
        if not isinstance(raw_rule, dict):
            continue
        matrix[code] = _normalize_process_area_rule(
            raw_rule,
            allowed_flow_ids=allowed_flow_ids,
            defaults=matrix.get(code) or matrix.get("DEFAULT"),
        )
    return matrix


def process_area_rule(area_focus: object, matrix: dict[str, dict] | None = None) -> dict | None:
    code = normalize_process_area_focus(area_focus)
    if not code:
        return None
    rules = normalize_process_matrix(matrix) if matrix is not None else default_process_matrix()
    return rules.get(code) or rules.get("DEFAULT")


def process_flow_visible(flow_id: str, area_focus: object, matrix: dict[str, dict] | None = None) -> bool:
    rule = process_area_rule(area_focus, matrix=matrix)
    visible_flow_ids = rule.get("visible_flow_ids") if rule else None
    return visible_flow_ids is None or flow_id in visible_flow_ids


def process_rule_has_filters(rule: dict | None) -> bool:
    return False


def process_matrix_storage_payload(
    matrix: dict[str, dict] | None = None,
    *,
    area_options: object = None,
) -> dict[str, dict]:
    rules = normalize_process_matrix(matrix, area_options=area_options)
    payload: dict[str, dict] = {}
    for code, rule in rules.items():
        if code == "DEFAULT":
            continue
        visible_flow_ids = rule.get("visible_flow_ids")
        payload[code] = {
            "visibleFlowIds": None if visible_flow_ids is None else sorted(str(value) for value in visible_flow_ids),
        }
    return payload


def process_matrix_public_payload(
    matrix: dict[str, dict] | None = None,
    *,
    flows: list[dict] | None = None,
    area_options: object = None,
    area_codes: set[str] | None = None,
) -> dict:
    active_codes: set[str] | None = None
    if area_options is not None:
        areas = list(normalize_process_area_options(area_options))
        active_codes = {normalize_process_area_focus(area.get("code")) for area in areas}
    elif area_codes is not None:
        active_code_list = sorted(
            code
            for code in {normalize_process_area_focus(code) for code in area_codes}
            if _valid_process_matrix_code(code) and code != PROCESS_MATRIX_ALL_CODE
        )
        active_codes = set(active_code_list)
        areas = [{"code": code, "label": code} for code in active_code_list]
        areas.append(dict(PROCESS_MATRIX_ALL_AREA_OPTION))
    else:
        base_rules = normalize_process_matrix(matrix, flows=flows)
        rule_codes = sorted(
            code
            for code in base_rules
            if code != "DEFAULT" and _valid_process_matrix_code(code) and code != PROCESS_MATRIX_ALL_CODE
        )
        areas = [{"code": code, "label": code} for code in rule_codes]
        areas.append(dict(PROCESS_MATRIX_ALL_AREA_OPTION))
    rules = normalize_process_matrix(matrix, flows=flows, area_options=areas)
    known_codes = {normalize_process_area_focus(area.get("code")) for area in areas}
    for code in sorted(rules):
        if code != "DEFAULT" and code not in known_codes and (active_codes is None or code in active_codes):
            areas.append({"code": code, "label": code})
            known_codes.add(code)

    public_rules: dict[str, dict] = {}
    for code, rule in rules.items():
        if active_codes is not None and code != "DEFAULT" and code not in known_codes:
            continue
        visible_flow_ids = rule.get("visible_flow_ids")
        public_rules[code] = {
            "visibleFlowIds": None if visible_flow_ids is None else sorted(str(value) for value in visible_flow_ids),
        }
    return {
        "areas": areas,
        "flows": flows or [],
        "matrix": public_rules,
    }


def _process_column_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _process_filter_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "nat", "none"}:
        return ""
    return text


def _read_process_filter_table(path: Path):
    import pandas as pd  # type: ignore

    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"}:
        return pd.read_excel(path, dtype=str)

    try:
        df = pd.read_csv(path, dtype=str, sep=None, engine="python", encoding="utf-8-sig")
        if df.shape[1] == 1 and len(df):
            first = str(df.iloc[0, 0])
            if "\t" in first:
                df = pd.read_csv(path, dtype=str, sep="\t", engine="python", encoding="utf-8-sig")
    except Exception:
        df = pd.read_csv(path, dtype=str, sep="\t", engine="python", encoding="utf-8-sig")
    return df


def _write_process_filter_table(
    df,
    *,
    source_key: str,
    area_focus: str,
    target_path: Path | None = None,
) -> Path:
    if target_path is None:
        target = tempfile.NamedTemporaryFile(
            delete=False,
            prefix=f"flow_{area_focus.lower()}_{_safe_upload_stem(source_key)}_",
            suffix=".csv",
        )
        path = Path(target.name)
        target.close()
    else:
        path = target_path
        path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(delete=False, dir=path.parent, prefix="pending_filter_", suffix=".csv")
    try:
        tmp.close()
        df.to_csv(tmp.name, index=False, encoding="utf-8-sig", sep="\t")
        Path(tmp.name).replace(path)
    except Exception:
        Path(tmp.name).unlink(missing_ok=True)
        raise
    return path


def apply_process_area_filters(
    files: dict[str, Path],
    area_focus: object,
    matrix: dict[str, dict] | None = None,
) -> tuple[dict[str, Path], list[Path], list[str]]:
    # Bearbeta-matrisen styr numera bara flodessynlighet. Fil-/radfilter och
    # Ytgenereringens egna installningar ar anvandarspecifika.
    return files, [], []



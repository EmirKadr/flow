from __future__ import annotations

from dataclasses import dataclass
import math
import re
import unicodedata
from typing import Any

import pandas as pd

from .carrier_clusters import carrier_match_key, normalize_carrier_cluster_payload, text_value


@dataclass(frozen=True)
class SurfaceGenerationResult:
    assignments: pd.DataFrame
    unplaced: pd.DataFrame
    carrier_overview: pd.DataFrame
    summary: dict[str, float | int]


def _norm(value: object) -> str:
    text = "" if value is None else str(value)
    return (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
        .strip()
        .lower()
        .replace("_", " ")
    )


def _find_col(df: pd.DataFrame, aliases: tuple[str, ...], *, required: bool = True) -> str | None:
    lookup = {_norm(col): col for col in df.columns}
    for alias in aliases:
        match = lookup.get(_norm(alias))
        if match is not None:
            return match
    if required:
        raise ValueError(f"Saknar kolumn: {aliases[0]}")
    return None


def _to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", ".", regex=False).str.replace(" ", "", regex=False),
        errors="coerce",
    ).fillna(0.0)


def _location_key(value: object) -> tuple[int, str, str] | None:
    location = str(value).strip().upper()
    if len(location) < 6:
        return None
    match = re.fullmatch(r"UTL(\d+)(.*)", location)
    if not match:
        return None
    number = int(match.group(1))
    if number < 1 or number > 652:
        return None
    return number, match.group(2), location


def prepare_locations(locations: pd.DataFrame) -> pd.DataFrame:
    loc_col = _find_col(locations, ("Lagerplats", "Location", "Plats"))
    type_col = _find_col(locations, ("Typ", "Type"))
    capacity_col = _find_col(locations, ("Max pall", "Max pallplatser", "Maxpall", "Capacity"))

    prepared = locations[[loc_col, type_col, capacity_col]].copy()
    prepared.columns = ["Lagerplats", "Typ", "Max pall"]
    prepared["Lagerplats"] = prepared["Lagerplats"].astype(str).str.strip()
    prepared["Typ"] = prepared["Typ"].astype(str).str.strip().str.upper()
    prepared["Max pall"] = _to_number(prepared["Max pall"])

    keys = prepared["Lagerplats"].map(_location_key)
    prepared["_location_number"] = keys.map(lambda item: item[0] if item else math.inf)
    prepared["_location_suffix"] = keys.map(lambda item: item[1] if item else "")
    prepared = prepared[
        prepared["Typ"].eq("U")
        & keys.notna()
        & prepared["Max pall"].gt(0)
    ].copy()
    prepared = prepared.sort_values(["_location_number", "_location_suffix", "Lagerplats"]).reset_index(drop=True)
    return prepared


def _locations_are_prepared(locations: pd.DataFrame) -> bool:
    return {
        "Lagerplats",
        "Typ",
        "Max pall",
        "_location_number",
        "_location_suffix",
    }.issubset(set(locations.columns))


def prepare_forecast(forecast: pd.DataFrame) -> pd.DataFrame:
    shipment_col = _find_col(forecast, ("Sändningsnr", "Sandningsnr", "Grupp", "Shipment"))
    carrier_col = _find_col(forecast, ("Transportör", "Transportor", "Carrier"), required=False)
    pallet_col = _find_col(
        forecast,
        (
            "Predikterade pallplatser",
            "Predikterad pallplatser",
            "predikterad_pallplatser",
            "Pallplatser",
        ),
    )

    cols = [shipment_col, pallet_col]
    if carrier_col:
        cols.append(carrier_col)
    prepared = forecast[cols].copy()
    prepared["Sändningsnr"] = prepared[shipment_col].astype(str).str.strip()
    prepared["Transportör"] = (
        prepared[carrier_col].astype(str).str.strip().replace("", "Okänd") if carrier_col else "Okänd"
    )
    prepared["Pallplatser"] = _to_number(prepared[pallet_col])
    prepared = prepared[
        prepared["Sändningsnr"].ne("")
        & prepared["Sändningsnr"].str.lower().ne("nan")
        & prepared["Pallplatser"].gt(0)
    ].copy()
    if prepared.empty:
        raise ValueError("Forecasten saknar placerbara sändningar med pallplatser över 0.")
    return prepared[["Sändningsnr", "Transportör", "Pallplatser"]]


def _cluster_rows(carrier_clusters: object) -> list[dict[str, Any]]:
    payload = normalize_carrier_cluster_payload(carrier_clusters)
    if not payload:
        return []
    return payload.get("rows") or []


def _cluster_row_values(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        text_value(row.get("alias")),
        text_value(row.get("description")),
        text_value(row.get("carrierNum")),
    )


def _match_cluster_row(carrier: object, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    key = carrier_match_key(carrier)
    if not key:
        return None
    exact: dict[str, dict[str, Any]] = {}
    for row in rows:
        for value in _cluster_row_values(row):
            row_key = carrier_match_key(value)
            if row_key and row_key not in exact:
                exact[row_key] = row
    if key in exact:
        return exact[key]

    candidates: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        for value in _cluster_row_values(row):
            row_key = carrier_match_key(value)
            if row_key and (key.startswith(row_key) or row_key.startswith(key)):
                candidates.append((abs(len(row_key) - len(key)), row))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _cluster_unit_key(row: dict[str, Any] | None, carrier: object) -> str:
    if row:
        cluster = text_value(row.get("clusterGroup"))
        if cluster:
            return f"cluster:{carrier_match_key(cluster)}"
        label = text_value(row.get("alias")) or text_value(row.get("description")) or text_value(row.get("carrierNum"))
        if label:
            return f"carrier:{carrier_match_key(label)}"
    return f"carrier:{carrier_match_key(carrier) or text_value(carrier)}"


def _cluster_unit_label(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    return text_value(row.get("clusterGroup"))


def _cluster_range(row: dict[str, Any] | None) -> tuple[int, int, bool] | None:
    if not row:
        return None
    start = row.get("startSeq")
    end = row.get("endSeq")
    if not isinstance(start, int) or not isinstance(end, int):
        return None
    return min(start, end), max(start, end), start > end


def _cluster_unit_configs(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    configs: dict[str, dict[str, Any]] = {}
    for row in rows:
        unit_key = _cluster_unit_key(row, text_value(row.get("alias")) or text_value(row.get("description")))
        if not unit_key:
            continue
        order = row.get("assignmentOrder")
        order_value = order if isinstance(order, int) else 10_000
        current = configs.get(unit_key)
        if current is None or order_value < current["order"]:
            configs[unit_key] = {
                "order": order_value,
                "range": _cluster_range(row),
                "label": _cluster_unit_label(row),
            }
        elif current.get("range") is None:
            current["range"] = _cluster_range(row)
    return configs


def _find_contiguous_surface_start(
    surfaces: pd.DataFrame,
    candidate_indices: list[int],
    used_locations: set[str],
    needed_pall: float,
) -> int:
    best_start = 0
    best_cap = -1.0
    run_start: int | None = None
    run_cap = 0.0
    for pos, surface_idx in enumerate(candidate_indices):
        surface = surfaces.iloc[surface_idx]
        location = str(surface["Lagerplats"])
        if location not in used_locations:
            if run_start is None:
                run_start = pos
            run_cap += float(surface["Max pall"])
            if run_cap >= needed_pall:
                return run_start
        else:
            if run_start is not None and run_cap > best_cap:
                best_start = run_start
                best_cap = run_cap
            run_start = None
            run_cap = 0.0
    if run_start is not None and run_cap > best_cap:
        best_start = run_start
    return best_start


def _build_surface_result(
    assignments: list[dict[str, object]],
    unplaced: list[dict[str, object]],
    shipments: pd.DataFrame,
    surfaces: pd.DataFrame,
) -> SurfaceGenerationResult:
    assignments_df = pd.DataFrame(assignments)
    unplaced_df = pd.DataFrame(unplaced)

    if assignments_df.empty:
        carrier_overview = pd.DataFrame(
            columns=[
                "Transportör",
                "Kluster",
                "Sändningar",
                "Placerade pallplatser",
                "Ytor",
                "Startplats",
                "Slutplats",
                "Outnyttjad kapacitet",
            ]
        )
    else:
        carrier_overview = (
            assignments_df.groupby("Transportör", sort=False)
            .agg(
                Sändningar=("Sändningsnr", "nunique"),
                **{
                    "Placerade pallplatser": ("Placerade pallplatser", "sum"),
                    "Ytor": ("Lagerplats", "count"),
                    "Startplats": ("Lagerplats", "first"),
                    "Slutplats": ("Lagerplats", "last"),
                    "Outnyttjad kapacitet": ("Outnyttjad kapacitet", "sum"),
                },
            )
            .reset_index()
        )
        if "Kluster" in assignments_df.columns:
            cluster_by_carrier = assignments_df.groupby("Transportör", sort=False)["Kluster"].first().to_dict()
            carrier_overview.insert(1, "Kluster", carrier_overview["Transportör"].map(cluster_by_carrier).fillna(""))

    total_need = float(shipments["Pallplatser"].sum())
    placed = float(assignments_df["Placerade pallplatser"].sum()) if not assignments_df.empty else 0.0
    available_capacity = float(surfaces["Max pall"].sum())
    summary = {
        "antal_sändningar": int(shipments["Sändningsnr"].nunique()),
        "antal_lagerplatser": int(len(surfaces)),
        "använda_lagerplatser": int(len(assignments_df)),
        "total_pallplatser": round(total_need, 2),
        "placerade_pallplatser": round(placed, 2),
        "ej_placerade_pallplatser": round(max(total_need - placed, 0), 2),
        "tillgänglig_kapacitet": round(available_capacity, 2),
    }
    return SurfaceGenerationResult(assignments_df, unplaced_df, carrier_overview, summary)


def _generate_surface_plan_sequential(shipments: pd.DataFrame, surfaces: pd.DataFrame) -> SurfaceGenerationResult:
    carrier_totals = (
        shipments.groupby("Transportör", dropna=False)["Pallplatser"]
        .sum()
        .sort_values(ascending=False)
    )
    carrier_rank = {carrier: rank for rank, carrier in enumerate(carrier_totals.index)}
    shipments["_carrier_rank"] = shipments["Transportör"].map(carrier_rank)
    shipments = shipments.sort_values(
        ["_carrier_rank", "Pallplatser", "Sändningsnr"],
        ascending=[True, False, True],
    ).reset_index(drop=True)

    assignments: list[dict[str, object]] = []
    unplaced: list[dict[str, object]] = []
    surface_idx = 0

    for _, shipment in shipments.iterrows():
        total_need = float(shipment["Pallplatser"])
        remaining = total_need
        used_count = 0

        while remaining > 0.0001 and surface_idx < len(surfaces):
            surface = surfaces.iloc[surface_idx]
            surface_idx += 1
            capacity = float(surface["Max pall"])
            placed = min(remaining, capacity)
            used_count += 1
            remaining = round(remaining - placed, 6)
            assignments.append(
                {
                    "Sändningsnr": shipment["Sändningsnr"],
                    "Transportör": shipment["Transportör"],
                    "Lagerplats": surface["Lagerplats"],
                    "Max pall": capacity,
                    "Placerade pallplatser": round(placed, 2),
                    "Sändningens pallplatser": round(total_need, 2),
                    "Outnyttjad kapacitet": round(capacity - placed, 2),
                    "Placering nr": used_count,
                }
            )

        if remaining > 0.0001:
            unplaced.append(
                {
                    "Sändningsnr": shipment["Sändningsnr"],
                    "Transportör": shipment["Transportör"],
                    "Pallplatser": round(total_need, 2),
                    "Ej placerade pallplatser": round(remaining, 2),
                }
            )

    return _build_surface_result(assignments, unplaced, shipments, surfaces)


def _generate_surface_plan_clustered(
    shipments: pd.DataFrame,
    surfaces: pd.DataFrame,
    carrier_clusters: object,
) -> SurfaceGenerationResult:
    rows = _cluster_rows(carrier_clusters)
    if not rows:
        return _generate_surface_plan_sequential(shipments, surfaces)

    carrier_totals = shipments.groupby("Transportör", dropna=False)["Pallplatser"].sum().sort_values(ascending=False)
    carrier_rank = {carrier: rank for rank, carrier in enumerate(carrier_totals.index)}
    unit_configs = _cluster_unit_configs(rows)
    shipments = shipments.copy()
    unit_keys: list[str] = []
    unit_orders: list[int] = []
    carrier_orders: list[int] = []
    cluster_labels: list[str] = []

    for _, shipment in shipments.iterrows():
        carrier = shipment["Transportör"]
        row = _match_cluster_row(carrier, rows)
        unit_key = _cluster_unit_key(row, carrier)
        config = unit_configs.get(unit_key, {})
        order = config.get("order")
        fallback_order = 10_000 + int(carrier_rank.get(carrier, 0))
        unit_keys.append(unit_key)
        unit_orders.append(order if isinstance(order, int) else fallback_order)
        row_order = row.get("assignmentOrder") if row else None
        carrier_orders.append(row_order if isinstance(row_order, int) else fallback_order)
        cluster_labels.append(str(config.get("label") or _cluster_unit_label(row) or ""))

    shipments["_unit_key"] = unit_keys
    shipments["_unit_order"] = unit_orders
    shipments["_carrier_order"] = carrier_orders
    shipments["Kluster"] = cluster_labels
    shipments = shipments.sort_values(
        ["_unit_order", "_carrier_order", "Pallplatser", "Sändningsnr"],
        ascending=[True, True, False, True],
    ).reset_index(drop=True)

    assignments: list[dict[str, object]] = []
    unplaced: list[dict[str, object]] = []
    used_locations: set[str] = set()

    for unit_key, unit_shipments in shipments.groupby("_unit_key", sort=False):
        config = unit_configs.get(unit_key, {})
        cluster_range = config.get("range")
        if cluster_range:
            lo, hi, reversed_dir = cluster_range
            candidate_indices = [
                idx for idx in range(len(surfaces))
                if lo <= int(surfaces.iloc[idx]["_location_number"]) <= hi
            ]
            if reversed_dir:
                candidate_indices.reverse()
        else:
            candidate_indices = list(range(len(surfaces)))
        unit_need = float(unit_shipments["Pallplatser"].sum())
        start_pos = _find_contiguous_surface_start(surfaces, candidate_indices, used_locations, unit_need)
        candidate_indices = candidate_indices[start_pos:]
        cursor = 0

        for _, shipment in unit_shipments.iterrows():
            total_need = float(shipment["Pallplatser"])
            remaining = total_need
            used_count = 0

            while remaining > 0.0001:
                while cursor < len(candidate_indices) and str(surfaces.iloc[candidate_indices[cursor]]["Lagerplats"]) in used_locations:
                    cursor += 1
                if cursor >= len(candidate_indices):
                    break
                surface = surfaces.iloc[candidate_indices[cursor]]
                cursor += 1
                location = str(surface["Lagerplats"])
                used_locations.add(location)
                capacity = float(surface["Max pall"])
                placed = min(remaining, capacity)
                used_count += 1
                remaining = round(remaining - placed, 6)
                assignments.append(
                    {
                        "Sändningsnr": shipment["Sändningsnr"],
                        "Transportör": shipment["Transportör"],
                        "Kluster": shipment.get("Kluster", ""),
                        "Lagerplats": location,
                        "Max pall": capacity,
                        "Placerade pallplatser": round(placed, 2),
                        "Sändningens pallplatser": round(total_need, 2),
                        "Outnyttjad kapacitet": round(capacity - placed, 2),
                        "Placering nr": used_count,
                    }
                )

            if remaining > 0.0001:
                unplaced.append(
                    {
                        "Sändningsnr": shipment["Sändningsnr"],
                        "Transportör": shipment["Transportör"],
                        "Kluster": shipment.get("Kluster", ""),
                        "Pallplatser": round(total_need, 2),
                        "Ej placerade pallplatser": round(remaining, 2),
                    }
                )

    return _build_surface_result(assignments, unplaced, shipments, surfaces)


def generate_surface_plan(
    forecast: pd.DataFrame,
    locations: pd.DataFrame,
    carrier_clusters: object | None = None,
) -> SurfaceGenerationResult:
    shipments = prepare_forecast(forecast)
    surfaces = locations if _locations_are_prepared(locations) else prepare_locations(locations)
    if surfaces.empty:
        raise ValueError("Lagerplatser saknar giltiga ytor: Typ U, UTL1-UTL652, minst 6 tecken och Max pall > 0.")
    return _generate_surface_plan_clustered(shipments, surfaces, carrier_clusters)

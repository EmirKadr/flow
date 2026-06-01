from __future__ import annotations

from functools import lru_cache
import json
import math
from pathlib import Path
import re
import unicodedata

import pandas as pd


MAP_LOCATIONS_PATH = Path(__file__).with_name("ytgenerering_map_locations.json")
DEFAULT_MAP_MAX_PALL = 2.0


def _norm(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _find_col(df: pd.DataFrame, candidates: tuple[str, ...], *, required: bool = True) -> str | None:
    lookup = {_norm(col): col for col in df.columns}
    for candidate in candidates:
        match = lookup.get(_norm(candidate))
        if match is not None:
            return match
    candidate_norms = tuple(_norm(candidate) for candidate in candidates)
    for key, col in lookup.items():
        if any(candidate and candidate in key for candidate in candidate_norms):
            return col
    if required:
        raise ValueError(f"Saknar kolumn: {candidates[0]}")
    return None


def _text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _number(value: object) -> float:
    text = _text(value).replace(" ", "").replace(",", ".")
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def _optional_number(value: object) -> float | None:
    text = _text(value).replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _int_number(value: object, *, positive: bool = False) -> int | None:
    number = _optional_number(value)
    if number is None:
        return None
    if positive and number <= 0:
        return None
    return int(number)


def _location_sort_key(value: object) -> tuple[int, str]:
    text = _text(value).upper()
    match = re.fullmatch(r"UTL(\d+)(.*)", text)
    if not match:
        return 10_000, text
    return int(match.group(1)), match.group(2)


def normalize_map_location_rows(value: object) -> list[dict[str, object]]:
    if value is None:
        return []
    payload = value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        payload = json.loads(text)
    if isinstance(payload, dict):
        raw_rows = payload.get("locations") or payload.get("rows") or []
    else:
        raw_rows = payload
    if not isinstance(raw_rows, list):
        return []

    rows_by_location: dict[str, dict[str, object]] = {}
    for raw in raw_rows:
        if not isinstance(raw, dict):
            continue
        location = _text(raw.get("location") or raw.get("lagerplats") or raw.get("name")).upper()
        if not re.fullmatch(r"UTL\d+[A-ZÅÄÖ]?", location):
            continue
        x = _int_number(raw.get("x"))
        y = _int_number(raw.get("y"))
        w = _int_number(raw.get("w") if "w" in raw else raw.get("width"), positive=True)
        h = _int_number(raw.get("h") if "h" in raw else raw.get("height"), positive=True)
        if x is None or y is None or w is None or h is None:
            continue
        max_pall = _optional_number(raw.get("maxPall") if "maxPall" in raw else raw.get("max_pall")) or 0.0
        if max_pall <= 0:
            max_pall = DEFAULT_MAP_MAX_PALL
        rows_by_location[location] = {
            "location": location,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "maxPall": round(max_pall, 2),
        }
    return sorted(rows_by_location.values(), key=lambda row: _location_sort_key(row["location"]))


def _split_order_numbers(value: object) -> list[str]:
    text = _text(value)
    if not text:
        return []
    return [part.strip() for part in re.split(r"[,;\s]+", text) if part.strip()]


@lru_cache(maxsize=1)
def default_map_location_rows() -> list[dict[str, object]]:
    rows = json.loads(MAP_LOCATIONS_PATH.read_text(encoding="utf-8"))
    return normalize_map_location_rows(rows)


def map_layout_payload(locations: object | None = None) -> dict[str, object]:
    rows = normalize_map_location_rows(locations)
    return {
        "version": 1,
        "locations": rows if rows else default_map_location_rows(),
        "defaults": default_map_location_rows(),
    }


def _map_coordinates(map_locations: object | None = None) -> dict[str, dict[str, object]]:
    rows = default_map_location_rows()
    custom_rows = normalize_map_location_rows(map_locations)
    if custom_rows:
        by_location = {str(row["location"]).upper(): row for row in rows}
        by_location.update({str(row["location"]).upper(): row for row in custom_rows})
        rows = sorted(by_location.values(), key=lambda row: _location_sort_key(row["location"]))
    return {str(row["location"]).strip().upper(): row for row in rows}


def extend_locations_with_map_layout(locations: pd.DataFrame, map_locations: object | None) -> tuple[pd.DataFrame, int]:
    rows = normalize_map_location_rows(map_locations)
    if not rows:
        return locations, 0
    merged = locations.copy()
    merged["Lagerplats"] = merged["Lagerplats"].astype(str).str.strip().str.upper()
    existing = set(merged["Lagerplats"])
    additions = []
    for row in rows:
        location = str(row["location"]).upper()
        max_pall = _number(row.get("maxPall"))
        if location in existing:
            if max_pall > 0:
                merged.loc[merged["Lagerplats"].eq(location), "Max pall"] = max_pall
            continue
        sort_number, suffix = _location_sort_key(location)
        if sort_number < 1 or sort_number > 652:
            continue
        additions.append(
            {
                "Lagerplats": location,
                "Typ": "U",
                "Max pall": max_pall,
                "_location_number": sort_number,
                "_location_suffix": suffix,
            }
        )
    if not additions:
        return merged, 0
    merged = pd.concat([merged, pd.DataFrame(additions)], ignore_index=True)
    merged = merged.sort_values(["_location_number", "_location_suffix", "Lagerplats"]).reset_index(drop=True)
    return merged, len(additions)


def _forecast_order_numbers(forecast_df: pd.DataFrame) -> dict[str, list[str]]:
    if forecast_df.empty:
        return {}
    shipment_col = _find_col(forecast_df, ("Sandningsnr", "Grupp", "Shipment"), required=False)
    order_col = _find_col(forecast_df, ("Ordernummer", "Ordernr", "Order num", "order_num"), required=False)
    if not shipment_col or not order_col:
        return {}
    orders: dict[str, list[str]] = {}
    for _, row in forecast_df.iterrows():
        shipment = _text(row.get(shipment_col))
        if not shipment:
            continue
        values = orders.setdefault(shipment, [])
        for order_number in _split_order_numbers(row.get(order_col)):
            if order_number not in values:
                values.append(order_number)
    return orders


def _forecast_customers(forecast_df: pd.DataFrame) -> dict[str, dict[str, str]]:
    """Mappa Sandningsnr -> {customer, customerNum} ur forecast-tabellen."""
    if forecast_df.empty:
        return {}
    shipment_col = _find_col(forecast_df, ("Sandningsnr", "Grupp", "Shipment"), required=False)
    name_col = _find_col(forecast_df, ("Kundnamn", "Kund namn", "Customer"), required=False)
    num_col = _find_col(forecast_df, ("Kund", "Kundnr", "Custom Num"), required=False)
    if not shipment_col or (not name_col and not num_col):
        return {}
    customers: dict[str, dict[str, str]] = {}
    for _, row in forecast_df.iterrows():
        shipment = _text(row.get(shipment_col))
        if not shipment or shipment in customers:
            continue
        customers[shipment] = {
            "customer": _text(row.get(name_col)) if name_col else "",
            "customerNum": _text(row.get(num_col)) if num_col else "",
        }
    return customers


def build_ytgenerering_map_payload(
    assignments_df: pd.DataFrame,
    unplaced_df: pd.DataFrame,
    locations_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    map_locations: object | None = None,
) -> dict[str, object]:
    coordinates = _map_coordinates(map_locations)
    assignment_location_col = _find_col(assignments_df, ("Lagerplats", "Location"), required=False)
    location_col = _find_col(locations_df, ("Lagerplats", "Location", "Plats"), required=False)
    capacity_col = _find_col(locations_df, ("Max pall", "Max pallplatser", "Maxpall", "Capacity"), required=False)
    capacity_by_location: dict[str, float] = {}
    available_names: list[str] = []

    if location_col:
        for _, row in locations_df.iterrows():
            name = _text(row.get(location_col)).upper()
            if not name:
                continue
            available_names.append(name)
            if capacity_col:
                capacity_by_location[name] = _number(row.get(capacity_col))

    if assignment_location_col:
        max_col = _find_col(assignments_df, ("Max pall", "Maxpall", "Capacity"), required=False)
        for _, row in assignments_df.iterrows():
            name = _text(row.get(assignment_location_col)).upper()
            if name and max_col and name not in capacity_by_location:
                capacity_by_location[name] = _number(row.get(max_col))

    seen_locations: set[str] = set()
    locations: list[dict[str, object]] = []
    missing_coordinates: list[str] = []
    for name in available_names:
        if name in seen_locations:
            continue
        seen_locations.add(name)
        coord = coordinates.get(name)
        if not coord:
            missing_coordinates.append(name)
            continue
        locations.append(
            {
                "location": name,
                "x": coord["x"],
                "y": coord["y"],
                "w": coord["w"],
                "h": coord["h"],
                "maxPall": round(capacity_by_location.get(name, 0.0), 2),
            }
        )

    shipment_col = _find_col(assignments_df, ("Sandningsnr", "Grupp", "Shipment"), required=False)
    carrier_col = _find_col(assignments_df, ("Transportor", "Carrier"), required=False)
    cluster_col = _find_col(assignments_df, ("Kluster", "Cluster", "Cluster group"), required=False)
    placed_col = _find_col(assignments_df, ("Placerade pallplatser", "Placed pallets"), required=False)
    shipment_pallets_col = _find_col(assignments_df, ("Sandningens pallplatser", "Shipment pallets"), required=False)
    max_col = _find_col(assignments_df, ("Max pall", "Maxpall", "Capacity"), required=False)
    unused_col = _find_col(assignments_df, ("Outnyttjad kapacitet", "Unused capacity"), required=False)
    placement_col = _find_col(assignments_df, ("Placering nr", "Placement"), required=False)
    order_numbers = _forecast_order_numbers(forecast_df)
    customers = _forecast_customers(forecast_df)

    assignments: list[dict[str, object]] = []
    if assignment_location_col:
        for index, row in assignments_df.reset_index(drop=True).iterrows():
            location = _text(row.get(assignment_location_col)).upper()
            shipment = _text(row.get(shipment_col)) if shipment_col else ""
            placed = _number(row.get(placed_col)) if placed_col else 0.0
            max_pall = _number(row.get(max_col)) if max_col else capacity_by_location.get(location, 0.0)
            customer = customers.get(shipment, {})
            assignments.append(
                {
                    "id": f"{index + 1}:{shipment}:{location}",
                    "shipment": shipment,
                    "carrier": _text(row.get(carrier_col)) if carrier_col else "",
                    "cluster": _text(row.get(cluster_col)) if cluster_col else "",
                    "customer": customer.get("customer", ""),
                    "customerNum": customer.get("customerNum", ""),
                    "location": location,
                    "placedPallets": round(placed, 2),
                    "shipmentPallets": round(_number(row.get(shipment_pallets_col)), 2)
                    if shipment_pallets_col
                    else 0.0,
                    "maxPall": round(max_pall, 2),
                    "unusedCapacity": round(_number(row.get(unused_col)), 2)
                    if unused_col
                    else round(max_pall - placed, 2),
                    "placementNo": int(_number(row.get(placement_col))) if placement_col else index + 1,
                    "orderNumbers": order_numbers.get(shipment, []),
                }
            )

    if not locations:
        for location in sorted({assignment["location"] for assignment in assignments if assignment.get("location")}):
            coord = coordinates.get(str(location))
            if not coord:
                continue
            locations.append(
                {
                    "location": location,
                    "x": coord["x"],
                    "y": coord["y"],
                    "w": coord["w"],
                    "h": coord["h"],
                    "maxPall": round(capacity_by_location.get(str(location), 0.0), 2),
                }
            )

    bounds = {}
    if locations:
        bounds = {
            "minX": min(float(loc["x"]) for loc in locations),
            "minY": min(float(loc["y"]) for loc in locations),
            "maxX": max(float(loc["x"]) + float(loc["w"]) for loc in locations),
            "maxY": max(float(loc["y"]) + float(loc["h"]) for loc in locations),
        }

    unplaced = []
    if not unplaced_df.empty:
        unplaced_shipment_col = _find_col(unplaced_df, ("Sandningsnr", "Grupp", "Shipment"), required=False)
        unplaced_carrier_col = _find_col(unplaced_df, ("Transportor", "Carrier"), required=False)
        unplaced_pall_col = _find_col(unplaced_df, ("Ej placerade pallplatser", "Pallplatser"), required=False)
        for record in unplaced_df.to_dict("records"):
            shipment = _text(record.get(unplaced_shipment_col)) if unplaced_shipment_col else ""
            customer = customers.get(shipment, {})
            record["shipment"] = shipment
            record["carrier"] = _text(record.get(unplaced_carrier_col)) if unplaced_carrier_col else ""
            record["customer"] = customer.get("customer", "")
            record["customerNum"] = customer.get("customerNum", "")
            record["unplacedPallets"] = _number(record.get(unplaced_pall_col)) if unplaced_pall_col else 0.0
            unplaced.append(record)
    return {
        "key": "ytgenerering-map",
        "type": "warehouse-location-map",
        "label": "Ytkarta",
        "locations": locations,
        "assignments": assignments,
        "unplaced": unplaced,
        "missingCoordinates": sorted(missing_coordinates),
        "bounds": bounds,
    }

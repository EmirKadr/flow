from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata

import pandas as pd


MAP_LOCATIONS_PATH = Path(__file__).with_name("ytgenerering_map_locations.json")


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


def _split_order_numbers(value: object) -> list[str]:
    text = _text(value)
    if not text:
        return []
    return [part.strip() for part in re.split(r"[,;\s]+", text) if part.strip()]


@lru_cache(maxsize=1)
def _map_coordinates() -> dict[str, dict[str, object]]:
    rows = json.loads(MAP_LOCATIONS_PATH.read_text(encoding="utf-8"))
    return {str(row["location"]).strip().upper(): row for row in rows}


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
) -> dict[str, object]:
    coordinates = _map_coordinates()
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

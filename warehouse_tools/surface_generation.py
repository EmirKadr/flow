from __future__ import annotations

from dataclasses import dataclass
import math
import re
import unicodedata

import pandas as pd


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


def generate_surface_plan(forecast: pd.DataFrame, locations: pd.DataFrame) -> SurfaceGenerationResult:
    shipments = prepare_forecast(forecast)
    surfaces = prepare_locations(locations)
    if surfaces.empty:
        raise ValueError("Lagerplatser saknar giltiga ytor: Typ U, UTL1-UTL652, minst 6 tecken och Max pall > 0.")

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

    assignments_df = pd.DataFrame(assignments)
    unplaced_df = pd.DataFrame(unplaced)

    if assignments_df.empty:
        carrier_overview = pd.DataFrame(
            columns=[
                "Transportör",
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

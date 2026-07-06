"""Bearbeta-flodena som paket: ett API-handtag per flode.

Tidigare en enda flows.py (1 400+ rader); uppdelad 2026-07 per doman med
registryt kvar har. Tester ska monkeypatcha implementationsmodulen
(t.ex. flows.shared._read, flows.forecast_flows.flow_forecast).
"""
from __future__ import annotations

from .shared import (
    DEFAULT_MAX_CSV_PARAM,
    PROCESS_AREA_FOCUS_PARAM,
    FileVersion,
    WAREHOUSE_RUNTIME_CACHE_TTL_SECONDS,
    WAREHOUSE_RUNTIME_CACHE_MAX_ITEMS,
    WAREHOUSE_RUNTIME_CACHE_APPROX_BYTES_PER_ITEM,
    WAREHOUSE_RUNTIME_CACHE_MAX_APPROX_BYTES,
    _WAREHOUSE_RUNTIME_CACHE_CREATED_AT,
    _runtime_cache_info,
    _maybe_trim_runtime_caches,
    _read_cached,
    _read,
    _file_version,
    _optional_file_version,
    _temp,
    _max_csv_path,
    _column_key,
    _find_table_column,
    _clean_cell,
    _split_order_numbers,
    _tsv_content,
    _normalize_lookup_value,
    _find_required_column,
)
from .allocation_flows import (
    NEAR_MISS_COLUMNS,
    ALLOCATE_DISPLAY_SUMMARY_TYPES,
    ORDERSALDO_HELPALL_COLUMN,
    _normalized_saldo_cached,
    _read_normalized_saldo,
    _normalized_items_cached,
    _read_normalized_items,
    _normalized_not_putaway_cached,
    _read_normalized_not_putaway,
    _allocation_outputs_cached,
    clear_allocation_cache,
    build_allocate_display_summary,
    add_ordersaldo_helpall_count,
    flow_allocate,
    flow_ordersaldo,
    flow_lyx,
    flow_pafyllnadsprio,
)
from .goods_declaration import (
    GOTLAND_POSTCODE_MIN,
    GOTLAND_POSTCODE_MAX,
    GOTLAND_POSTCODE_ROWS,
    _dangerous_goods_level,
    _postcode_digits,
    _is_gotland_postcode,
    _security_levels_by_item,
    _address_sea_lookup,
    _overview_address_lookup,
    _order_address_column,
    _lq_sea_status,
    flow_goods_declaration,
)
from .report_flows import (
    flow_hib_koppling,
    flow_overview_check,
    flow_dispatch_check,
    flow_vecka27_check,
    flow_prognos_report,
    flow_observations_update,
    flow_observations_sync,
    flow_split_values,
    flow_update_check,
)
from .forecast_flows import (
    ORDER_SET_AREA_IMPORT_KEY,
    ORDER_SET_AREA_IMPORT_LABEL,
    ORDER_SET_AREA_IMPORT_FILENAME,
    ORDER_SET_AREA_IMPORT_COLUMNS,
    YTGENERERING_UTL_MIN_PARAM,
    YTGENERERING_UTL_MAX_PARAM,
    YTGENERERING_UTL_DEFAULT_MIN,
    YTGENERERING_UTL_DEFAULT_MAX,
    _prepared_locations_cached,
    _read_prepared_locations,
    clear_prepared_location_cache,
    warm_prepared_locations,
    _ytgenerering_utl_number,
    _ytgenerering_utl_range,
    _filter_ytgenerering_locations,
    build_order_set_area_import,
    FORECAST_FILE_LABELS,
    _require_files,
    flow_forecast,
    _forecast_dataframe_from_params,
    _forecast_dataframe_from_result,
    _flow_ytgenerering_from_forecast_df,
    flow_ytgenerering,
)
from .shared import E  # bakatkompatibel alias: flows.E



# --- Registry ----------------------------------------------------------------
# Varje post: id, label, category, description, inputs[], handler.
# input.type: file | text | number | textarea
# input.detect: lista av filtyper (fran motorns _detect_file_type) som auto-routas hit.

FLOWS: list[dict] = [
    {
        "id": "allocate", "label": "Allokering", "category": "Allokering",
        "description": "Allokera kundorder mot buffertpallar (Helpall -> AutoStore -> Huvudplock, FIFO) med near-miss-loggning, refill och pallplatsberäkning.",
        "handler": flow_allocate,
        "inputs": [
            {"key": "orders", "label": "Detalj Kundorder (Alla)", "type": "file", "required": True, "detect": ["orders"]},
            {"key": "buffer", "label": "Buffertpall", "type": "file", "required": True, "detect": ["buffer"]},
            {"key": "saldo", "label": "Saldo Inkl. Automation", "type": "file", "required": False, "detect": ["automation"]},
            {"key": "items", "label": "Item Option", "type": "file", "required": False, "detect": ["item", "item_option"]},
            {"key": "not_putaway", "label": "Ej Inlagrade Artiklar", "type": "file", "required": False, "detect": ["not_putaway", "wms_booking"]},
        ],
    },
    {
        "id": "forecast", "label": "Forecast", "category": "Forecast & yta",
        "description": "Prognostisera pallplatser per sändningsnr med lokala orderfiler och kärnfiler.",
        "handler": flow_forecast,
        "hidden": True,
        "inputs": [
            {"key": "orders", "label": "Detalj Kundorder (Alla)", "type": "file", "required": True, "detect": ["orders"]},
            {"key": "overview", "label": "Orderöversikt", "type": "file", "required": True, "detect": ["overview"]},
            {"key": "buffer", "label": "Buffertpall", "type": "file", "required": True, "detect": ["buffer"]},
        ],
        "coredata": [
            {"key": "custom", "label": "custom", "required": True},
            {"key": "item", "label": "item", "required": True},
            {"key": "item_alias", "label": "item_alias", "required": True},
            {"key": "dimension", "label": "dimension", "required": True},
            {"key": "pallet_type", "label": "pallet_type", "required": True},
            {"key": "item_option", "label": "item_option", "required": True},
            {"key": "trans_agency", "label": "Transportör", "required": False},
        ],
    },
    {
        "id": "ytgenerering", "label": "Ytgenerering", "category": "Forecast & yta",
        "description": "Kör Forecast och skapar ytkarta/importfil när lagerplatser finns.",
        "handler": flow_ytgenerering,
        "inputs": [
            {"key": "orders", "label": "Detalj Kundorder (Alla)", "type": "file", "required": True, "detect": ["orders"]},
            {"key": "overview", "label": "Orderöversikt", "type": "file", "required": True, "detect": ["overview"]},
            {"key": "buffer", "label": "Buffertpall", "type": "file", "required": True, "detect": ["buffer"]},
        ],
        "coredata": [
            {"key": "custom", "label": "custom", "required": True},
            {"key": "item", "label": "item", "required": True},
            {"key": "item_alias", "label": "item_alias", "required": True},
            {"key": "dimension", "label": "dimension", "required": True},
            {"key": "pallet_type", "label": "pallet_type", "required": True},
            {"key": "item_option", "label": "item_option", "required": True},
            {"key": "trans_agency", "label": "Transportör", "required": False},
            {"key": "location", "label": "Lagerplatser", "required": False},
        ],
    },
    {
        "id": "ordersaldo", "label": "Ordersaldo", "category": "Order & saldo",
        "description": "Beräkna kompletta ordrar och artiklar med underskott utifrån Detalj Kundorder (Alla).",
        "handler": flow_ordersaldo,
        "inputs": [
            {"key": "orders", "label": "Detalj Kundorder (Alla)", "type": "file", "required": True, "detect": ["orders"]},
            {"key": "saldo", "label": "Saldo Inkl. Automation", "type": "file", "required": False, "detect": ["automation"]},
            {"key": "max_csv", "label": "artikel_max.csv (sammanställd data)", "type": "file", "required": False, "detect": []},
        ],
    },
    {
        "id": "lyx", "label": "LYX-artiklar", "category": "Order & saldo",
        "description": "Identifiera LYX-artiklar utifrån en saldofil och artikel_max-referens.",
        "handler": flow_lyx,
        "inputs": [
            {"key": "saldo", "label": "Saldofil", "type": "file", "required": True, "detect": ["automation", "buffer"]},
            {"key": "max_csv", "label": "artikel_max.csv (sammanställd data)", "type": "file", "required": False, "detect": []},
        ],
    },
    {
        "id": "pafyllnadsprio", "label": "Påfyllnadsprio", "category": "Order & saldo",
        "description": "Prioritera påfyllnad utifrån underskott med saldo och orderöversikt i lastningsfönster-läge.",
        "handler": flow_pafyllnadsprio,
        "inputs": [
            {"key": "orders", "label": "Detalj Kundorder (Alla)", "type": "file", "required": True, "detect": ["orders"]},
            {"key": "saldo", "label": "Saldo Inkl. Automation", "type": "file", "required": True, "detect": ["automation"]},
            {"key": "overview", "label": "Orderöversikt (lastningsfönster)", "type": "file", "required": True, "detect": ["overview"]},
            {"key": "max_csv", "label": "artikel_max.csv (sammanställd data)", "type": "file", "required": False, "detect": []},
        ],
    },
    {
        "id": "hib-koppling", "label": "HIB-koppling", "category": "Kontroller",
        "description": "Räkna ut vilka HIB-ordrar som behöver kopplas om samt missade avgångar.",
        "handler": flow_hib_koppling,
        "inputs": [
            {"key": "details", "label": "Detalj Kundorder (Alla)", "type": "file", "required": True, "detect": ["orders"]},
            {"key": "overview", "label": "Orderöversikt", "type": "file", "required": True, "detect": ["overview"]},
        ],
    },
    {
        "id": "overview-check", "label": "Orderöversiktkontroll", "category": "Kontroller",
        "description": "Hitta sändningsnr med flera kunder/transportörer och HIB utan butikssändning.",
        "handler": flow_overview_check,
        "inputs": [
            {"key": "overview", "label": "Orderöversikt", "type": "file", "required": True, "detect": ["overview"]},
            {"key": "details", "label": "Detalj Kundorder (Alla)", "type": "file", "required": False, "detect": ["orders"]},
        ],
    },
    {
        "id": "dispatch-check", "label": "Dispatchkontroll", "category": "Kontroller",
        "description": "Jämför orderöversikt mot dispatchpallar och lista avvikelser.",
        "handler": flow_dispatch_check,
        "inputs": [
            {"key": "overview", "label": "Orderöversikt", "type": "file", "required": True, "detect": ["overview"]},
            {"key": "dispatch", "label": "Dispatchpallar", "type": "file", "required": True, "detect": ["dispatch"]},
            {"key": "details", "label": "Detalj Kundorder (Alla)", "type": "file", "required": False, "detect": ["orders"]},
        ],
    },
    {
        "id": "goods-declaration", "label": "Godsdeklaration", "category": "Kontroller",
        "description": "Kontrollera DG/LQ-artiklar mot artikel säkerhetsinformation och Gotlandsadresser för sjö/hav.",
        "handler": flow_goods_declaration,
        "inputs": [
            {"key": "orders", "label": "Detalj Kundorder (Alla)", "type": "file", "required": True, "detect": ["orders"]},
            {"key": "overview", "label": "Orderöversikt (adressnummer)", "type": "file", "required": True, "detect": ["overview"]},
            {"key": "custom_adr", "label": "Alternativ Leveransadress", "type": "file", "required": True, "detect": ["custom_adr"]},
        ],
        "coredata": [
            {"key": "item_security_info", "label": "Artikel Säkerhetsinformation", "required": True},
        ],
    },
    {
        "id": "vecka27-check", "label": "Vecka 27-kontroll", "category": "Kontroller",
        "description": "Kontrollera orderrader mot vecka 27-reglerna.",
        "handler": flow_vecka27_check,
        "inputs": [
            {"key": "orders", "label": "Detalj Kundorder (Alla)", "type": "file", "required": True, "detect": ["orders"]},
        ],
    },
    {
        "id": "prognos-report", "label": "Prognosrapport", "category": "Sökning & prognos",
        "description": "Bygg prognos-/kampanjrapport mot autoplock. Saldo krävs (Robot=Y-filter).",
        "handler": flow_prognos_report,
        "inputs": [
            {"key": "prognos", "label": "Prognosfil", "type": "file", "required": False, "detect": ["prognos"]},
            {"key": "campaign", "label": "Kampanjfil", "type": "file", "required": False, "detect": ["campaign"]},
            {"key": "saldo", "label": "Saldo Inkl. Automation", "type": "file", "required": True, "detect": ["automation"]},
            {"key": "buffer", "label": "Buffertpall", "type": "file", "required": False, "detect": ["buffer"]},
        ],
    },
    {
        "id": "observations-update", "label": "Observations-uppdatering", "category": "Data & verktyg",
        "description": "Lägg till nya status-30-pallar i observations och räkna om artikel_max. Skriver till temporära filer.",
        "handler": flow_observations_update,
        "inputs": [
            {"key": "buffer", "label": "Buffertpall", "type": "file", "required": True, "detect": ["buffer"]},
        ],
    },
    {
        "id": "observations-sync", "label": "Observations-synk", "category": "Data & verktyg",
        "description": "Hämta observations från GitHub (eller en lokal fil). Ingen push, skriver till temporära filer.",
        "handler": flow_observations_sync,
        "inputs": [
            {"key": "remote_file", "label": "Lokal observationsfil (valfri)", "type": "file", "required": False, "detect": []},
        ],
    },
    {
        "id": "split-values", "label": "Dela värden", "category": "Data & verktyg",
        "description": "Dela en lång lista av värden i kolumner med valbar kolumnstorlek.",
        "handler": flow_split_values,
        "inputs": [
            {"key": "values", "label": "Värden (ett per rad)", "type": "textarea", "required": False},
            {"key": "values_file", "label": "...eller ladda upp textfil", "type": "file", "required": False, "detect": []},
            {"key": "chunk_size", "label": "Antal per kolumn", "type": "number", "required": False, "default": "2000"},
        ],
    },
    {
        "id": "update-check", "label": "Uppdateringskoll", "category": "Data & verktyg",
        "description": "Kontrollera om en nyare version av appen finns på GitHub.",
        "handler": flow_update_check,
        "inputs": [],
    },
]

FLOW_BY_ID: dict[str, dict] = {flow["id"]: flow for flow in FLOWS}

# Flöden som visas som egna vyer. Allt övrigt samlas i den kombinerade
# huvudvyn där filerna delas mellan körningarna.
SOLO_FLOWS = {
    "observations-update",
    "observations-sync",
    "split-values",
    "update-check",
}


# Gemensam datapool: combined-flöden laddar upp filerna EN gång här, och
# varje flödes filinput mappas till en pool-nyckel. Endast "details" skiljer
# sig från sin pool-nyckel (samma filformat som "orders").
DATA_POOL: list[dict] = [
    {"key": "orders", "label": "Detalj Kundorder (Alla)", "detect": ["orders"]},
    {"key": "buffer", "label": "Buffertpall", "detect": ["buffer"]},
    {"key": "saldo", "label": "Saldo Inkl. Automation", "detect": ["automation"]},
    {"key": "overview", "label": "Orderöversikt", "detect": ["overview"]},
    {"key": "dispatch", "label": "Dispatchpallar", "detect": ["dispatch"]},
    {"key": "custom_adr", "label": "Alternativ Leveransadress", "detect": ["custom_adr"]},
    {"key": "items", "label": "Item Option", "detect": ["item", "item_option"]},
    {"key": "not_putaway", "label": "Ej Inlagrade Artiklar", "detect": ["not_putaway", "wms_booking"]},
    {"key": "prognos", "label": "Prognosfil", "detect": ["prognos"]},
    {"key": "campaign", "label": "Kampanjfil", "detect": ["campaign"]},
    {"key": "max_csv", "label": "artikel_max.csv", "detect": []},
]

_POOL_KEY_OVERRIDE = {"details": "orders"}


def _pool_key(input_key: str) -> str:
    return _POOL_KEY_OVERRIDE.get(input_key, input_key)


def public_registry() -> list[dict]:
    """Registret utan handler-referenser - sant till frontenden.

    Varje flöde får ett ``view``-fält: ``solo`` (egen vy) eller
    ``combined`` (delar huvudvyn med övriga combined-flöden). Filinputs i
    combined-flöden får en ``pool``-nyckel mot den gemensamma datapoolen.
    """
    result: list[dict] = []
    for flow in FLOWS:
        if flow.get("hidden"):
            continue
        view = "solo" if flow["id"] in SOLO_FLOWS else "combined"
        inputs: list[dict] = []
        for inp in flow["inputs"]:
            new_inp = dict(inp)
            if view == "combined" and inp.get("type") == "file":
                new_inp["pool"] = _pool_key(inp["key"])
            inputs.append(new_inp)
        result.append({
            **{key: value for key, value in flow.items() if key != "handler"},
            "inputs": inputs,
            "view": view,
        })
    return result


def public_pool() -> list[dict]:
    """Datapoolens slots - sänt till frontenden för den kombinerade vyn."""
    return [dict(slot) for slot in DATA_POOL]

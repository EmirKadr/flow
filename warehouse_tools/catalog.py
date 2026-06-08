"""Lightweight warehouse tool catalog.

This module is intentionally dependency-free. The web/app UI can load flow
metadata and upload slots without importing the old allocation runtime.
"""
from __future__ import annotations

from copy import deepcopy


CATALOG_FLOWS: list[dict] = [
    {
        "id": "allocate",
        "label": "Allokering",
        "category": "Allokering",
        "description": "Allokera kundorder mot buffertpallar med near-miss, refill och pallplatsberäkning.",
        "inputs": [
            {"key": "orders", "label": "Detalj Kundorder (Alla)", "type": "file", "required": True, "detect": ["orders"]},
            {"key": "buffer", "label": "Buffertpall", "type": "file", "required": True, "detect": ["buffer"]},
            {"key": "saldo", "label": "Saldo Inkl. Automation", "type": "file", "required": False, "detect": ["automation"]},
            {"key": "items", "label": "Item Option", "type": "file", "required": False, "detect": ["item", "item_option"]},
            {"key": "not_putaway", "label": "Ej Inlagrade Artiklar", "type": "file", "required": False, "detect": ["not_putaway", "wms_booking"]},
        ],
    },
    {
        "id": "forecast",
        "label": "Forecast",
        "category": "Forecast & yta",
        "description": "Prognostisera pallplatser per sändningsnr med lokala orderfiler och kärnfiler.",
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
        "id": "ytgenerering",
        "label": "Ytgenerering",
        "category": "Forecast & yta",
        "description": "Kör Forecast och skapar ytkarta/importfil när lagerplatser finns.",
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
        "id": "ordersaldo",
        "label": "Ordersaldo",
        "category": "Order & saldo",
        "description": "Beräkna kompletta ordrar och artiklar med underskott utifrån Detalj Kundorder (Alla).",
        "inputs": [
            {"key": "orders", "label": "Detalj Kundorder (Alla)", "type": "file", "required": True, "detect": ["orders"]},
            {"key": "saldo", "label": "Saldo Inkl. Automation", "type": "file", "required": False, "detect": ["automation"]},
            {"key": "max_csv", "label": "artikel_max.csv (sammanställd data)", "type": "file", "required": False, "detect": []},
        ],
    },
    {
        "id": "lyx",
        "label": "LYX-artiklar",
        "category": "Order & saldo",
        "description": "Identifiera LYX-artiklar utifrån en saldofil och artikel_max-referens.",
        "inputs": [
            {"key": "saldo", "label": "Saldofil", "type": "file", "required": True, "detect": ["automation", "buffer"]},
            {"key": "max_csv", "label": "artikel_max.csv (sammanställd data)", "type": "file", "required": False, "detect": []},
        ],
    },
    {
        "id": "pafyllnadsprio",
        "label": "Påfyllnadsprio",
        "category": "Order & saldo",
        "description": "Prioritera påfyllnad utifrån underskott med saldo och orderöversikt i lastningsfönster-läge.",
        "inputs": [
            {"key": "orders", "label": "Detalj Kundorder (Alla)", "type": "file", "required": True, "detect": ["orders"]},
            {"key": "saldo", "label": "Saldo Inkl. Automation", "type": "file", "required": True, "detect": ["automation"]},
            {"key": "overview", "label": "Orderöversikt (lastningsfönster)", "type": "file", "required": True, "detect": ["overview"]},
            {"key": "max_csv", "label": "artikel_max.csv (sammanställd data)", "type": "file", "required": False, "detect": []},
        ],
    },
    {
        "id": "hib-koppling",
        "label": "HIB-koppling",
        "category": "Kontroller",
        "description": "Räkna ut vilka HIB-ordrar som behöver kopplas om samt missade avgångar.",
        "inputs": [
            {"key": "details", "label": "Detalj Kundorder (Alla)", "type": "file", "required": True, "detect": ["orders"]},
            {"key": "overview", "label": "Orderöversikt", "type": "file", "required": True, "detect": ["overview"]},
        ],
    },
    {
        "id": "overview-check",
        "label": "Orderöversiktkontroll",
        "category": "Kontroller",
        "description": "Hitta sändningsnr med flera kunder/transportörer och HIB utan butikssändning.",
        "inputs": [
            {"key": "overview", "label": "Orderöversikt", "type": "file", "required": True, "detect": ["overview"]},
            {"key": "details", "label": "Detalj Kundorder (Alla)", "type": "file", "required": False, "detect": ["orders"]},
        ],
    },
    {
        "id": "dispatch-check",
        "label": "Dispatchkontroll",
        "category": "Kontroller",
        "description": "Jämför orderöversikt mot dispatchpallar och lista avvikelser.",
        "inputs": [
            {"key": "overview", "label": "Orderöversikt", "type": "file", "required": True, "detect": ["overview"]},
            {"key": "dispatch", "label": "Dispatchpallar", "type": "file", "required": True, "detect": ["dispatch"]},
            {"key": "details", "label": "Detalj Kundorder (Alla)", "type": "file", "required": False, "detect": ["orders"]},
        ],
    },
    {
        "id": "goods-declaration",
        "label": "Godsdeklaration",
        "category": "Kontroller",
        "description": "Kontrollera DG/LQ-artiklar mot artikel säkerhetsinformation och Gotlandsadresser för sjö/hav.",
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
        "id": "vecka27-check",
        "label": "Vecka 27-kontroll",
        "category": "Kontroller",
        "description": "Kontrollera orderrader mot vecka 27-reglerna.",
        "inputs": [
            {"key": "orders", "label": "Detalj Kundorder (Alla)", "type": "file", "required": True, "detect": ["orders"]},
        ],
    },
    {
        "id": "prognos-report",
        "label": "Prognosrapport",
        "category": "Sökning & prognos",
        "description": "Bygg prognos-/kampanjrapport mot autoplock. Saldo krävs för Robot=Y-filter.",
        "inputs": [
            {"key": "prognos", "label": "Prognosfil", "type": "file", "required": False, "detect": ["prognos"]},
            {"key": "campaign", "label": "Kampanjfil", "type": "file", "required": False, "detect": ["campaign"]},
            {"key": "saldo", "label": "Saldo Inkl. Automation", "type": "file", "required": True, "detect": ["automation"]},
            {"key": "buffer", "label": "Buffertpall", "type": "file", "required": False, "detect": ["buffer"]},
        ],
    },
    {
        "id": "observations-update",
        "label": "Observations-uppdatering",
        "category": "Data & verktyg",
        "description": "Lägg till nya status-30-pallar i observations och räkna om artikel_max.",
        "inputs": [
            {"key": "buffer", "label": "Buffertpall", "type": "file", "required": True, "detect": ["buffer"]},
        ],
    },
    {
        "id": "observations-sync",
        "label": "Observations-synk",
        "category": "Data & verktyg",
        "description": "Hämta observations från GitHub eller en lokal fil.",
        "inputs": [
            {"key": "remote_file", "label": "Lokal observationsfil (valfri)", "type": "file", "required": False, "detect": []},
        ],
    },
    {
        "id": "split-values",
        "label": "Dela värden",
        "category": "Data & verktyg",
        "description": "Dela en lång lista av värden i kolumner med valbar kolumnstorlek.",
        "inputs": [
            {"key": "values", "label": "Värden (ett per rad)", "type": "textarea", "required": False},
            {"key": "values_file", "label": "...eller ladda upp textfil", "type": "file", "required": False, "detect": []},
            {"key": "chunk_size", "label": "Antal per kolumn", "type": "number", "required": False, "default": "2000"},
        ],
    },
    {
        "id": "update-check",
        "label": "Uppdateringskoll",
        "category": "Data & verktyg",
        "description": "Kontrollera om en nyare version av appen finns på GitHub.",
        "inputs": [],
    },
]

FLOW_BY_ID: dict[str, dict] = {flow["id"]: flow for flow in CATALOG_FLOWS}

SOLO_FLOWS = {
    "observations-update",
    "observations-sync",
    "split-values",
    "update-check",
}

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
    result: list[dict] = []
    for flow in CATALOG_FLOWS:
        if flow.get("hidden"):
            continue
        view = "solo" if flow["id"] in SOLO_FLOWS else "combined"
        inputs: list[dict] = []
        for inp in flow["inputs"]:
            new_inp = dict(inp)
            if view == "combined" and inp.get("type") == "file":
                new_inp["pool"] = _pool_key(inp["key"])
            inputs.append(new_inp)
        result.append({**deepcopy(flow), "inputs": inputs, "view": view})
    return result


def public_pool() -> list[dict]:
    return [dict(slot) for slot in DATA_POOL]

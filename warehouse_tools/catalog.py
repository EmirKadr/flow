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
            {"key": "orders", "label": "Detalj Kundorder(alla)", "type": "file", "required": True, "detect": ["orders"]},
            {"key": "buffer", "label": "Buffertpallar", "type": "file", "required": True, "detect": ["buffer"]},
            {"key": "saldo", "label": "Saldo ink. Automation", "type": "file", "required": False, "detect": ["automation"]},
            {"key": "items", "label": "Item option", "type": "file", "required": False, "detect": ["item"]},
            {"key": "not_putaway", "label": "Ej inlagrade", "type": "file", "required": False, "detect": []},
        ],
    },
    {
        "id": "ordersaldo",
        "label": "Ordersaldo",
        "category": "Order & saldo",
        "description": "Beräkna kompletta ordrar och artiklar med underskott utifrån Detalj Kundorder(alla).",
        "inputs": [
            {"key": "orders", "label": "Detalj Kundorder(alla)", "type": "file", "required": True, "detect": ["orders"]},
            {"key": "saldo", "label": "Saldo ink. Automation (Utbeställt)", "type": "file", "required": False, "detect": ["automation"]},
        ],
    },
    {
        "id": "lyx",
        "label": "LYX-artiklar",
        "category": "Order & saldo",
        "description": "Identifiera LYX-artiklar utifrån en saldofil och artikel_max-referens.",
        "inputs": [
            {"key": "saldo", "label": "Saldofil", "type": "file", "required": True, "detect": ["automation", "buffer"]},
            {"key": "max_csv", "label": "artikel_max.csv (kärnfil)", "type": "file", "required": False, "detect": []},
        ],
    },
    {
        "id": "pafyllnadsprio",
        "label": "Påfyllnadsprio",
        "category": "Order & saldo",
        "description": "Prioritera påfyllnad utifrån underskott. Med orderöversikt används lastningsfönster-läge.",
        "inputs": [
            {"key": "orders", "label": "Detalj Kundorder(alla)", "type": "file", "required": True, "detect": ["orders"]},
            {"key": "saldo", "label": "Saldo ink. Automation", "type": "file", "required": False, "detect": ["automation"]},
            {"key": "overview", "label": "Orderöversikt (lastningsfönster)", "type": "file", "required": False, "detect": ["overview"]},
            {"key": "max_csv", "label": "artikel_max.csv (kärnfil)", "type": "file", "required": False, "detect": []},
        ],
    },
    {
        "id": "hib-koppling",
        "label": "HIB-koppling",
        "category": "Kontroller",
        "description": "Räkna ut vilka HIB-ordrar som behöver kopplas om samt missade avgångar.",
        "inputs": [
            {"key": "details", "label": "Detalj Kundorder(alla)", "type": "file", "required": True, "detect": ["orders"]},
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
            {"key": "details", "label": "Detalj Kundorder(alla) (kundnamn)", "type": "file", "required": False, "detect": ["orders"]},
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
            {"key": "details", "label": "Detalj Kundorder(alla) (kundnamn)", "type": "file", "required": False, "detect": ["orders"]},
        ],
    },
    {
        "id": "vecka27-check",
        "label": "Vecka 27-kontroll",
        "category": "Kontroller",
        "description": "Kontrollera orderrader mot vecka 27-reglerna.",
        "inputs": [
            {"key": "orders", "label": "Detalj Kundorder(alla)", "type": "file", "required": True, "detect": ["orders"]},
        ],
    },
    {
        "id": "eftersok",
        "label": "Eftersök",
        "category": "Sökning & prognos",
        "description": "Spåra en artikel/pall genom WMS-loggarna utifrån inköps- och artikelnummer.",
        "inputs": [
            {"key": "purchase", "label": "Inköpsnummer", "type": "text", "required": True},
            {"key": "article", "label": "Artikelnummer", "type": "text", "required": True},
            {"key": "wms_receive", "label": "Mottagningslogg", "type": "file", "required": True, "detect": ["wms_receive"]},
            {"key": "wms_booking", "label": "Inlagringslogg", "type": "file", "required": False, "detect": ["wms_booking"]},
            {"key": "wms_buffert", "label": "Buffertpallar", "type": "file", "required": False, "detect": ["buffer"]},
            {"key": "wms_trans", "label": "Transaktionslogg", "type": "file", "required": False, "detect": ["wms_trans"]},
            {"key": "wms_pick", "label": "Plocklogg", "type": "file", "required": False, "detect": ["wms_pick"]},
            {"key": "wms_correct", "label": "Korrigeringslogg", "type": "file", "required": False, "detect": ["wms_correct"]},
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
            {"key": "saldo", "label": "Saldo ink. Automation", "type": "file", "required": True, "detect": ["automation"]},
            {"key": "buffer", "label": "Buffertpallar", "type": "file", "required": False, "detect": ["buffer"]},
        ],
    },
    {
        "id": "observations-update",
        "label": "Observations-uppdatering",
        "category": "Data & verktyg",
        "description": "Lägg till nya status-30-pallar i observations och räkna om artikel_max.",
        "inputs": [
            {"key": "buffer", "label": "Buffertpallar", "type": "file", "required": True, "detect": ["buffer"]},
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
    "eftersok",
    "observations-update",
    "observations-sync",
    "split-values",
    "update-check",
}

DATA_POOL: list[dict] = [
    {"key": "orders", "label": "Detalj Kundorder(alla)", "detect": ["orders"]},
    {"key": "buffer", "label": "Buffertpallar", "detect": ["buffer"]},
    {"key": "saldo", "label": "Saldo ink. Automation", "detect": ["automation"]},
    {"key": "overview", "label": "Orderöversikt", "detect": ["overview"]},
    {"key": "dispatch", "label": "Dispatchpallar", "detect": ["dispatch"]},
    {"key": "items", "label": "Item option", "detect": ["item"]},
    {"key": "not_putaway", "label": "Ej inlagrade", "detect": []},
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

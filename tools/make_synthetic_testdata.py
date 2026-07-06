"""Generera syntetisk, deterministisk testdata för warehouse-flödena.

Kör:  python -m tools.make_synthetic_testdata

Skriver TSV-filer (utf-8-sig, tab, samma format som ASK-exporterna) till
tests/services/fixtures/synthetic/data/ utifrån kolumnspecen i
tests/services/fixtures/synthetic/columns.json. Alla värden är påhittade
(artiklar SYNT-A*, order 99xxxx, kunder KUND-*) — inga kund- eller lagerdata.
Deterministiskt seed så filerna är byte-stabila; ett kontraktstest verifierar
att incheckade filer matchar generatorn.

Syfte: karakteriseringstesterna kan köra i CI (där privat testdata/ saknas)
mot egna golden-snapshots, så motorregressioner fångas även utanför Emirs
maskin. Se tests/services/test_warehouse_flow_characterization.py.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "services" / "fixtures" / "synthetic"
DATA_DIR = FIXTURES / "data"
SPEC_PATH = FIXTURES / "columns.json"

BASE_DATE = datetime(2026, 5, 1, 8, 0, 0)  # fast datum: inga "idag"-beroenden
ARTICLES = [f"SYNT-A{i:03d}" for i in range(1, 9)]
ORDERS = [f"99{i:04d}" for i in range(1, 7)]
CUSTOMERS = [f"KUND-{c}" for c in "ABCDEF"]


def _ts(offset_hours: int) -> str:
    return (BASE_DATE + timedelta(hours=offset_hours)).strftime("%Y-%m-%d %H:%M:%S")


def _date(offset_days: int) -> str:
    return (BASE_DATE + timedelta(days=offset_days)).strftime("%Y-%m-%d")


def _rows(columns: list[str], count: int, filler) -> pd.DataFrame:
    rows = [{col: filler(col, index) for col in columns} for index in range(count)]
    return pd.DataFrame(rows, columns=columns)


def build_frames(spec: dict[str, list[str]]) -> dict[str, pd.DataFrame]:
    rng = random.Random(42)

    def orders_filler(col: str, i: int):
        article = ARTICLES[i % len(ARTICLES)]
        order = ORDERS[i % len(ORDERS)]
        values = {
            "Status": [10, 20, 40, 60][i % 4],
            "Kund": CUSTOMERS[i % len(CUSTOMERS)],
            "Artikel": article,
            "Plockplats": f"P-{100 + i}",
            "Plock": rng.randint(1, 20),
            "Plockat": rng.randint(0, 10),
            "Beställt": rng.randint(1, 24),
            "Timestamp": _ts(i),
            "Zon": ["A", "B"][i % 2],
            "Rad": i + 1,
            "Order nr": order,
            "Orderstart": _ts(i - 24),
            "Lager": "SYNT",
            "Bolag": "SYNTBOLAG",
            "Orderdatum": _date(-(i % 3)),
            "Index num": i + 1,
        }
        return values.get(col, "")

    def saldo_filler(col: str, i: int):
        values = {
            "Artikel": ARTICLES[i % len(ARTICLES)],
            "Beskrivning": f"Syntetisk artikel {i + 1}",
            "Vikt netto": round(rng.uniform(0.5, 12.0), 2),
            "Plockplats": f"P-{100 + i}",
            "Plocksaldo": rng.randint(0, 60),
            "Kundorder": rng.randint(0, 30),
            "Buffertsaldo": rng.randint(0, 200),
            "Utbeställt": rng.randint(0, 40),
            "Saldo": rng.randint(0, 260),
            "Lager": "SYNT",
            "Bolag": "SYNTBOLAG",
        }
        return values.get(col, "")

    def overview_filler(col: str, i: int):
        values = {
            "Ordernr": ORDERS[i % len(ORDERS)],
            "Status": [10, 30, 50, 70][i % 4],
            "Struktur": "SYNT-STRUKTUR",
            "Transportör": f"TRP-{1 + i % 2}",
            "Starttid": _ts(i),
            "Orderdatum": _date(-(i % 3)),
            "Leveransdatum": _date(1 + i % 2),
            "Laststarttid": _ts(6 + i),
            "Avgångstid": _ts(9 + i),
            "Rader": rng.randint(1, 8),
            "Antal": rng.randint(1, 80),
            "Lager": "SYNT",
            "Kund nr": f"K{i + 1:03d}",
            "Kund": CUSTOMERS[i % len(CUSTOMERS)],
            "Sändningsnr": f"S{i + 1:05d}",
            "Bolag": "SYNTBOLAG",
            # "0" = saknar alt-adress (LQ ej klar-vägen); 1-3 matchar custom_adr.
            "Alt adress": str(i % 4),
        }
        return values.get(col, "")

    def dispatch_filler(col: str, i: int):
        values = {
            "Plockpallsnr.": f"PP{i + 1:05d}",
            "Ordernr": ORDERS[i % len(ORDERS)],
            "Kund": CUSTOMERS[i % len(CUSTOMERS)],
            "Transportör": f"TRP-{1 + i % 2}",
            "Leveransdatum": _date(1 + i % 2),
            "Status": [20, 40][i % 2],
            "Rader": rng.randint(1, 6),
            "Kolli": rng.randint(1, 30),
            "Vikt": round(rng.uniform(5, 400), 1),
            "Bolag": "SYNTBOLAG",
            "Sändningsnr": f"S{i + 1:05d}",
        }
        return values.get(col, "")

    def buffer_filler(col: str, i: int):
        values = {
            "Lagerplats": f"B-{200 + i}",
            "Pallid": f"PL{i + 1:06d}",
            "Artikel": ARTICLES[i % len(ARTICLES)],
            "Beskrivning": f"Syntetisk artikel {i % len(ARTICLES) + 1}",
            "Palltyp": ["EUR", "HALV"][i % 2],
            "Antal": rng.randint(10, 120),
            "Status": [1, 2][i % 2],
            "Vikt": round(rng.uniform(20, 600), 1),
            "Timestamp": _ts(i),
            "Antal per lav": rng.randint(4, 12),
            "Lager": "SYNT",
            "Bolag": "SYNTBOLAG",
        }
        return values.get(col, "")

    def items_filler(col: str, i: int):
        values = {
            "Artikel": ARTICLES[i % len(ARTICLES)],
            "Lager": "SYNT",
            "Bolag": "SYNTBOLAG",
            "Timestamp": _ts(i),
            "Klassificering": ["STD", "SKRYM"][i % 2],
            "Plockzon": ["A", "B"][i % 2],
            "Ej staplingsbar": ["0", "1"][i % 2],
        }
        return values.get(col, "")

    def not_putaway_filler(col: str, i: int):
        values = {
            "Status": [5, 10][i % 2],
            "Prioritet": i % 3,
            "Pall nr": f"NP{i + 1:05d}",
            "Artikel": ARTICLES[i % len(ARTICLES)],
            "Antal": rng.randint(5, 60),
            "Vikt": round(rng.uniform(10, 300), 1),
            "Bolag": "SYNTBOLAG",
            "Lager": "SYNT",
            "Antal per lav": rng.randint(4, 12),
        }
        return values.get(col, "")

    def custom_adr_filler(col: str, i: int):
        # Postnummer varvar Gotland (621-624xx -> "LQ Gotland") och fastlandet
        # sa goods-declaration motionerar bada sjovagarna.
        postcodes = ["621 45", "12345", "623 10", "54321"]
        values = {
            "Kund": f"K{i + 1:03d}",
            "Namn": f"Syntetisk mottagare {i + 1}",
            "Adress": f"Syntetgatan {i + 1}",
            "Post nr": postcodes[i % len(postcodes)],
            "Ort": ["Visby", "Fastlandet"][i % 2],
            "Adr num": str(1 + i % 3),
            "Land": "SE",
            "Bolag": "SYNTBOLAG",
        }
        return values.get(col, "")

    def item_security_filler(col: str, i: int):
        # Nivamonster "", LQ, DG, "" sa prioriteringen DG > LQ > tom provas.
        values = {
            "Artikel": ARTICLES[i % len(ARTICLES)],
            "Beskrivning": f"Syntetisk artikel {i % len(ARTICLES) + 1}",
            "Farligt gods nivå": ["", "LQ", "DG", ""][i % 4],
            "Lager": "SYNT",
            "Bolag": "SYNTBOLAG",
            "Timestamp": _ts(i),
        }
        return values.get(col, "")

    fillers = {
        "orders": (orders_filler, 24),
        "saldo": (saldo_filler, 8),
        "overview": (overview_filler, 12),
        "dispatch": (dispatch_filler, 10),
        "buffer": (buffer_filler, 16),
        "items": (items_filler, 8),
        "not_putaway": (not_putaway_filler, 6),
        "custom_adr": (custom_adr_filler, 8),
        "item_security_info": (item_security_filler, 8),
    }
    return {
        key: _rows(spec[key], count, filler)
        for key, (filler, count) in fillers.items()
    }


def main() -> int:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for key, frame in build_frames(spec).items():
        path = DATA_DIR / f"{key}.csv"
        frame.to_csv(path, sep="\t", index=False, encoding="utf-8-sig", lineterminator="\n")
        print(f"{path.relative_to(ROOT)}: {len(frame)} rader, {len(frame.columns)} kolumner")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

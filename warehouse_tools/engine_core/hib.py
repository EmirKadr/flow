"""HIB-koppling och missade avgångar."""
from __future__ import annotations

import base64
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .io_utils import (
    smart_to_datetime,
)

def _hib_orders_with_today_origin(kund_df: pd.DataFrame) -> set[str]:
    """Returnera HIB-ordrar vars Ursprungsdatum är samma som dagens kördatum."""
    if (
        not isinstance(kund_df, pd.DataFrame)
        or kund_df.empty
        or "Ordernr" not in kund_df.columns
        or "Ordertyp" not in kund_df.columns
        or "Ursprungsdatum" not in kund_df.columns
    ):
        return set()

    try:
        parsed = smart_to_datetime(kund_df["Ursprungsdatum"])
        today = pd.Timestamp.now().date()
        mask = (
            kund_df["Ordertyp"].astype(str).str.strip().str.upper().eq("HIB")
            & parsed.notna()
            & parsed.dt.date.eq(today)
        )
    except Exception:
        today_str = pd.Timestamp.now().strftime("%Y-%m-%d")
        mask = (
            kund_df["Ordertyp"].astype(str).str.strip().str.upper().eq("HIB")
            & kund_df["Ursprungsdatum"].astype(str).str.strip().eq(today_str)
        )

    if not mask.any():
        return set()

    return set(kund_df.loc[mask, "Ordernr"].astype(str).str.strip())

# Kolumnnamn för den hoistade "Ursprungsdatum == idag"-flaggan. Läggs bara på den
# projicerade loop-ramen, aldrig på indata.
_TODAY_ORIGIN_COL = "_hib_today_origin"

# Datumformat som är entydiga och format-homogena (se _OriginToday).
_ISO_DATE_RE = r"^\d{4}-\d{2}-\d{2}$"
_NUM8_DATE_RE = r"^\d{8}$"

# Exakt de kolumner kundloopen i respektive funktion läser. Ursprungsdatum är
# valfri i båda (den ingår inte i required_overview_cols för missade avgångar).
_HIB_LOOP_COLS = [
    "Kund nr", "Ordernr", "Ordertyp", "Orderdatum", "Sändningsnr", "Zon", "Multi",
    "Ursprungsdatum",
]
_MISSED_LOOP_COLS = ["Kund nr", "Ordernr", "Ordertyp", "Sändningsnr", "Ursprungsdatum"]

class _OriginToday:
    """Hoistad motsvarighet till :func:`_hib_orders_with_today_origin`.

    Originalet kör ``smart_to_datetime`` en gång PER KUNDGRUPP, vilket är den
    enskilt dyraste posten i flödet (~0,9 s över 350 anrop). Att i stället parsa
    hela ``ov`` en gång är dock **inte** beteendebevarande i allmänhet:
    ``smart_to_datetime`` (io_utils.py:142-161) gör sample-baserad
    formatinferens, och pandas 3 härleder ETT format per anrop ur seriens första
    icke-null-värde och coercar allt annat till NaT. Byter man indata från
    kundgruppen till hela filen kan både inferensen och resultatet bli ett annat.

    Konkret motbevis (kört): kolumnen ``["05/06/2026", "2026-05-17" * 10]`` ger
    globalt ``2026-05-06`` för rad 0 (iso_like -> dayfirst=False -> %m/%d/%Y) men
    ``2026-06-05`` per grupp (dayfirst=True -> %d/%m/%Y). Båda är icke-NaT, så en
    "föll parsningen till NaT?"-vakt fångar det inte.

    Vakten här är därför strikt starkare: den globala parsningen används bara när
    HELA kolumnen bevisligen är format-homogen, dvs. varje icke-null råvärde
    matchar antingen ``%Y-%m-%d`` eller ``%Y%m%d`` och inget av dem parsades till
    NaT. Då blir smart_to_datetimes grenval (numeric_like/iso_like/dayfirst) och
    pandas formatgissning identiska för hela filen och för varje delmängd av den,
    och den globala parsningen är per konstruktion lika med per-grupp-parsningen.
    Håller villkoret inte, används den oförändrade per-grupp-funktionen.

    Verklig data (v_ask_order_overview): 1570/1570 rader full-ISO -> snabb väg.
    """

    def __init__(self, ov: pd.DataFrame) -> None:
        self._always_empty = (
            not isinstance(ov, pd.DataFrame)
            or "Ordernr" not in ov.columns
            or "Ordertyp" not in ov.columns
            or "Ursprungsdatum" not in ov.columns
        )
        self._today_hib: Optional[np.ndarray] = None
        if self._always_empty:
            return
        try:
            raw = ov["Ursprungsdatum"]
            text = raw.dropna().astype(str).str.strip()
            homogeneous = bool(
                len(text) == 0
                or text.str.match(_ISO_DATE_RE).all()
                or text.str.match(_NUM8_DATE_RE).all()
            )
            if not homogeneous:
                return
            parsed = smart_to_datetime(raw)
            # Ett icke-null råvärde som blev NaT betyder att en grupp som bara
            # innehåller sådana värden hamnar i smart_to_datetimes retry-gren och
            # kan få ett annat resultat än den globala parsningen.
            if bool((parsed.isna() & raw.notna()).any()):
                return
            is_hib = ov["Ordertyp"].astype(str).str.strip().str.upper().eq("HIB")
            is_today = parsed.notna() & parsed.dt.date.eq(pd.Timestamp.now().date())
            self._today_hib = (is_hib & is_today).to_numpy()
        except Exception:
            self._today_hib = None

    def attach(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Lägg flaggkolumnen på den (redan kopierade) loop-ramen."""
        if self._today_hib is not None:
            frame[_TODAY_ORIGIN_COL] = self._today_hib
        return frame

    def for_group(self, kund_df: pd.DataFrame) -> set[str]:
        if self._always_empty:
            return set()
        if self._today_hib is None:
            # Ingen bevisat säker hoist -> exakt den gamla vägen, per grupp.
            return _hib_orders_with_today_origin(kund_df)
        mask = kund_df[_TODAY_ORIGIN_COL].to_numpy()
        if not mask.any():
            return set()
        return set(kund_df.loc[mask, "Ordernr"].astype(str).str.strip())

def _project(ov: pd.DataFrame, needed: list[str]) -> pd.DataFrame:
    """Projicera ov till de kolumner kundloopen faktiskt läser.

    groupby och varje bool-mask nedan materialiserar annars hela den
    45-kolumners arrow-strängbackade ramen - kolumnbredden, inte radantalet, är
    den dominerande kostnaden i profilen.
    """
    if ov.columns.duplicated().any():
        # Dubblettkolumner: rör inte ramen, då blir ov[col] en DataFrame och
        # beteendet ska förbli exakt som förut.
        return ov.copy()
    return ov.loc[:, [c for c in needed if c in ov.columns]].copy()

_MISSING = object()

def _parse_date_cached(value: str, cache: dict) -> object:
    """Memoiserad skalär datumparsning. Cachear inte vid undantag."""
    hit = cache.get(value, _MISSING)
    if hit is not _MISSING:
        return hit
    parsed = pd.to_datetime(value, errors="coerce")
    cache[value] = parsed
    return parsed

def _earliest_pos(positions: list[int], date_str: list[str], cache: dict) -> int:
    """Positionen för den butiksorder som har äldst orderdatum.

    Bevarar den gamla ``_choose_earliest``-semantiken EXAKT (inget idxmin):
      (a) första raden är default,
      (b) ett icke-NaT slår alltid ett NaT,
      (c) är BÅDA NaT jämförs rådatumsträngarna lexikografiskt,
      (d) strikt ``<`` -> vid lika datum vinner den FÖRSTA raden.
    """
    best = positions[0]
    best_s = date_str[best]
    for pos in positions:
        cur_s = date_str[pos]
        try:
            d_new = _parse_date_cached(cur_s, cache)
            d_old = _parse_date_cached(best_s, cache)
            if (pd.isna(d_old) and not pd.isna(d_new)) or (
                not pd.isna(d_old) and not pd.isna(d_new) and d_new < d_old
            ):
                best, best_s = pos, cur_s
            elif pd.isna(d_new) and pd.isna(d_old) and cur_s < best_s:
                best, best_s = pos, cur_s
        except Exception:
            # Fallback: jämför strängar om datumkonvertering misslyckas
            if cur_s < best_s:
                best, best_s = pos, cur_s
    return best

def compute_hib_koppling(
    details_df: pd.DataFrame, overview_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Analysera orderdetaljer (beställningslinjer) och orderöversikt för att
    identifiera vilka HIB‑ordrar som behöver ändras.  Resultatet innehåller
    följande kolumner:

      - ordernummer: Ordernumret för HIB‑ordern.
      - Ursprungsdatum: Ursprungsdatum från orderöversikten om det finns.
      - Orderdatum: Nytt orderdatum om det skiljer sig från butikens orderdatum.
      - sändningsnummer: Nytt sändningsnummer om det skiljer sig från butikens order.
      - Zon: "F" om någon rad inte ligger i zon F/H/R och därför måste sättas till F.
      - Multi: "MULTI" om det behövs ett nytt multi‑nummer för kundens HIB‑ordrar.

    Endast ordrar där minst en kolumn behöver uppdateras inkluderas i resultatet.
    """
    # Kopiera och städa kolumnnamn (ta bort BOM och trimma blanksteg)
    details = details_df.copy()
    overview = overview_df.copy()
    details.columns = [str(c).replace("\ufeff", "").strip() for c in details.columns]
    overview.columns = [str(c).replace("\ufeff", "").strip() for c in overview.columns]
    # Map synonyms in overview columns to canonical names so that column order and variations do not matter.
    synonyms = {
        "Ordernr": ["Ordernr", "Order nr", "Order number", "Ordernummer"],
        "Ordertyp": ["Ordertyp", "Order typ", "Order type", "Ordertype"],
        "Kund nr": ["Kund nr", "Kundnr", "Kundnummer", "Customer number", "Kund NR"],
        "Bolag": ["Bolag", "Company", "Bolag nr", "Bol"],
        "Orderdatum": ["Orderdatum", "Order datum", "Order date", "Orderdate"],
        "Sändningsnr": [
            "Sändningsnr",
            "Sändnings nr",
            "Sändningsnummer",
            "Sendingsnr",
            "Sändnings number",
        ],
        "Zon": ["Zon", "Zone"],
        "Multi": ["Multi", "Multi nr", "Multinr", "Multi number"],
        "Ursprungsdatum": ["Ursprungsdatum", "Ursprungs datum", "Original date", "Ursprungsdate"],
    }
    for canonical, syns in synonyms.items():
        if canonical in overview.columns:
            continue
        for candidate in syns:
            # search for a matching column, case-insensitive after stripping spaces
            for col in list(overview.columns):
                if col.strip().lower() == candidate.strip().lower():
                    overview.rename(columns={col: canonical}, inplace=True)
                    break
            if canonical in overview.columns:
                break

    # Säkerställ att nödvändiga kolumner finns, annars returnera tomt df
    required_overview_cols = {"Ordernr", "Ordertyp", "Kund nr", "Orderdatum", "Sändningsnr", "Zon", "Multi"}
    missing = [c for c in required_overview_cols if c not in overview.columns]
    if missing:
        return pd.DataFrame(columns=["ordernummer", "Ursprungsdatum", "Orderdatum", "sändningsnummer", "Zon", "Multi"])

    # Normalisera ordertyp men låt indata-filtret styra vilka rader som ingår.
    ov = overview.copy()
    ov["Ordertyp"] = ov["Ordertyp"].astype(str).str.strip().str.upper()
    if ov.empty:
        return pd.DataFrame(columns=["ordernummer", "Ursprungsdatum", "Orderdatum", "sändningsnummer", "Zon", "Multi"])

    # Samla status per order från beställningslinjerna
    details.columns = [c.replace("\ufeff", "").strip() for c in details.columns]
    # Säkerställ att vi har nödvändiga kolumner även där
    if "Order nr" not in details.columns or "Status" not in details.columns:
        return pd.DataFrame(columns=["ordernummer", "Ursprungsdatum", "Orderdatum", "sändningsnummer", "Zon", "Multi"])

    # Konvertera status till tal när möjligt (allt som inte går tolkas som stort tal för att markera ej OK)
    def to_status_numeric(x):
        try:
            return int(float(str(x).strip()))
        except Exception:
            return 9999

    details["_status_num"] = details["Status"].apply(to_status_numeric)

    # Map för order -> max status
    order_status_max = details.groupby("Order nr")["_status_num"].max().to_dict()

    # Map för order -> zoner i beställningslinjer.
    # Samma semantik som groupby("Order nr")["Zon"].apply(lambda x: list(x.dropna().astype(str))):
    # NaN-zoner faller bort, NaN-ordernr blir ingen grupp, radordningen bevaras -
    # men utan att bygga en Series per order (~2000 grupper).
    order_zones: dict = {}
    _zon_notna = details["Zon"].notna()
    for _ord, _zon in zip(
        details.loc[_zon_notna, "Order nr"].tolist(),
        details.loc[_zon_notna, "Zon"].astype(str).tolist(),
    ):
        if _ord is None or _ord != _ord:  # NaN-nyckel: groupby släpper den
            continue
        order_zones.setdefault(_ord, []).append(_zon)

    # Skapa mappning från ordernummer till kundnamn (butiksnamn) om möjligt
    order_to_kundnamn: dict[str, str] = {}
    if "Order nr" in details.columns and "Kund.1" in details.columns:
        try:
            order_to_kundnamn = (details.groupby("Order nr")["Kund.1"].first()
                                 .fillna("")
                                 .astype(str)
                                 .str.strip()
                                 .to_dict())
        except Exception:
            order_to_kundnamn = {}

    # Resultatlista
    rows: list[dict] = []

    # "Ursprungsdatum == idag" parsas en gång för hela ov när det bevisligen är
    # beteendebevarande (se _OriginToday), annars per kundgrupp som förut.
    origin = _OriginToday(ov)
    has_ursprung = "Ursprungsdatum" in ov.columns
    # En parse-cache per anrop (aldrig modulglobal - den skulle läcka mellan
    # requests och filversioner).
    parse_cache: dict = {}
    ov_slim = origin.attach(_project(ov, _HIB_LOOP_COLS))

    # Gruppera orderöversikten efter kundnummer
    for kund_nr, kund_df in ov_slim.groupby("Kund nr"):
        # Hämta butikens order (Ordertyp N) och hämta deras ordernummer
        # Hitta butiksordrar (Ordertyp N) och HIB‑ordrar, men deduplicera per ordernummer
        ordertyp = kund_df["Ordertyp"]
        store_df = kund_df[ordertyp == "N"]
        hib_df = kund_df[ordertyp == "HIB"]
        if store_df.empty or hib_df.empty:
            # inga HIB att koppla eller ingen butik => hoppa över.
            # Checken ligger före origin.for_group: funktionen är ren och dess
            # resultat kastades ändå för dessa grupper (126 av 175 på verklig data).
            continue
        ignored_hib_orders = origin.for_group(kund_df)
        if ignored_hib_orders:
            hib_df = hib_df[~hib_df["Ordernr"].astype(str).str.strip().isin(ignored_hib_orders)]
            if hib_df.empty:
                continue
        # Deduplicera för att undvika att samma order behandlas flera gånger (en rad per zon i orderöversikten)
        store_df = store_df.drop_duplicates(subset=["Ordernr"]).reset_index(drop=True)
        hib_df = hib_df.drop_duplicates(subset=["Ordernr"]).reset_index(drop=True)

        # Materialisera butikskolumnerna EN gång per kund. iterrows/bool-masker
        # per HIB-order materialiserar annars hela raden ur en bred arrow-ram.
        n_store = len(store_df)
        store_ordernr = store_df["Ordernr"].tolist()
        # Mask-semantik: astype(str) BEHÅLLER NaN (pandas 3 str-dtype) - exakt vad
        # den gamla bool-masken jämförde med.
        store_ship_mask = store_df["Sändningsnr"].astype(str).str.strip().tolist()
        # Loop-semantik: str(nan) -> "nan" - exakt vad den gamla iterrows-koden såg.
        # De två listorna är AVSIKTLIGT olika; de får inte slås ihop.
        store_date_str = [str(v).strip() for v in store_df["Orderdatum"].tolist()]
        store_kname = [order_to_kundnamn.get(o, "").strip().lower() for o in store_ordernr]

        # Filtrera butiksordrar där alla statusar är < 34
        # Detta bildar listan av "giltiga" butiksordrar som kan användas som referens.
        #
        # OBS! Vissa butiksorder kan sakna status i orderdetaljerna. Tidigare
        # användes ett defaultvärde på 9999 vilket uteslöt dessa order från matchning.
        # Det ledde till att en HIB-order med korrekt sändningsnummer och datum ändå
        # kopplades om till en annan butik. För att behandla sådana butiksorder som
        # giltiga sätts nu defaultstatus till 0 istället för 9999. Då inkluderas
        # butiksorder som saknar statusuppgift.
        valid_pos = [i for i, o in enumerate(store_ordernr) if order_status_max.get(o, 0) < 34]
        if not valid_pos:
            # ingen giltig butiksorder att koppla mot
            continue

        # Fallback‑butiksorder: den med äldst orderdatum bland giltiga
        fallback_store_row = store_df.iloc[_earliest_pos(valid_pos, store_date_str, parse_cache)]
        # Undersök HIB‑ordrar som är tillåtna (alla status < 34)
        hib_orders: list[tuple] = []
        for h_ord, h_ship, h_date in zip(
            hib_df["Ordernr"].tolist(),
            hib_df["Sändningsnr"].tolist(),
            hib_df["Orderdatum"].tolist(),
        ):
            # Kontrollera status
            maxstatus = order_status_max.get(h_ord, 9999)
            if maxstatus >= 34:
                continue  # denna hib får inte ändras
            hib_orders.append((h_ord, str(h_ship).strip(), str(h_date).strip()))
        if not hib_orders:
            continue
        # Bestäm zon‑flagga per hibordernummer
        zone_flag = False  # om någon rad ej är F/H/R => True
        hib_zone_updates = {}  # ordernummer -> zon_update ("F" eller "")
        for h_ord, _cur_ship, _cur_date in hib_orders:
            zones = [z.strip().upper() for z in order_zones.get(h_ord, []) if str(z).strip()]
            # Om det finns minst en zon som inte är F, H eller R
            if any(z not in ("F", "H", "R") for z in zones):
                zone_flag = True
                hib_zone_updates[h_ord] = "F"
            else:
                hib_zone_updates[h_ord] = ""
        # Bestäm multi‑nummer per order i zon F
        # Zon-F-raderna grupperas EN gång per kund i stället för en bool-mask över
        # kund_df per HIB-order.
        zone_f = kund_df[kund_df["Zon"].astype(str).str.strip().str.upper() == "F"]
        multi_by_order: dict = {}
        for _ord, _multi in zip(
            zone_f["Ordernr"].tolist(),
            [str(v).strip() for v in zone_f["Multi"].tolist()],
        ):
            multi_by_order.setdefault(_ord, []).append(_multi)
        # Samla multi‑nummer för varje HIB‑order i zon F (i orderöversikten)
        hib_f_multi: dict[str, list[str]] = {}
        missing_multi_per_order: dict[str, bool] = {}
        for h_ord, _cur_ship, _cur_date in hib_orders:
            zone_multis = multi_by_order.get(h_ord)
            if zone_multis is None:
                # ingen rad i zon F => saknar multi för denna order
                missing_multi_per_order[h_ord] = True
                hib_f_multi[h_ord] = []
            else:
                # Endast icke-tomma värden räknas; saknas alla är multi:t "missing".
                mlist = [m for m in zone_multis if m]
                missing_multi_per_order[h_ord] = not mlist
                hib_f_multi[h_ord] = mlist
        # Global unik mängd av alla multi-värden (icke-tomma) i zon F för denna kund
        multi_vals_global: set[str] = set()
        for mlist in hib_f_multi.values():
            for m in mlist:
                if m:
                    multi_vals_global.add(m)
        # Det finns en gemensam multi om mängden har exakt ett värde
        common_multi_exists = len(multi_vals_global) == 1
        # Om det finns en gemensam multi, extrahera den
        common_multi_value = next(iter(multi_vals_global)) if common_multi_exists else None
        # Ursprungsdatum per order: första icke-null i radordning (som .iloc[0] förut)
        ursprung_by_order: dict = {}
        if has_ursprung:
            udf = kund_df[["Ordernr", "Ursprungsdatum"]].dropna(subset=["Ursprungsdatum"])
            for _ord, _udat in zip(
                udf["Ordernr"].tolist(),
                udf["Ursprungsdatum"].astype(str).str.strip().tolist(),
            ):
                ursprung_by_order.setdefault(_ord, _udat)
        # Generera rader
        for h_ord, cur_ship, cur_date in hib_orders:
            # Beräkna uppdateringar
            ship_update = ""
            date_update = ""
            z_update = hib_zone_updates.get(h_ord, "")

            # Kundnamn för HIB‑ordern, används för att prioritera matchning mot samma butik
            hib_kundnamn = order_to_kundnamn.get(h_ord, "").strip().lower()

            # Kandidater med samma sändningsnummer och samma kundnamn
            # Använd alla butiksordrar (store_df) för att hitta matchning på sändningsnummer
            # oavsett status. Detta säkerställer att en HIB‑order som redan är kopplad till
            # en butik med ett avslutat orderstatus (>34) inte kopplas om till en annan butik
            # bara för att dess butik inte finns bland de giltiga butiksordrarna.
            pos_both = [
                j for j in range(n_store)
                if store_ship_mask[j] == cur_ship and store_kname[j] == hib_kundnamn
            ]
            if pos_both:
                # Välj den tidigaste av de butiksorder som matchar både sändningsnummer och kundnamn
                candidate_row = store_df.iloc[_earliest_pos(pos_both, store_date_str, parse_cache)]
            else:
                # Annars matcha endast på sändningsnummer (oavsett kundnamn) i alla butiksordrar
                pos_ship = [j for j in range(n_store) if store_ship_mask[j] == cur_ship]
                if pos_ship:
                    candidate_row = store_df.iloc[_earliest_pos(pos_ship, store_date_str, parse_cache)]
                else:
                    # Om ingen matchande sändningsnummer hittas används fallback‑butiken
                    candidate_row = fallback_store_row

            # Hämta referensdata från vald butiksorder
            ref_ship = str(candidate_row["Sändningsnr"]).strip()
            ref_date = str(candidate_row["Orderdatum"]).strip()

            # Om HIB‑orderns värde inte matchar referensen anges uppdatering
            if cur_ship != ref_ship:
                ship_update = ref_ship
            if cur_date != ref_date:
                date_update = ref_date
            # Bestäm multi‑uppdatering per order
            multi_update = ""
            if len(hib_orders) > 1:
                # saknar F‑zon eller multi för denna order
                if missing_multi_per_order.get(h_ord, False):
                    multi_update = "MULTI"
                else:
                    if common_multi_exists:
                        # det finns exakt en gemensam multi; kontrollera om denna order har samma värde
                        if set(hib_f_multi.get(h_ord, [])) != {common_multi_value}:
                            multi_update = "MULTI"
                    else:
                        # flera olika multi-värden existerar globalt; föreslå att enas på en multi
                        multi_update = "MULTI"
            ursprungsdatum = ursprung_by_order.get(h_ord, "") if has_ursprung else ""
            # Inkludera endast om någon kolumn behöver ändras
            if ship_update or date_update or z_update or multi_update:
                rows.append({
                    "ordernummer": h_ord,
                    "kundnamn": order_to_kundnamn.get(h_ord, ""),
                    "Ursprungsdatum": ursprungsdatum,
                    "Orderdatum": date_update,
                    "sändningsnummer": ship_update,
                    "Zon": z_update,
                    "Multi": multi_update
                })
    # Skapa DataFrame
    if not rows:
        return pd.DataFrame(columns=["ordernummer", "Ursprungsdatum", "Orderdatum", "sändningsnummer", "Zon", "Multi"])
    result_df = pd.DataFrame(rows)
    if result_df.empty:
        return result_df
    # Sortera efter kundnamn (A→Z) och sedan ordernummer för stabilitet
    # Detta gör att Excel-filen hamnar i alfabetisk ordning på kundnamn
    result_df = result_df.sort_values(by=["kundnamn", "ordernummer"]).reset_index(drop=True)
    # Placera kolumner i ordning: ordernr, kundnamn, ursprungsdatum, orderdatum, sändningsnummer, Zon, Multi
    cols = ["ordernummer", "kundnamn", "Ursprungsdatum", "Orderdatum", "sändningsnummer", "Zon", "Multi"]
    result_df = result_df[cols]
    return result_df

def compute_missed_departures(details_df: pd.DataFrame, overview_df: pd.DataFrame) -> pd.DataFrame:
    """
    Identifiera HIB‑ordrar som har orderrader med status > 34 och vars sändningsnummer inte matchar
    någon butiksorder för samma kund.  Returnerar ett DataFrame med kolumnerna:
      - ordernummer: HIB‑ordernummer.
      - kundnamn: Kundnamn om tillgängligt.
      - Missat: alltid "MISSAT SIN AVGÅNG" för dessa ordrar.
    """
    try:
        # Kopiera och städa kolumnnamn
        details = details_df.copy()
        overview = overview_df.copy()
        details.columns = [str(c).replace("\ufeff", "").strip() for c in details.columns]
        overview.columns = [str(c).replace("\ufeff", "").strip() for c in overview.columns]
        # Synonym‑mappning som i compute_hib_koppling
        synonyms = {
            "Ordernr": ["Ordernr", "Order nr", "Order number", "Ordernummer"],
            "Ordertyp": ["Ordertyp", "Order typ", "Order type", "Ordertype"],
            "Kund nr": ["Kund nr", "Kundnr", "Kundnummer", "Customer number", "Kund NR"],
            "Bolag": ["Bolag", "Company", "Bolag nr", "Bol"],
            "Orderdatum": ["Orderdatum", "Order datum", "Order date", "Orderdate"],
            "Sändningsnr": [
                "Sändningsnr",
                "Sändnings nr",
                "Sändningsnummer",
                "Sendingsnr",
                "Sändnings number",
            ],
            "Zon": ["Zon", "Zone"],
            "Multi": ["Multi", "Multi nr", "Multinr", "Multi number"],
        }
        for canonical, syns in synonyms.items():
            if canonical not in overview.columns:
                for candidate in syns:
                    for col in list(overview.columns):
                        if col.strip().lower() == candidate.strip().lower():
                            overview.rename(columns={col: canonical}, inplace=True)
                            break
                    if canonical in overview.columns:
                        break
        # Kontrollera att nödvändiga kolumner finns
        required_overview_cols = {"Ordernr", "Ordertyp", "Kund nr", "Sändningsnr"}
        if any(c not in overview.columns for c in required_overview_cols):
            return pd.DataFrame(columns=["ordernummer", "kundnamn", "Missat"])
        # Normalisera ordertyp men låt indata-filtret styra vilka rader som ingår.
        ov = overview.copy()
        ov["Ordertyp"] = ov["Ordertyp"].astype(str).str.strip().str.upper()
        if ov.empty:
            return pd.DataFrame(columns=["ordernummer", "kundnamn", "Missat"])
        # Säkerställ att details har ordernr och status
        if "Order nr" not in details.columns or "Status" not in details.columns:
            return pd.DataFrame(columns=["ordernummer", "kundnamn", "Missat"])
        # Konvertera status till numeriskt
        def to_status_numeric(x):
            try:
                return int(float(str(x).strip()))
            except Exception:
                return 9999
        details["_status_num"] = details["Status"].apply(to_status_numeric)
        order_status_max = details.groupby("Order nr")["_status_num"].max().to_dict()
        # Mappning ordernummer -> kundnamn
        order_to_kundnamn: dict[str, str] = {}
        if "Order nr" in details.columns and "Kund.1" in details.columns:
            try:
                order_to_kundnamn = (
                    details.groupby("Order nr")["Kund.1"].first()
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .to_dict()
                )
            except Exception:
                order_to_kundnamn = {}
        rows: list[dict] = []
        # Samma tre grepp som i compute_hib_koppling: hoistad datumparsning,
        # kolumnprojektion före groupby och inga iterrows.
        origin = _OriginToday(ov)
        ov_slim = origin.attach(_project(ov, _MISSED_LOOP_COLS))
        # Gruppera efter kundnummer
        for kund_nr, kund_df in ov_slim.groupby("Kund nr"):
            ordertyp = kund_df["Ordertyp"]
            store_df = kund_df[ordertyp == "N"]
            hib_df = kund_df[ordertyp == "HIB"]
            if store_df.empty or hib_df.empty:
                continue
            ignored_hib_orders = origin.for_group(kund_df)
            if ignored_hib_orders:
                hib_df = hib_df[~hib_df["Ordernr"].astype(str).str.strip().isin(ignored_hib_orders)]
                if hib_df.empty:
                    continue
            store_df = store_df.drop_duplicates(subset=["Ordernr"]).reset_index(drop=True)
            hib_df = hib_df.drop_duplicates(subset=["Ordernr"]).reset_index(drop=True)
            # Sändningsnummer för butikens ordrar (loop-semantik: str(nan) -> "nan",
            # vilket är sanningsvärt och därför ingick även förut).
            store_ships: set[str] = {
                s for s in (str(v).strip() for v in store_df["Sändningsnr"].tolist()) if s
            }
            for h_ord, h_ship in zip(
                hib_df["Ordernr"].tolist(), hib_df["Sändningsnr"].tolist()
            ):
                maxstatus = order_status_max.get(h_ord, 9999)
                # Intressanta HIB‑ordrar har status > 34
                if maxstatus <= 34:
                    continue
                cur_ship = str(h_ship).strip()
                # Om sändningsnumret finns i butikernas sändningar är det inte en missad avgång
                if cur_ship and cur_ship in store_ships:
                    continue
                rows.append({
                    "ordernummer": h_ord,
                    "kundnamn": order_to_kundnamn.get(h_ord, ""),
                    "Missat": "MISSAT SIN AVGÅNG",
                })
        if not rows:
            return pd.DataFrame(columns=["ordernummer", "kundnamn", "Missat"])
        result = pd.DataFrame(rows)
        result = result.sort_values(by=["kundnamn", "ordernummer"]).reset_index(drop=True)
        return result
    except Exception:
        return pd.DataFrame(columns=["ordernummer", "kundnamn", "Missat"])

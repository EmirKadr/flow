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

    # Map för order -> zoner i beställningslinjer
    order_zones = details.groupby("Order nr")["Zon"].apply(lambda x: list(x.dropna().astype(str))).to_dict()

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

    # Gruppera orderöversikten efter kundnummer
    for kund_nr, kund_df in ov.groupby("Kund nr"):
        # Hämta butikens order (Ordertyp N) och hämta deras ordernummer
        # Hitta butiksordrar (Ordertyp N) och HIB‑ordrar, men deduplicera per ordernummer
        store_df = kund_df[kund_df["Ordertyp"] == "N"].copy()
        hib_df = kund_df[kund_df["Ordertyp"] == "HIB"].copy()
        ignored_hib_orders = _hib_orders_with_today_origin(kund_df)
        if ignored_hib_orders:
            hib_df = hib_df[~hib_df["Ordernr"].astype(str).str.strip().isin(ignored_hib_orders)].copy()
        # Deduplicera för att undvika att samma order behandlas flera gånger (en rad per zon i orderöversikten)
        if not store_df.empty:
            store_df = store_df.drop_duplicates(subset=["Ordernr"]).reset_index(drop=True)
        if not hib_df.empty:
            hib_df = hib_df.drop_duplicates(subset=["Ordernr"]).reset_index(drop=True)
        if store_df.empty or hib_df.empty:
            # inga HIB att koppla eller ingen butik => hoppa över
            continue
        # Filtrera butiksordrar där alla statusar är < 34
        # Detta bildar listan av "giltiga" butiksordrar som kan användas som referens.
        #
        # OBS! Vissa butiksorder kan sakna status i orderdetaljerna. Tidigare
        # användes ett defaultvärde på 9999 vilket uteslöt dessa order från matchning.
        # Det ledde till att en HIB-order med korrekt sändningsnummer och datum ändå
        # kopplades om till en annan butik. För att behandla sådana butiksorder som
        # giltiga sätts nu defaultstatus till 0 istället för 9999. Då inkluderas
        # butiksorder som saknar statusuppgift.
        valid_store_df = store_df[store_df["Ordernr"].map(lambda ordnum: order_status_max.get(ordnum, 0) < 34)].copy()
        if valid_store_df.empty:
            # ingen giltig butiksorder att koppla mot
            continue

        # Hjälpfunktion: välj den butiksorder som har äldst orderdatum i ett givet DataFrame
        def _choose_earliest(df: pd.DataFrame) -> pd.Series:
            # Börja med första rad som referens
            earliest_row = df.iloc[0]
            earliest_date = str(earliest_row["Orderdatum"]).strip()
            for _, r in df.iterrows():
                date_str = str(r["Orderdatum"]).strip()
                try:
                    d_new = pd.to_datetime(date_str, errors="coerce")
                    d_old = pd.to_datetime(earliest_date, errors="coerce")
                    if (pd.isna(d_old) and not pd.isna(d_new)) or (
                        not pd.isna(d_old) and not pd.isna(d_new) and d_new < d_old
                    ):
                        earliest_row = r
                        earliest_date = date_str
                    elif pd.isna(d_new) and pd.isna(d_old) and date_str < earliest_date:
                        earliest_row = r
                        earliest_date = date_str
                except Exception:
                    # Fallback: jämför strängar om datumkonvertering misslyckas
                    if date_str < earliest_date:
                        earliest_row = r
                        earliest_date = date_str
            return earliest_row

        # Fallback‑butiksorder: den med äldst orderdatum bland giltiga
        fallback_store_row = _choose_earliest(valid_store_df)
        # Undersök HIB‑ordrar som är tillåtna (alla status < 34)
        hib_orders: list[dict] = []
        for _, hib_row in hib_df.iterrows():
            h_ord = hib_row["Ordernr"]
            # Kontrollera status
            maxstatus = order_status_max.get(h_ord, 9999)
            if maxstatus >= 34:
                continue  # denna hib får inte ändras
            hib_orders.append({"row": hib_row, "ordernr": h_ord})
        if not hib_orders:
            continue
        # Bestäm zon‑flagga per hibordernummer
        zone_flag = False  # om någon rad ej är F/H/R => True
        hib_zone_updates = {}  # ordernummer -> zon_update ("F" eller "")
        for hib in hib_orders:
            h_ord = hib["ordernr"]
            zones = [z.strip().upper() for z in order_zones.get(h_ord, []) if str(z).strip()]
            # Om det finns minst en zon som inte är F, H eller R
            if any(z not in ("F", "H", "R") for z in zones):
                zone_flag = True
                hib_zone_updates[h_ord] = "F"
            else:
                hib_zone_updates[h_ord] = ""
        # Bestäm multi‑nummer per order i zon F
        # Samla multi‑nummer för varje HIB‑order i zon F (i orderöversikten)
        hib_f_multi: dict[str, list[str]] = {}
        missing_multi_per_order: dict[str, bool] = {}
        for hib in hib_orders:
            h_ord = hib["ordernr"]
            # Alla rader i kund_df för denna order där zon är F
            hib_zone_rows = kund_df[(kund_df["Ordernr"] == h_ord) & (kund_df["Zon"].astype(str).str.strip().str.upper() == "F")]
            mlist: list[str] = []
            if hib_zone_rows.empty:
                # ingen rad i zon F => saknar multi för denna order
                missing_multi_per_order[h_ord] = True
            else:
                missing_flag = True
                for _, zrow in hib_zone_rows.iterrows():
                    mval = str(zrow.get("Multi", "")).strip()
                    if mval:
                        mlist.append(mval)
                        missing_flag = False
                missing_multi_per_order[h_ord] = missing_flag
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
        # Generera rader
        for hib in hib_orders:
            h_row = hib["row"]
            h_ord = hib["ordernr"]
            # Beräkna uppdateringar
            ship_update = ""
            date_update = ""
            z_update = hib_zone_updates.get(h_ord, "")
            # Jämför sändningsnummer och orderdatum mot matchande butiksorder
            cur_ship = str(h_row["Sändningsnr"]).strip()
            cur_date = str(h_row["Orderdatum"]).strip()

            # Kundnamn för HIB‑ordern, används för att prioritera matchning mot samma butik
            hib_kundnamn = order_to_kundnamn.get(h_ord, "").strip().lower()

            # Försök hitta butiksorder som matchar både sändningsnummer och kundnamn
            def _store_kname(ordnr: str) -> str:
                return order_to_kundnamn.get(ordnr, "").strip().lower()

            # Kandidater med samma sändningsnummer och samma kundnamn
            # Använd alla butiksordrar (store_df) för att hitta matchning på sändningsnummer
            # oavsett status. Detta säkerställer att en HIB‑order som redan är kopplad till
            # en butik med ett avslutat orderstatus (>34) inte kopplas om till en annan butik
            # bara för att dess butik inte finns i valid_store_df.
            ship_kname_candidates = store_df[
                (store_df["Sändningsnr"].astype(str).str.strip() == cur_ship)
                & (store_df["Ordernr"].map(lambda x: _store_kname(x) == hib_kundnamn))
            ]
            if not ship_kname_candidates.empty:
                # Välj den tidigaste av de butiksorder som matchar både sändningsnummer och kundnamn
                candidate_row = _choose_earliest(ship_kname_candidates)
            else:
                # Annars matcha endast på sändningsnummer (oavsett kundnamn) i alla butiksordrar
                ship_candidates = store_df[store_df["Sändningsnr"].astype(str).str.strip() == cur_ship]
                if not ship_candidates.empty:
                    candidate_row = _choose_earliest(ship_candidates)
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
            ursprungsdatum = ""
            if "Ursprungsdatum" in ov.columns:
                udat_vals = kund_df.loc[kund_df["Ordernr"] == h_ord, "Ursprungsdatum"].dropna().astype(str).str.strip()
                if not udat_vals.empty:
                    ursprungsdatum = udat_vals.iloc[0]
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
        # Gruppera efter kundnummer
        for kund_nr, kund_df in ov.groupby("Kund nr"):
            store_df = kund_df[kund_df["Ordertyp"] == "N"].copy()
            hib_df = kund_df[kund_df["Ordertyp"] == "HIB"].copy()
            ignored_hib_orders = _hib_orders_with_today_origin(kund_df)
            if ignored_hib_orders:
                hib_df = hib_df[~hib_df["Ordernr"].astype(str).str.strip().isin(ignored_hib_orders)].copy()
            if not store_df.empty:
                store_df = store_df.drop_duplicates(subset=["Ordernr"]).reset_index(drop=True)
            if not hib_df.empty:
                hib_df = hib_df.drop_duplicates(subset=["Ordernr"]).reset_index(drop=True)
            if store_df.empty or hib_df.empty:
                continue
            # Sändningsnummer för butikens ordrar
            store_ships: set[str] = set()
            for _, row in store_df.iterrows():
                ship = str(row.get("Sändningsnr", "")).strip()
                if ship:
                    store_ships.add(ship)
            for _, hib_row in hib_df.iterrows():
                h_ord = hib_row["Ordernr"]
                maxstatus = order_status_max.get(h_ord, 9999)
                # Intressanta HIB‑ordrar har status > 34
                if maxstatus <= 34:
                    continue
                cur_ship = str(hib_row.get("Sändningsnr", "")).strip()
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

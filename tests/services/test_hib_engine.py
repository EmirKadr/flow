"""Beteendeskydd för HIB-motorn (warehouse_tools/engine_core/hib.py).

Bakgrund: `compute_hib_koppling` och `compute_missed_departures` optimerades
2026-07-14 (kandidat #42: hoistad datumparsning, kolumnprojektion före groupby,
inga iterrows, hoistade bool-masker). Golden-testerna i
`test_warehouse_flow_characterization.py` räcker INTE som skydd:

* Den privata golden (62/3 rader) körs bara lokalt - `testdata/` är gitignorerad.
* Den syntetiska golden som faktiskt körs i CI ger {changes: 0, missed: 0}. Den
  bevisar kolumnkontrakt och kraschfrihet, inte beteende. `compute_missed_departures`
  har dessutom `except Exception: return tom DataFrame` runt hela kroppen - i CI
  kan den kasta undantag på varje rad utan att något blir rött.
* "Ursprungsdatum == idag"-grenen är DÖD i golden-körningen: testdatan är en export
  från 2026-05-19, så `pd.Timestamp.now().date()` matchar aldrig. Man kan gå sönder
  i den utan att ett enda test rodnar.

Testerna här är därför inbyggda (ingen privat testdata) och siktar exakt på de
luckorna. Referensimplementationen nedan är en ORDAGRANN kopia av koden före
optimeringen; den är facit för differentialtestet.

Tre saker kräver särskild akt (och har egna avsnitt längst ned):

* **Kolumnprojektionen** (`_project`, 45 -> 8 kolumner) är bygget största grepp och
  det som ändrar vad varje nedströms `.tolist()`/`.iloc[]` läser. Matas motorn bara
  smala ramar är `_project` en identitetsfunktion och bevisar ingenting. Avsnitt 5
  kör hela differentialen på BREDA ramar med den verkliga `v_ask_order_overview`-
  formen (43 kolumner, omkastad ordning, fientliga dekoyvärden, dubblettetiketter).
* **NaN-semantiken** mellan `store_ship_mask` (hib.py: `.astype(str)` BEHÅLLER NaN)
  och `store_date_str` (hib.py: `str(v)` ger strängen `"nan"`) skyddades tidigare
  bara av en kodkommentar. Avsnitt 6 gör den skillnaden användarsynlig.
* **Den hoistade snabbvägen** (`_OriginToday`) är det enda greppet som inte är
  trivialt beteendebevarande - och den blandade seedgenereringen tog den aldrig
  (0/60 seeds hade en flaggad today-HIB). Differentialen kör därför även
  format-homogena seeds (avsnitt 4).
"""
from __future__ import annotations

import random

import pandas as pd
import pytest

from warehouse_tools.engine_core.hib import (
    _HIB_LOOP_COLS,
    _MISSED_LOOP_COLS,
    _TODAY_ORIGIN_COL,
    _OriginToday,
    _project,
    compute_hib_koppling,
    compute_missed_departures,
)
from warehouse_tools.engine_core.io_utils import smart_to_datetime

# ---------------------------------------------------------------------------
# Referensimplementation: ordagrann kopia av hib.py före optimeringen (HEAD
# 54b9371). Ändra ALDRIG den här koden för att få ett rött test grönt - den är
# definitionen av "oförändrat beteende". Ändras produktbeteendet avsiktligt ska
# både referensen och golden uppdateras medvetet, i samma arbetsinsats.
# ---------------------------------------------------------------------------

def _ref_hib_orders_with_today_origin(kund_df: pd.DataFrame) -> set[str]:
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


_EMPTY_CHANGES = ["ordernummer", "Ursprungsdatum", "Orderdatum", "sändningsnummer", "Zon", "Multi"]


def _ref_compute_hib_koppling(details_df: pd.DataFrame, overview_df: pd.DataFrame) -> pd.DataFrame:
    details = details_df.copy()
    overview = overview_df.copy()
    details.columns = [str(c).replace("﻿", "").strip() for c in details.columns]
    overview.columns = [str(c).replace("﻿", "").strip() for c in overview.columns]

    required_overview_cols = {"Ordernr", "Ordertyp", "Kund nr", "Orderdatum", "Sändningsnr", "Zon", "Multi"}
    if [c for c in required_overview_cols if c not in overview.columns]:
        return pd.DataFrame(columns=_EMPTY_CHANGES)

    ov = overview.copy()
    ov["Ordertyp"] = ov["Ordertyp"].astype(str).str.strip().str.upper()
    if ov.empty:
        return pd.DataFrame(columns=_EMPTY_CHANGES)
    if "Order nr" not in details.columns or "Status" not in details.columns:
        return pd.DataFrame(columns=_EMPTY_CHANGES)

    def to_status_numeric(x):
        try:
            return int(float(str(x).strip()))
        except Exception:
            return 9999

    details["_status_num"] = details["Status"].apply(to_status_numeric)
    order_status_max = details.groupby("Order nr")["_status_num"].max().to_dict()
    order_zones = details.groupby("Order nr")["Zon"].apply(lambda x: list(x.dropna().astype(str))).to_dict()

    order_to_kundnamn: dict[str, str] = {}
    if "Order nr" in details.columns and "Kund.1" in details.columns:
        try:
            order_to_kundnamn = (
                details.groupby("Order nr")["Kund.1"].first().fillna("").astype(str).str.strip().to_dict()
            )
        except Exception:
            order_to_kundnamn = {}

    rows: list[dict] = []
    for _kund_nr, kund_df in ov.groupby("Kund nr"):
        store_df = kund_df[kund_df["Ordertyp"] == "N"].copy()
        hib_df = kund_df[kund_df["Ordertyp"] == "HIB"].copy()
        ignored_hib_orders = _ref_hib_orders_with_today_origin(kund_df)
        if ignored_hib_orders:
            hib_df = hib_df[~hib_df["Ordernr"].astype(str).str.strip().isin(ignored_hib_orders)].copy()
        if not store_df.empty:
            store_df = store_df.drop_duplicates(subset=["Ordernr"]).reset_index(drop=True)
        if not hib_df.empty:
            hib_df = hib_df.drop_duplicates(subset=["Ordernr"]).reset_index(drop=True)
        if store_df.empty or hib_df.empty:
            continue
        valid_store_df = store_df[store_df["Ordernr"].map(lambda o: order_status_max.get(o, 0) < 34)].copy()
        if valid_store_df.empty:
            continue

        def _choose_earliest(df: pd.DataFrame) -> pd.Series:
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
                    if date_str < earliest_date:
                        earliest_row = r
                        earliest_date = date_str
            return earliest_row

        fallback_store_row = _choose_earliest(valid_store_df)
        hib_orders: list[dict] = []
        for _, hib_row in hib_df.iterrows():
            h_ord = hib_row["Ordernr"]
            if order_status_max.get(h_ord, 9999) >= 34:
                continue
            hib_orders.append({"row": hib_row, "ordernr": h_ord})
        if not hib_orders:
            continue

        hib_zone_updates: dict = {}
        for hib in hib_orders:
            h_ord = hib["ordernr"]
            zones = [z.strip().upper() for z in order_zones.get(h_ord, []) if str(z).strip()]
            hib_zone_updates[h_ord] = "F" if any(z not in ("F", "H", "R") for z in zones) else ""

        hib_f_multi: dict[str, list[str]] = {}
        missing_multi_per_order: dict[str, bool] = {}
        for hib in hib_orders:
            h_ord = hib["ordernr"]
            hib_zone_rows = kund_df[
                (kund_df["Ordernr"] == h_ord)
                & (kund_df["Zon"].astype(str).str.strip().str.upper() == "F")
            ]
            mlist: list[str] = []
            if hib_zone_rows.empty:
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

        multi_vals_global: set[str] = {m for ml in hib_f_multi.values() for m in ml if m}
        common_multi_exists = len(multi_vals_global) == 1
        common_multi_value = next(iter(multi_vals_global)) if common_multi_exists else None

        for hib in hib_orders:
            h_row = hib["row"]
            h_ord = hib["ordernr"]
            ship_update = ""
            date_update = ""
            z_update = hib_zone_updates.get(h_ord, "")
            cur_ship = str(h_row["Sändningsnr"]).strip()
            cur_date = str(h_row["Orderdatum"]).strip()
            hib_kundnamn = order_to_kundnamn.get(h_ord, "").strip().lower()

            def _store_kname(ordnr) -> str:
                return order_to_kundnamn.get(ordnr, "").strip().lower()

            ship_kname_candidates = store_df[
                (store_df["Sändningsnr"].astype(str).str.strip() == cur_ship)
                & (store_df["Ordernr"].map(lambda x: _store_kname(x) == hib_kundnamn))
            ]
            if not ship_kname_candidates.empty:
                candidate_row = _choose_earliest(ship_kname_candidates)
            else:
                ship_candidates = store_df[store_df["Sändningsnr"].astype(str).str.strip() == cur_ship]
                candidate_row = _choose_earliest(ship_candidates) if not ship_candidates.empty else fallback_store_row

            ref_ship = str(candidate_row["Sändningsnr"]).strip()
            ref_date = str(candidate_row["Orderdatum"]).strip()
            if cur_ship != ref_ship:
                ship_update = ref_ship
            if cur_date != ref_date:
                date_update = ref_date

            multi_update = ""
            if len(hib_orders) > 1:
                if missing_multi_per_order.get(h_ord, False):
                    multi_update = "MULTI"
                elif common_multi_exists:
                    if set(hib_f_multi.get(h_ord, [])) != {common_multi_value}:
                        multi_update = "MULTI"
                else:
                    multi_update = "MULTI"

            ursprungsdatum = ""
            if "Ursprungsdatum" in ov.columns:
                udat = kund_df.loc[kund_df["Ordernr"] == h_ord, "Ursprungsdatum"].dropna().astype(str).str.strip()
                if not udat.empty:
                    ursprungsdatum = udat.iloc[0]

            if ship_update or date_update or z_update or multi_update:
                rows.append({
                    "ordernummer": h_ord,
                    "kundnamn": order_to_kundnamn.get(h_ord, ""),
                    "Ursprungsdatum": ursprungsdatum,
                    "Orderdatum": date_update,
                    "sändningsnummer": ship_update,
                    "Zon": z_update,
                    "Multi": multi_update,
                })

    if not rows:
        return pd.DataFrame(columns=_EMPTY_CHANGES)
    result_df = pd.DataFrame(rows).sort_values(by=["kundnamn", "ordernummer"]).reset_index(drop=True)
    return result_df[["ordernummer", "kundnamn", "Ursprungsdatum", "Orderdatum", "sändningsnummer", "Zon", "Multi"]]


def _ref_compute_missed_departures(details_df: pd.DataFrame, overview_df: pd.DataFrame) -> pd.DataFrame:
    cols = ["ordernummer", "kundnamn", "Missat"]
    try:
        details = details_df.copy()
        overview = overview_df.copy()
        details.columns = [str(c).replace("﻿", "").strip() for c in details.columns]
        overview.columns = [str(c).replace("﻿", "").strip() for c in overview.columns]
        if any(c not in overview.columns for c in {"Ordernr", "Ordertyp", "Kund nr", "Sändningsnr"}):
            return pd.DataFrame(columns=cols)
        ov = overview.copy()
        ov["Ordertyp"] = ov["Ordertyp"].astype(str).str.strip().str.upper()
        if ov.empty or "Order nr" not in details.columns or "Status" not in details.columns:
            return pd.DataFrame(columns=cols)

        def to_status_numeric(x):
            try:
                return int(float(str(x).strip()))
            except Exception:
                return 9999

        details["_status_num"] = details["Status"].apply(to_status_numeric)
        order_status_max = details.groupby("Order nr")["_status_num"].max().to_dict()
        order_to_kundnamn: dict[str, str] = {}
        if "Order nr" in details.columns and "Kund.1" in details.columns:
            try:
                order_to_kundnamn = (
                    details.groupby("Order nr")["Kund.1"].first().fillna("").astype(str).str.strip().to_dict()
                )
            except Exception:
                order_to_kundnamn = {}

        rows: list[dict] = []
        for _kund_nr, kund_df in ov.groupby("Kund nr"):
            store_df = kund_df[kund_df["Ordertyp"] == "N"].copy()
            hib_df = kund_df[kund_df["Ordertyp"] == "HIB"].copy()
            ignored = _ref_hib_orders_with_today_origin(kund_df)
            if ignored:
                hib_df = hib_df[~hib_df["Ordernr"].astype(str).str.strip().isin(ignored)].copy()
            if not store_df.empty:
                store_df = store_df.drop_duplicates(subset=["Ordernr"]).reset_index(drop=True)
            if not hib_df.empty:
                hib_df = hib_df.drop_duplicates(subset=["Ordernr"]).reset_index(drop=True)
            if store_df.empty or hib_df.empty:
                continue
            store_ships: set[str] = set()
            for _, row in store_df.iterrows():
                ship = str(row.get("Sändningsnr", "")).strip()
                if ship:
                    store_ships.add(ship)
            for _, hib_row in hib_df.iterrows():
                h_ord = hib_row["Ordernr"]
                if order_status_max.get(h_ord, 9999) <= 34:
                    continue
                cur_ship = str(hib_row.get("Sändningsnr", "")).strip()
                if cur_ship and cur_ship in store_ships:
                    continue
                rows.append({
                    "ordernummer": h_ord,
                    "kundnamn": order_to_kundnamn.get(h_ord, ""),
                    "Missat": "MISSAT SIN AVGÅNG",
                })
        if not rows:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame(rows).sort_values(by=["kundnamn", "ordernummer"]).reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=cols)


# ---------------------------------------------------------------------------
# Hjälpare
# ---------------------------------------------------------------------------

OV_COLS = ["Ordernr", "Ordertyp", "Kund nr", "Orderdatum", "Sändningsnr", "Zon", "Multi", "Ursprungsdatum"]


def _overview(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=OV_COLS)


def _details(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["Order nr", "Status", "Zon", "Kund.1"])


def _assert_same(left: pd.DataFrame, right: pd.DataFrame, what: str) -> None:
    """Cell-för-cell-likhet, NaN-okänslig (samma normalisering som golden-testet)."""
    assert list(left.columns) == list(right.columns), f"{what}: kolumner skiljer"
    assert len(left) == len(right), f"{what}: radantal {len(left)} != {len(right)}"
    lo = left.astype(object).where(left.notna(), None).reset_index(drop=True)
    ro = right.astype(object).where(right.notna(), None).reset_index(drop=True)
    assert lo.equals(ro), f"{what}: cellvärden skiljer\n--- optimerad ---\n{lo}\n--- referens ---\n{ro}"


def _today(fmt: str) -> str:
    return pd.Timestamp.now().strftime(fmt)


# --- Bred overview-ram -----------------------------------------------------
# Den verkliga kolumnuppsättningen i v_ask_order_overview (43 kolumner). Bara 8 av
# dem läses av kundloopen; resten är exakt det `_project` ska kasta bort. Alla
# tester som bara matar OV_COLS kör `_project` som identitetsfunktion och säger
# därför ingenting om projektionen.
_ORDER_OVERVIEW_COLS = (
    "Ordernr", "Status", "Land", "Struktur", "Trans nr", "Transportör", "Prio",
    "Starttid", "Orderdatum", "Leveransdatum", "Ursprungsdatum", "Laststarttid",
    "Avgångstid", "Yta", "Användare", "Timestamp", "Rader", "Antal", "Zon",
    "Multi", "SPC", "Robot info", "Ordertyp", "Lager", "Volym", "Vikt",
    "Kund nr", "Kund", "Avgångsnr.", "Multi index", "Vagn", "Sändningsnr",
    "Produkt", "TransportProdukt", "Avgång", "Bolag", "Alt adress", "Kund Adr",
    "Butiks nr", "Kund ref", "Inköpsnr", "Meddelande", "Orderflag",
)
_DECOY_COLS = tuple(c for c in _ORDER_OVERVIEW_COLS if c not in OV_COLS)

# Dekoyvärden som är AVSIKTLIGT giftiga: läser projektionen fel kolumn ska svaret
# sluta stämma mot referensen i stället för att råka bli rätt ändå.
_DECOY_VALUES = {
    "Status": "9999",              # läst som Ordertyp/Status => allt annat utfall
    "Land": "HIB",                 # läst som Ordertyp => butiksordern blir HIB
    "Vagn": "N",                   # läst som Ordertyp => HIB-ordern blir butik
    "Leveransdatum": "1999-01-01",  # läst som Orderdatum => "äldst"-valet kastas om
    "Starttid": "2099-12-31",      # läst som Orderdatum => likaså
    "Multi index": "MULTI-FEL",    # läst som Multi => multi-logiken spårar ur
    "Kund": "FEL BUTIK",           # läst som Kund nr => grupperingen spårar ur
    "Avgångsnr.": "SHIP-FEL",      # läst som Sändningsnr => fel butiksmatchning
}


def _decoy_value(col: str, i: int) -> str:
    return _DECOY_VALUES.get(col, f"{col}#{i}")


def _widen(ov: pd.DataFrame, *, seed: int = 0, duplicate: str | None = None) -> pd.DataFrame:
    """Blås upp en smal overview-ram till den verkliga 43-kolumnersformen.

    Samma rader och samma värden i loop-kolumnerna, men med dekoy-kolumnerna
    inskjutna och HELA kolumnordningen omkastad. `duplicate` lägger till en extra
    kolumn med ett redan använt namn - dubblettetiketter är verklighet i ASK-
    exporterna (v_ask_customer_order_details_all har både "Kund Kund" och
    "Artikel Artikel") och triggar `_project`s dubblettgren.
    """
    rnd = random.Random(90210 + seed)
    wide = pd.DataFrame(index=ov.index)
    for col in ov.columns:
        wide[col] = ov[col]
    for col in _DECOY_COLS:
        wide[col] = [_decoy_value(col, i) for i in range(len(ov))]
    cols = list(wide.columns)
    rnd.shuffle(cols)
    wide = wide.loc[:, cols]
    if duplicate is not None:
        extra = pd.DataFrame({duplicate: [f"DUBBLETT#{i}" for i in range(len(ov))]}, index=ov.index)
        wide = pd.concat([wide, extra], axis=1)
    return wide


# ---------------------------------------------------------------------------
# 1. "Ursprungsdatum == idag" - den gren som är DÖD i golden-körningen
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("majoritet_fmt", "idag_fmt"),
    [
        ("%Y-%m-%d", "%d/%m/%Y"),   # ISO-majoritet + slash-datum för idag
        ("%Y-%m-%d", "%Y%m%d"),     # ISO-majoritet + 8-siffrigt för idag
        ("%Y%m%d", "%Y-%m-%d"),     # 8-siffrig majoritet + ISO för idag
        ("%Y-%m-%d", "%Y-%m-%d"),   # homogent (den snabba vägen på verklig data)
    ],
)
def test_today_origin_ignoreras_aven_vid_blandade_datumformat(majoritet_fmt, idag_fmt):
    """En HIB-order vars Ursprungsdatum är IDAG ska ignoreras - oavsett datumformat.

    Detta är vakten mot en naiv hoist av `smart_to_datetime` till hela `ov`.
    smart_to_datetime gör sample-baserad formatinferens och pandas 3 härleder ETT
    format per anrop ur seriens första icke-null-värde. Parsar man hela filen i
    stället för kundgruppen kan både grenvalet och resultatet bli ett annat.

    Uppställningen är exakt den som skiljer en naiv hoist från den korrekta:
    kund K1:s EGNA ursprungsdatum är homogena i `idag_fmt` (så per-grupp-parsningen
    hittar dagens datum och ignorerar H2), medan FILENS majoritet är `majoritet_fmt`
    (så en global parsning härleder fel format för K1 och missar H2). Optimeringen
    får därför bara ta den globala vägen när HELA kolumnen är format-homogen -
    annars ska den falla tillbaka på per-grupp-parsningen.
    """
    gammalt = pd.Timestamp("2026-05-13")
    overview = _overview([
        # Kund 1: butik + två HIB. Gruppens Ursprungsdatum är homogena i idag_fmt.
        {"Ordernr": "N1", "Ordertyp": "N", "Kund nr": "K1", "Orderdatum": "2026-05-10",
         "Sändningsnr": "S1", "Zon": "F", "Multi": "M1", "Ursprungsdatum": gammalt.strftime(idag_fmt)},
        {"Ordernr": "H1", "Ordertyp": "HIB", "Kund nr": "K1", "Orderdatum": "2026-05-12",
         "Sändningsnr": "S9", "Zon": "F", "Multi": "M1", "Ursprungsdatum": gammalt.strftime(idag_fmt)},
        {"Ordernr": "H2", "Ordertyp": "HIB", "Kund nr": "K1", "Orderdatum": "2026-05-12",
         "Sändningsnr": "S9", "Zon": "F", "Multi": "M2", "Ursprungsdatum": _today(idag_fmt)},
        # Kund 2..7: bulk som ger majoritetsformatet dess majoritet i filen.
        *[
            {"Ordernr": f"N{i}", "Ordertyp": "N", "Kund nr": f"K{i}", "Orderdatum": "2026-05-10",
             "Sändningsnr": f"S{i}", "Zon": "F", "Multi": "M1",
             "Ursprungsdatum": gammalt.strftime(majoritet_fmt)}
            for i in range(2, 8)
        ],
    ])
    details = _details([
        {"Order nr": "N1", "Status": "10", "Zon": "F", "Kund.1": "Butik A"},
        {"Order nr": "H1", "Status": "10", "Zon": "F", "Kund.1": "Butik A"},
        {"Order nr": "H2", "Status": "10", "Zon": "F", "Kund.1": "Butik A"},
    ])

    ref = _ref_compute_hib_koppling(details, overview)
    got = compute_hib_koppling(details, overview)
    _assert_same(got, ref, f"hib-koppling (fil {majoritet_fmt} + K1/idag {idag_fmt})")

    # Och det konkreta beteendet: H2 (ursprungsdatum = idag) ska aldrig föreslås.
    assert "H2" not in set(got["ordernummer"]), (
        "HIB-order med dagens Ursprungsdatum kom med i Ändringar-tabellen"
    )
    # H1 ska däremot finnas (sändningsnr S9 != butikens S1 -> ändring föreslås).
    assert "H1" in set(got["ordernummer"])


def test_today_origin_utan_nat_kraver_homogenitetsvakt(monkeypatch):
    """Det HÅRDA fallet: global parsning ger NOLL NaT men ÄNDÅ fel datum.

    Det räcker alltså INTE att kontrollera "föll något icke-tomt värde till NaT
    globalt?" innan man använder den hoistade parsningen - en sådan vakt fyrar
    aldrig här. `smart_to_datetime` måste vara format-HOMOGEN över hela kolumnen.

    Mekanism (verifierad i pandas 3.0.3): ett icke-nollutfyllt ISO-datum
    ("2026-5-7") bland nollutfyllda ISO-datum gör att pandas inte kan gissa ett
    format och faller tillbaka på dateutil per element - då parsar ALLA värden
    (noll NaT), men `dayfirst` skiljer:
      * hela filen  -> iso_like (majoriteten är nollutfylld) -> dayfirst=False -> 2026-05-07
      * kundgruppen -> iso_like FALSKT (inget värde är nollutfyllt) -> dayfirst=True -> 2026-07-05
    Med dagens datum fryst till 2026-07-05 ignorerar den gamla (per-grupp) koden
    därför HIB-ordern, medan en hoist utan homogenitetsvakt INTE gör det.

    Faller detta test: någon har tagit bort eller försvagat homogenitetsvakten i
    _OriginToday. Den är load-bearing, inte defensiv utfyllnad.
    """
    frozen = pd.Timestamp("2026-07-05 09:00:00")
    monkeypatch.setattr(pd.Timestamp, "now", classmethod(lambda cls, tz=None: frozen))
    assert pd.Timestamp.now().date() == frozen.date()

    overview = _overview([
        # Kund K1: alla ursprungsdatum är icke-nollutfyllda -> gruppen får dayfirst=True.
        {"Ordernr": "N1", "Ordertyp": "N", "Kund nr": "K1", "Orderdatum": "2026-05-10",
         "Sändningsnr": "S1", "Zon": "F", "Multi": "M1", "Ursprungsdatum": "2026-5-3"},
        {"Ordernr": "H1", "Ordertyp": "HIB", "Kund nr": "K1", "Orderdatum": "2026-05-12",
         "Sändningsnr": "S9", "Zon": "F", "Multi": "M1", "Ursprungsdatum": "2026-5-3"},
        # H2: per grupp -> 2026-07-05 (= fryst idag). Globalt -> 2026-05-07 (!= idag).
        {"Ordernr": "H2", "Ordertyp": "HIB", "Kund nr": "K1", "Orderdatum": "2026-05-12",
         "Sändningsnr": "S9", "Zon": "F", "Multi": "M2", "Ursprungsdatum": "2026-5-7"},
        # Bulk med nollutfyllda ISO-datum -> filens majoritet blir iso_like.
        *[
            {"Ordernr": f"N{i}", "Ordertyp": "N", "Kund nr": f"K{i}", "Orderdatum": "2026-05-10",
             "Sändningsnr": f"S{i}", "Zon": "F", "Multi": "M1", "Ursprungsdatum": "2026-05-13"}
            for i in range(2, 8)
        ],
    ])
    details = _details([
        {"Order nr": "N1", "Status": "10", "Zon": "F", "Kund.1": "Butik A"},
        {"Order nr": "H1", "Status": "10", "Zon": "F", "Kund.1": "Butik A"},
        {"Order nr": "H2", "Status": "10", "Zon": "F", "Kund.1": "Butik A"},
    ])

    # Förutsättningen som gör fallet hårt: den globala parsningen har inga NaT alls.
    globalt = smart_to_datetime(overview["Ursprungsdatum"])
    assert not bool((globalt.isna() & overview["Ursprungsdatum"].notna()).any()), (
        "fixturen tappade sin poäng - global parsning gav NaT, då räcker en NaT-vakt"
    )

    ref = _ref_compute_hib_koppling(details, overview)
    got = compute_hib_koppling(details, overview)
    _assert_same(got, ref, "hib-koppling (noll NaT globalt, ändå fel datum)")
    assert "H2" not in set(got["ordernummer"]), (
        "HIB-order med dagens Ursprungsdatum kom med - homogenitetsvakten i "
        "_OriginToday saknas eller är för svag"
    )
    assert "H1" in set(got["ordernummer"])


def test_today_origin_ignoreras_i_missade_avgangar():
    """Samma today-origin-gren, men i compute_missed_departures."""
    overview = _overview([
        {"Ordernr": "N1", "Ordertyp": "N", "Kund nr": "K1", "Orderdatum": "2026-05-10",
         "Sändningsnr": "S1", "Zon": "F", "Multi": "M1", "Ursprungsdatum": "2026-05-17"},
        {"Ordernr": "H1", "Ordertyp": "HIB", "Kund nr": "K1", "Orderdatum": "2026-05-12",
         "Sändningsnr": "S9", "Zon": "F", "Multi": "M1", "Ursprungsdatum": _today("%Y-%m-%d")},
    ])
    details = _details([
        {"Order nr": "N1", "Status": "10", "Zon": "F", "Kund.1": "Butik A"},
        {"Order nr": "H1", "Status": "40", "Zon": "F", "Kund.1": "Butik A"},  # > 34 => missad avgång
    ])
    got = compute_missed_departures(details, overview)
    _assert_same(got, _ref_compute_missed_departures(details, overview), "missade avgångar (today-origin)")
    assert got.empty, "HIB-order med dagens Ursprungsdatum ska inte rapporteras som missad avgång"


# ---------------------------------------------------------------------------
# 2. _choose_earliest-semantiken (fyra regler) - får INTE bli idxmin
# ---------------------------------------------------------------------------

def _earliest_case(store_datum: list[str]) -> pd.DataFrame:
    """Bygg ett fall där HIB-orderns sändningsnr matchar ALLA butiksordrar, så att
    valet av referensbutik enbart avgörs av 'äldst orderdatum'-regeln. Butikens
    sändningsnummer är unikt per rad -> resultatets sändningsnummer avslöjar vilken
    rad som vann."""
    rows = []
    for i, datum in enumerate(store_datum):
        rows.append({
            "Ordernr": f"N{i}", "Ordertyp": "N", "Kund nr": "K1", "Orderdatum": datum,
            "Sändningsnr": "SHIP", "Zon": "F", "Multi": "M1", "Ursprungsdatum": "2026-05-17",
        })
    rows.append({
        "Ordernr": "H1", "Ordertyp": "HIB", "Kund nr": "K1", "Orderdatum": "2000-01-01",
        "Sändningsnr": "ANNAT", "Zon": "F", "Multi": "M1", "Ursprungsdatum": "2026-05-17",
    })
    return _overview(rows)


def _earliest_details(n_store: int) -> pd.DataFrame:
    rows = [{"Order nr": f"N{i}", "Status": "10", "Zon": "F", "Kund.1": "Butik A"} for i in range(n_store)]
    rows.append({"Order nr": "H1", "Status": "10", "Zon": "F", "Kund.1": "Butik A"})
    return _details(rows)


@pytest.mark.parametrize(
    "datum",
    [
        ["2026-05-10", "2026-05-12"],                 # (b) normalfall, äldst vinner
        ["2026-05-12", "2026-05-10"],                 # äldst vinner även när den ligger sist
        ["2026-05-10", "2026-05-10"],                 # (d) lika datum -> FÖRSTA raden vinner
        ["skräp", "2026-05-10"],                      # (b) icke-NaT slår NaT
        ["2026-05-10", "skräp"],                      # (b) åt andra hållet
        ["skräp", ""],                                # (c) båda NaT -> lexikografiskt ("" < "skräp")
        ["", "skräp"],                                # (c) åt andra hållet
        ["zzz", "aaa"],                               # (c) båda NaT -> lexikografiskt
        ["aaa", "aaa"],                               # (c)+(d) båda NaT och lika -> första raden
        ["", "", ""],                                 # (a) allt NaT och lika -> första raden
        ["2026-05-10", "skräp", "2026-05-09"],        # blandat
        ["skräp", "2026-05-09", "2026-05-09"],        # lika äldsta datum + NaT
    ],
)
def test_choose_earliest_semantik(datum):
    """Regel (a) första raden är default, (b) icke-NaT slår NaT, (c) båda NaT ->
    lexikografisk jämförelse av RÅDATUMSTRÄNGARNA, (d) strikt '<' -> vid lika datum
    vinner FÖRSTA raden. idxmin hoppar över NaT och saknar strängfallback."""
    overview = _earliest_case(datum)
    details = _earliest_details(len(datum))
    _assert_same(
        compute_hib_koppling(details, overview),
        _ref_compute_hib_koppling(details, overview),
        f"choose_earliest {datum}",
    )


def test_lika_orderdatum_ger_forsta_butiksordern():
    """Minimifall för regel (d), oberoende av referensimplementationen: två
    butiksordrar med SAMMA orderdatum men olika sändningsnr -> HIB-ordern ska få
    den FÖRSTA butiksorderns sändningsnummer (strikt '<', ingen omsortering)."""
    overview = _overview([
        {"Ordernr": "N1", "Ordertyp": "N", "Kund nr": "K1", "Orderdatum": "2026-05-10",
         "Sändningsnr": "FORST", "Zon": "F", "Multi": "M1", "Ursprungsdatum": "2026-05-17"},
        {"Ordernr": "N2", "Ordertyp": "N", "Kund nr": "K1", "Orderdatum": "2026-05-10",
         "Sändningsnr": "ANDRA", "Zon": "F", "Multi": "M1", "Ursprungsdatum": "2026-05-17"},
        {"Ordernr": "H1", "Ordertyp": "HIB", "Kund nr": "K1", "Orderdatum": "2026-05-10",
         "Sändningsnr": "SAKNAS", "Zon": "F", "Multi": "M1", "Ursprungsdatum": "2026-05-17"},
    ])
    details = _details([
        {"Order nr": "N1", "Status": "10", "Zon": "F", "Kund.1": "Butik A"},
        {"Order nr": "N2", "Status": "10", "Zon": "F", "Kund.1": "Butik A"},
        {"Order nr": "H1", "Status": "10", "Zon": "F", "Kund.1": "Butik A"},
    ])
    got = compute_hib_koppling(details, overview)
    assert len(got) == 1
    assert got.iloc[0]["sändningsnummer"] == "FORST"


# ---------------------------------------------------------------------------
# 3. compute_missed_departures får inte vara tyst tom
# ---------------------------------------------------------------------------

def test_missed_departures_ar_inte_tyst_tom():
    """Vakt mot `except Exception: return tom DataFrame` (hib.py). Den syntetiska
    golden som körs i CI är 0 rader missade avgångar - kastar funktionen undantag
    på varje rad blir ingenting rött. Här MÅSTE exakt en rad komma ut."""
    overview = _overview([
        {"Ordernr": "N1", "Ordertyp": "N", "Kund nr": "K1", "Orderdatum": "2026-05-10",
         "Sändningsnr": "S1", "Zon": "F", "Multi": "M1", "Ursprungsdatum": "2026-05-17"},
        {"Ordernr": "H1", "Ordertyp": "HIB", "Kund nr": "K1", "Orderdatum": "2026-05-12",
         "Sändningsnr": "S-OKAND", "Zon": "F", "Multi": "M1", "Ursprungsdatum": "2026-05-17"},
    ])
    details = _details([
        {"Order nr": "N1", "Status": "10", "Zon": "F", "Kund.1": "Butik A"},
        {"Order nr": "H1", "Status": "40", "Zon": "F", "Kund.1": "Butik A"},  # > 34
    ])
    got = compute_missed_departures(details, overview)
    assert len(got) == 1, "missad avgång rapporterades inte - swallow:en kan dölja ett undantag"
    assert got.iloc[0]["ordernummer"] == "H1"
    assert got.iloc[0]["Missat"] == "MISSAT SIN AVGÅNG"
    assert got.iloc[0]["kundnamn"] == "Butik A"
    assert list(got.columns) == ["ordernummer", "kundnamn", "Missat"]


def test_missed_departures_matchande_sandningsnr_ar_inte_missad():
    """Motsatsen: samma sändningsnr som butiken -> ingen missad avgång."""
    overview = _overview([
        {"Ordernr": "N1", "Ordertyp": "N", "Kund nr": "K1", "Orderdatum": "2026-05-10",
         "Sändningsnr": "S1", "Zon": "F", "Multi": "M1", "Ursprungsdatum": "2026-05-17"},
        {"Ordernr": "H1", "Ordertyp": "HIB", "Kund nr": "K1", "Orderdatum": "2026-05-12",
         "Sändningsnr": "S1", "Zon": "F", "Multi": "M1", "Ursprungsdatum": "2026-05-17"},
    ])
    details = _details([
        {"Order nr": "N1", "Status": "10", "Zon": "F", "Kund.1": "Butik A"},
        {"Order nr": "H1", "Status": "40", "Zon": "F", "Kund.1": "Butik A"},
    ])
    assert compute_missed_departures(details, overview).empty


# ---------------------------------------------------------------------------
# 4. Differentialtest mot referensimplementationen
# ---------------------------------------------------------------------------

_DATUM_ALTERNATIV = [
    "2026-05-10", "2026-05-12", "2026-05-12", "2026-06-04",
    "", "skräp", "20260512", "12/05/2026", None,
]
_SHIP_ALTERNATIV = ["S1", "S2", "S1", "", None]
_ZON_ALTERNATIV = ["F", "H", "R", "K", "", None]
_MULTI_ALTERNATIV = ["M1", "M2", "", None]
_STATUS_ALTERNATIV = ["10", "33", "34", "35", "40", "", "inf", "abc", None]


def _urspool(lage: str) -> list | None:
    """Ursprungsdatum-pool per läge.

    `blandat` = det ursprungliga (heterogena) läget. Där är kolumnen ALDRIG
    format-homogen, så `_OriginToday` faller alltid tillbaka på per-grupp-parsning:
    den hoistade snabbvägen körs inte en enda gång i de 60 blandade seedsen (mätt:
    0/60 hade en flaggad today-HIB). `iso`/`num8` ger en format-homogen kolumn -
    det är det enda sättet att faktiskt exekvera hoisten. Dagens datum ligger med
    tre gånger i poolen så att `is_today`-grenen får träff i de flesta seeds.
    """
    if lage == "blandat":
        return None
    if lage == "iso":
        idag = _today("%Y-%m-%d")
        return ["2026-05-10", "2026-05-12", "2026-06-04", "2026-01-31", None, idag, idag, idag]
    if lage == "num8":
        idag = _today("%Y%m%d")
        return ["20260510", "20260512", "20260604", "20260131", None, idag, idag, idag]
    raise AssertionError(f"okänt läge: {lage}")


def _slumpram(rnd: random.Random, urs_pool: list | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pseudoslumpad (details, overview). `urs_pool` styr Ursprungsdatum-kolumnen.

    OBS: när `urs_pool is None` görs EXAKT samma sekvens av rnd-anrop som före
    utökningen, så de 60 ursprungliga blandade seedsen behåller sin data.
    """
    n_kunder = rnd.randint(1, 4)
    ov_rows: list[dict] = []
    det_rows: list[dict] = []
    hib_urs = _DATUM_ALTERNATIV + [_today("%Y-%m-%d"), _today("%d/%m/%Y"), _today("%Y%m%d")]
    for k in range(n_kunder):
        kund = f"K{k}"
        butiker = rnd.randint(0, 3)
        hibbar = rnd.randint(0, 3)
        for i in range(butiker):
            o = f"N{k}_{i}"
            ov_rows.append({
                "Ordernr": o, "Ordertyp": "N", "Kund nr": kund,
                "Orderdatum": rnd.choice(_DATUM_ALTERNATIV),
                "Sändningsnr": rnd.choice(_SHIP_ALTERNATIV),
                "Zon": rnd.choice(_ZON_ALTERNATIV),
                "Multi": rnd.choice(_MULTI_ALTERNATIV),
                "Ursprungsdatum": rnd.choice(urs_pool if urs_pool is not None else _DATUM_ALTERNATIV),
            })
            det_rows.append({
                "Order nr": o, "Status": rnd.choice(_STATUS_ALTERNATIV),
                "Zon": rnd.choice(_ZON_ALTERNATIV), "Kund.1": rnd.choice(["Butik A", "Butik B", "", None]),
            })
        for i in range(hibbar):
            o = f"H{k}_{i}"
            # Flera rader per HIB-order (en per zon) - dubbletter är normalfallet.
            for _ in range(rnd.randint(1, 2)):
                ov_rows.append({
                    "Ordernr": o, "Ordertyp": rnd.choice(["HIB", "hib ", "HIB"]), "Kund nr": kund,
                    "Orderdatum": rnd.choice(_DATUM_ALTERNATIV),
                    "Sändningsnr": rnd.choice(_SHIP_ALTERNATIV),
                    "Zon": rnd.choice(_ZON_ALTERNATIV),
                    "Multi": rnd.choice(_MULTI_ALTERNATIV),
                    # Ibland dagens datum -> today-origin-grenen aktiveras
                    "Ursprungsdatum": rnd.choice(urs_pool if urs_pool is not None else hib_urs),
                })
            det_rows.append({
                "Order nr": o, "Status": rnd.choice(_STATUS_ALTERNATIV),
                "Zon": rnd.choice(_ZON_ALTERNATIV), "Kund.1": rnd.choice(["Butik A", "Butik B", "", None]),
            })
        # En främmande ordertyp emellanåt
        if rnd.random() < 0.3:
            ov_rows.append({
                "Ordernr": f"E{k}", "Ordertyp": "EH", "Kund nr": kund, "Orderdatum": "2026-05-11",
                "Sändningsnr": "S3", "Zon": "F", "Multi": "M9",
                # Måste följa poolen, annars bryter raden kolumnens formathomogenitet.
                "Ursprungsdatum": "2026-05-17" if urs_pool is None else rnd.choice(urs_pool),
            })
    rnd.shuffle(ov_rows)
    return _details(det_rows), _overview(ov_rows)


def _normaliserad_ov(overview: pd.DataFrame) -> pd.DataFrame:
    """Samma ram som motorn bygger `_OriginToday` på (Ordertyp normaliserad)."""
    ov = overview.copy()
    ov["Ordertyp"] = ov["Ordertyp"].astype(str).str.strip().str.upper()
    return ov


@pytest.mark.parametrize("lage", ["blandat", "iso", "num8"])
@pytest.mark.parametrize("seed", range(60))
def test_hib_koppling_mot_referensimplementation(seed, lage):
    """Differentialtest: optimerad motor vs. den ordagranna kopian av koden före
    optimeringen, över pseudoslumpade ramar med NaT/skräpdatum/lika datum/tomma
    värden/dubblettordernr/blandade datumformat/dagens ursprungsdatum.

    `iso`/`num8` är tillagda för att faktiskt EXEKVERA den hoistade snabbvägen i
    `_OriginToday`. I `blandat` är Ursprungsdatum-kolumnen aldrig format-homogen,
    så hoisten avvisas alltid och koden faller tillbaka på per-grupp-parsningen -
    dvs. exakt det grepp som byggaren själv pekar ut som det enda icke-triviala
    hade noll differentialtäckning.
    """
    rnd = random.Random(20260714 + seed)
    details, overview = _slumpram(rnd, _urspool(lage))

    if lage != "blandat":
        origin = _OriginToday(_normaliserad_ov(overview))
        assert origin._today_hib is not None, (
            f"seed={seed} tog inte snabbvägen - då bevisar {lage}-seeden ingenting om hoisten"
        )

    _assert_same(
        compute_hib_koppling(details, overview),
        _ref_compute_hib_koppling(details, overview),
        f"hib-koppling seed={seed} läge={lage}",
    )
    _assert_same(
        compute_missed_departures(details, overview),
        _ref_compute_missed_departures(details, overview),
        f"missade avgångar seed={seed} läge={lage}",
    )


def _seeds_med_flaggad_today_hib(lage: str) -> int:
    """Antal seeds där snabbvägen både VALDES och faktiskt flaggade en HIB-order."""
    n = 0
    for seed in range(60):
        rnd = random.Random(20260714 + seed)
        _details_df, overview = _slumpram(rnd, _urspool(lage))
        origin = _OriginToday(_normaliserad_ov(overview))
        if origin._today_hib is not None and bool(origin._today_hib.any()):
            n += 1
    return n


def test_seedkorpusen_tacker_den_hoistade_snabbvagen():
    """MÄTER differentialens täckning av hoisten i stället för att påstå den.

    Det räcker inte att snabbvägen VÄLJS - den måste också flagga något, annars är
    `is_hib & is_today` bara en dyr `False`-array och differentialen säger
    fortfarande ingenting om hoistens korrekthet.

    Siffran för `blandat` är precis luckan granskaren hittade: de ursprungliga 60
    seedsen har en heterogen Ursprungsdatum-kolumn, så homogenitetsvakten avvisar
    hoisten (eller flaggar ingenting) i varenda seed. Faller assertionen för
    `iso`/`num8` har seedgenereringen slutat träna grenen och differentialen har
    tyst blivit tandlös igen.
    """
    assert _seeds_med_flaggad_today_hib("blandat") == 0, (
        "de blandade seedsen flaggar nu today-HIB - då är kommentaren ovan inaktuell, "
        "men täckningen är i så fall bara bättre; uppdatera dokumentationen"
    )
    for lage in ("iso", "num8"):
        med_traff = _seeds_med_flaggad_today_hib(lage)
        assert med_traff >= 20, (
            f"bara {med_traff}/60 {lage}-seeds flaggade en HIB-order med dagens "
            "Ursprungsdatum - snabbvägens is_hib&is_today-gren tränas inte längre"
        )


def test_saknad_ursprungsdatumkolumn_ar_ok():
    """Ursprungsdatum är valfri (den ingår inte i required_overview_cols för
    missade avgångar). Projektionen får inte krascha när kolumnen saknas."""
    overview = _overview([
        {"Ordernr": "N1", "Ordertyp": "N", "Kund nr": "K1", "Orderdatum": "2026-05-10",
         "Sändningsnr": "S1", "Zon": "F", "Multi": "M1", "Ursprungsdatum": None},
        {"Ordernr": "H1", "Ordertyp": "HIB", "Kund nr": "K1", "Orderdatum": "2026-05-12",
         "Sändningsnr": "S9", "Zon": "F", "Multi": "M1", "Ursprungsdatum": None},
    ]).drop(columns=["Ursprungsdatum"])
    details = _details([
        {"Order nr": "N1", "Status": "10", "Zon": "F", "Kund.1": "Butik A"},
        {"Order nr": "H1", "Status": "40", "Zon": "F", "Kund.1": "Butik A"},
    ])
    _assert_same(
        compute_hib_koppling(details, overview),
        _ref_compute_hib_koppling(details, overview),
        "hib-koppling utan Ursprungsdatum",
    )
    _assert_same(
        compute_missed_departures(details, overview),
        _ref_compute_missed_departures(details, overview),
        "missade avgångar utan Ursprungsdatum",
    )


# ---------------------------------------------------------------------------
# 5. Kolumnprojektionen (_project) - byggets största grepp, tidigare 0 % täckt
# ---------------------------------------------------------------------------
# Alla tester ovan matar OV_COLS, som är exakt _HIB_LOOP_COLS. Då är `_project`
# en identitetsfunktion och exekveras aldrig på en bredare ram - trots att den är
# det som avgör vad varje nedströms .tolist()/.iloc[] faktiskt läser. Här matas
# den verkliga 43-kolumnersramen i omkastad ordning.

def test_project_narrows_bred_ram_till_exakt_loop_kolumnerna():
    """STRUKTUR: projektionen ska faktiskt SMALNA av ramen.

    Behovet av ett strukturtest: differentialtesterna nedan kan per konstruktion
    INTE se om projektionen tas bort (`return ov.copy()` ÄR referensbeteendet -
    identisk utdata, bara långsammare). Backas greppet ut är det bara det här
    testet som rodnar, och vinsten (-79 %) skulle annars tyst försvinna.
    """
    bred = _widen(_overview([
        {"Ordernr": "N1", "Ordertyp": "N", "Kund nr": "K1", "Orderdatum": "2026-05-10",
         "Sändningsnr": "S1", "Zon": "F", "Multi": "M1", "Ursprungsdatum": "2026-05-17"},
    ]))
    assert len(bred.columns) == len(_ORDER_OVERVIEW_COLS), "fixturen är inte bred längre"

    # Kolumn-ORDNINGEN pinnas medvetet INTE: allt nedströms läser på namn, så en
    # omkastning vore beteendebevarande och ett test som rodnade på den vore brus.
    # Det som är kontraktet är: inga loop-kolumner tappade, inga extra kolumner kvar.
    for needed in (_HIB_LOOP_COLS, _MISSED_LOOP_COLS):
        smal = _project(bred, needed)
        assert set(smal.columns) == set(needed), "projektionen tappade eller bytte kolumner"
        assert len(smal.columns) == len(needed), (
            f"projektionen behöll {len(smal.columns)} kolumner i stället för {len(needed)} - "
            "greppet är borta och vinsten med det"
        )

    # ...och den får inte röra indatan.
    assert len(bred.columns) == len(_ORDER_OVERVIEW_COLS)


def test_project_bevarar_varden_radordning_och_index():
    """Projektionen får inte tappa, kasta om eller skriva om NÅGON cell.

    Radordningen är load-bearing: `_OriginToday.attach` lägger sin flaggkolumn som
    en POSITIONELL numpy-array beräknad på hela `ov`. Kastar `_project` om raderna
    landar today-origin-flaggorna på fel ordrar.
    """
    smal = _overview([
        {"Ordernr": f"O{i}", "Ordertyp": "HIB" if i % 2 else "N", "Kund nr": f"K{i % 3}",
         "Orderdatum": f"2026-05-{10 + i:02d}", "Sändningsnr": f"S{i}", "Zon": "F",
         "Multi": f"M{i}", "Ursprungsdatum": "2026-05-17"}
        for i in range(7)
    ])
    bred = _widen(smal, seed=3)

    got = _project(bred, _HIB_LOOP_COLS)

    assert len(got) == len(bred)
    assert list(got.index) == list(bred.index), "projektionen ändrade indexet"
    for col in _HIB_LOOP_COLS:
        assert got[col].tolist() == bred[col].tolist(), f"{col}: värden tappade eller omkastade"


@pytest.mark.parametrize("lage", ["blandat", "iso", "num8"])
@pytest.mark.parametrize("seed", range(25))
def test_bred_overview_ram_ger_samma_svar(seed, lage):
    """DIFFERENTIAL på bred ram: en 43-kolumners v_ask_order_overview i omkastad
    kolumnordning med giftiga dekoyvärden ska ge exakt samma svar som referensen
    (som aldrig projicerar) OCH som den smala ramen.

    Läser projektionen fel kolumn - t.ex. positionellt i stället för på namn - blir
    "Land"=HIB en butiksorder, "Leveransdatum"=1999-01-01 den äldsta ordern osv.
    """
    rnd = random.Random(20260714 + seed)
    details, smal = _slumpram(rnd, _urspool(lage))
    bred = _widen(smal, seed=seed)

    for namn, fn, ref_fn in (
        ("hib-koppling", compute_hib_koppling, _ref_compute_hib_koppling),
        ("missade avgångar", compute_missed_departures, _ref_compute_missed_departures),
    ):
        pa_bred = fn(details, bred)
        _assert_same(pa_bred, ref_fn(details, bred), f"{namn} bred seed={seed} läge={lage}")
        # Extra kolumner får inte ändra svaret alls.
        _assert_same(pa_bred, fn(details, smal), f"{namn} bred==smal seed={seed} läge={lage}")


def test_bred_ram_med_dubblettkolumn_ar_oforandrad():
    """`_project` har en dubblettgren (`ov.columns.duplicated()`) som aldrig kördes.

    Dubblettetiketter är verklighet i ASK-exporterna. Grenen ska lämna ramen orörd
    så beteendet blir exakt referensens.
    """
    smal = _overview([
        {"Ordernr": "N1", "Ordertyp": "N", "Kund nr": "K1", "Orderdatum": "2026-05-10",
         "Sändningsnr": "S1", "Zon": "F", "Multi": "M1", "Ursprungsdatum": "2026-05-17"},
        {"Ordernr": "H1", "Ordertyp": "HIB", "Kund nr": "K1", "Orderdatum": "2026-05-12",
         "Sändningsnr": "S9", "Zon": "F", "Multi": "M1", "Ursprungsdatum": "2026-05-17"},
    ])
    details = _details([
        {"Order nr": "N1", "Status": "10", "Zon": "F", "Kund.1": "Butik A"},
        {"Order nr": "H1", "Status": "10", "Zon": "F", "Kund.1": "Butik A"},
    ])
    # "Kund" dubbleras - en icke-loop-kolumn, precis som i de verkliga exporterna.
    bred = _widen(smal, duplicate="Kund")
    assert bool(bred.columns.duplicated().any())

    # _project ska lämna en dubblettram orörd (annars blir ov[col] en DataFrame).
    orord = _project(bred, _HIB_LOOP_COLS)
    assert list(orord.columns) == list(bred.columns), "dubblettgrenen projicerar - ramen ska lämnas orörd"

    got = compute_hib_koppling(details, bred)
    _assert_same(got, _ref_compute_hib_koppling(details, bred), "hib-koppling dubblettkolumn")
    _assert_same(got, compute_hib_koppling(details, smal), "dubblettram == smal ram")
    _assert_same(
        compute_missed_departures(details, bred),
        _ref_compute_missed_departures(details, bred),
        "missade avgångar dubblettkolumn",
    )


def test_bred_ram_tar_fortfarande_snabbvagen_och_ignorerar_dagens_hib():
    """Projektion + hoist tillsammans, på bred ram: today-origin-flaggan ska landa
    på RÄTT rad även när ramen är 43 kolumner och raderna ligger i godtycklig ordning."""
    smal = _overview([
        {"Ordernr": "N1", "Ordertyp": "N", "Kund nr": "K1", "Orderdatum": "2026-05-10",
         "Sändningsnr": "S1", "Zon": "F", "Multi": "M1", "Ursprungsdatum": "2026-05-17"},
        # H2 ligger FÖRE H1 i radordningen -> en positionell felinriktning syns.
        {"Ordernr": "H2", "Ordertyp": "HIB", "Kund nr": "K1", "Orderdatum": "2026-05-12",
         "Sändningsnr": "S9", "Zon": "F", "Multi": "M2", "Ursprungsdatum": _today("%Y-%m-%d")},
        {"Ordernr": "H1", "Ordertyp": "HIB", "Kund nr": "K1", "Orderdatum": "2026-05-12",
         "Sändningsnr": "S9", "Zon": "F", "Multi": "M1", "Ursprungsdatum": "2026-05-17"},
    ])
    details = _details([
        {"Order nr": "N1", "Status": "10", "Zon": "F", "Kund.1": "Butik A"},
        {"Order nr": "H1", "Status": "10", "Zon": "F", "Kund.1": "Butik A"},
        {"Order nr": "H2", "Status": "10", "Zon": "F", "Kund.1": "Butik A"},
    ])
    bred = _widen(smal, seed=11)

    origin = _OriginToday(_normaliserad_ov(bred))
    assert origin._today_hib is not None, "homogen ISO-kolumn ska ta snabbvägen"
    assert origin._today_hib.tolist() == [False, True, False], (
        "today-origin-flaggan hamnade på fel rad i den breda ramen"
    )
    # Flaggan ska överleva projektionen och landa på samma rader.
    flaggad = origin.attach(_project(_normaliserad_ov(bred), _HIB_LOOP_COLS))
    assert flaggad.loc[flaggad[_TODAY_ORIGIN_COL], "Ordernr"].tolist() == ["H2"]

    got = compute_hib_koppling(details, bred)
    _assert_same(got, _ref_compute_hib_koppling(details, bred), "hib-koppling bred + today-origin")
    assert "H2" not in set(got["ordernummer"]), "HIB med dagens Ursprungsdatum kom med på bred ram"
    assert "H1" in set(got["ordernummer"])


# ---------------------------------------------------------------------------
# 6. NaN-semantiken: store_ship_mask (astype(str)) vs store_date_str (str(v))
# ---------------------------------------------------------------------------
# hib.py bygger två listor ur samma butiksram med AVSIKTLIGT olika idiom:
#
#   store_ship_mask = store_df["Sändningsnr"].astype(str).str.strip().tolist()
#   store_date_str  = [str(v).strip() for v in store_df["Orderdatum"].tolist()]
#
# I pandas 3 BEHÅLLER `.astype(str)` NaN som NaN, medan `str(nan)` ger strängen
# "nan". Det är precis skillnaden mellan den gamla bool-maskens semantik och den
# gamla iterrows-loopens semantik. Skrivs den ena raden om till den andras idiom
# ändras ANVÄNDARSYNLIG utdata - och det skyddades tidigare bara av en kodkommentar.

def test_nan_sandningsnr_matchar_inte_hib_ordens_nan_strang():
    """Butiksorder med NaN Sändningsnr får INTE matcha en HIB-order med NaN.

    HIB-sidan ser `str(nan).strip()` == "nan". Butiksmasken byggs med
    `.astype(str)`, som bevarar NaN -> jämförelsen blir False -> ingen matchning ->
    fallback-butiken (äldst orderdatum) används. Byter man butiksmaskens idiom till
    `str(v)` blir masken "nan" == "nan" -> butiken matchar -> HIB-ordern anses redan
    korrekt och FÖRSVINNER ur Ändringar-tabellen.

    Muterat (`store_ship_mask = [str(v).strip() for v in ...]`) ger 0 rader i stället
    för 1. De två listorna är avsiktligt olika och får inte slås ihop.
    """
    overview = _overview([
        # N1: NaN Sändningsnr, NYARE orderdatum -> aldrig fallback-butiken.
        {"Ordernr": "N1", "Ordertyp": "N", "Kund nr": "K1", "Orderdatum": "2026-05-20",
         "Sändningsnr": None, "Zon": "F", "Multi": "M1", "Ursprungsdatum": "2026-05-17"},
        # N2: giltigt Sändningsnr och ÄLDST orderdatum -> fallback-butiken.
        {"Ordernr": "N2", "Ordertyp": "N", "Kund nr": "K1", "Orderdatum": "2026-05-10",
         "Sändningsnr": "S2", "Zon": "F", "Multi": "M1", "Ursprungsdatum": "2026-05-17"},
        # H1: NaN Sändningsnr -> cur_ship blir strängen "nan".
        {"Ordernr": "H1", "Ordertyp": "HIB", "Kund nr": "K1", "Orderdatum": "2026-05-20",
         "Sändningsnr": None, "Zon": "F", "Multi": "M1", "Ursprungsdatum": "2026-05-17"},
    ])
    details = _details([
        {"Order nr": "N1", "Status": "10", "Zon": "F", "Kund.1": "Butik A"},
        {"Order nr": "N2", "Status": "10", "Zon": "F", "Kund.1": "Butik A"},
        {"Order nr": "H1", "Status": "10", "Zon": "F", "Kund.1": "Butik A"},
    ])

    # Förutsättningen som gör fallet skarpt: de två idiomen skiljer sig faktiskt.
    # Håller inte detta (t.ex. efter en pandas-uppgradering) är hela invarianten
    # en annan och koden i hib.py måste omprövas - inte testet lappas.
    ships = overview.loc[overview["Ordertyp"] == "N", "Sändningsnr"]
    mask_idiom = ships.astype(str).str.strip().tolist()[0]
    loop_idiom = [str(v).strip() for v in ships.tolist()][0]
    assert pd.isna(mask_idiom), "astype(str) bevarar inte längre NaN - invarianten i hib.py gäller inte"
    assert loop_idiom == "nan"

    got = compute_hib_koppling(details, overview)
    _assert_same(got, _ref_compute_hib_koppling(details, overview), "hib-koppling NaN-sändningsnr")

    assert len(got) == 1, (
        "HIB-ordern försvann ur Ändringar - butiksmasken har troligen bytt till "
        "str(v)-idiomet och låter NaN matcha strängen \"nan\""
    )
    assert got.iloc[0]["ordernummer"] == "H1"
    assert got.iloc[0]["sändningsnummer"] == "S2", (
        "fel butiksorder valdes som referens - NaN-semantiken i store_ship_mask är bruten"
    )
    assert got.iloc[0]["Orderdatum"] == "2026-05-10"


def test_nan_sandningsnr_raknas_som_butikssandning_i_missade_avgangar():
    """Spegelbilden i compute_missed_departures: där är str(nan) -> "nan" AVSIKTLIGT.

    `store_ships` byggs med loop-semantik (`str(v).strip()`), så en butiksorder med
    NaN Sändningsnr bidrar med strängen "nan" - sanningsvärd, och därmed med i
    mängden precis som i den gamla iterrows-koden. En HIB-order med NaN Sändningsnr
    får cur_ship == "nan", hittar den i mängden och är alltså INTE en missad avgång.

    Byter man till `.astype(str)`-idiomet hamnar NaN (inte "nan") i mängden,
    `"nan" in store_ships` blir False och H1 rapporteras felaktigt som MISSAT SIN
    AVGÅNG. Muterat: 1 rad i stället för 0.
    """
    overview = _overview([
        {"Ordernr": "N1", "Ordertyp": "N", "Kund nr": "K1", "Orderdatum": "2026-05-20",
         "Sändningsnr": None, "Zon": "F", "Multi": "M1", "Ursprungsdatum": "2026-05-17"},
        {"Ordernr": "H1", "Ordertyp": "HIB", "Kund nr": "K1", "Orderdatum": "2026-05-20",
         "Sändningsnr": None, "Zon": "F", "Multi": "M1", "Ursprungsdatum": "2026-05-17"},
    ])
    details = _details([
        {"Order nr": "N1", "Status": "10", "Zon": "F", "Kund.1": "Butik A"},
        {"Order nr": "H1", "Status": "40", "Zon": "F", "Kund.1": "Butik A"},  # > 34
    ])

    got = compute_missed_departures(details, overview)
    _assert_same(got, _ref_compute_missed_departures(details, overview), "missade avgångar NaN-sändningsnr")
    assert got.empty, (
        "H1 rapporterades som missad avgång - store_ships har troligen bytt till "
        "astype(str)-idiomet, så NaN inte längre blir strängen \"nan\""
    )

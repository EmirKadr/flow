"""Bygg träningsdata: features per sändning från orderdetaljer + label från dispatch.

Bryggan ordernr → sändningsnr går via plocklog (Plockpallsnr) → dispatch (Plockpallsnr.).
"""
from pathlib import Path
import os
import re
import pandas as pd
import numpy as np

DATA = Path(__file__).parent / "data"
DATA_FORE = DATA / "Före"   # input vid förprognos (det vi får använda)
DATA_EFTER = DATA / "Efter"  # facit (label + bridge - bara för training)
TRAINING_CACHE = Path(__file__).parent / "training.parquet"
USE_TRAINING_CACHE_ENV = "MESTERGRUPPEN_USE_TRAINING_CACHE"
EXCLUDE_CUSTOMERS = {"40002", "90002"}

# Palltyp -> pallplatser (dispatch-sidans Palltyp som heltalskod)
# Hur dispatchpallar översätts till antal pallplatser i fordonet.
PALLTYP_TO_PALLPLATSER = {
    "8": 0.5,   # MG HALVPALL
    "15": 0.5,  # GG HALVPALL
    "11": 1.0,  # EUROPALL B
    "27": 1.0,  # ENGÅNG / Ej Godkänd
    "28": 1.0,  # BYGGPALL
    "35": 1.0,  # Skrymmepall 1.4m
    "34": 2.0,  # Skrymmepall 2.2m
    # 0/saknas = kartonger, paket, vagn = inte pallplats
}

_HEIGHT_RE_CM = re.compile(r"(?:max\s*)?(\d{2,3})\s*cm", re.IGNORECASE)
_HEIGHT_RE_M = re.compile(r"(\d[,.]\d{1,2})\s*m\b", re.IGNORECASE)


def _training_source_paths() -> list[Path]:
    paths = [Path(__file__)]
    paths.extend(sorted(DATA_FORE.glob("*.csv")))
    paths.extend(sorted(DATA_EFTER.glob("*.csv")))
    return paths


def _training_cache_is_fresh() -> bool:
    return TRAINING_CACHE.exists()


def _extract_height_cm(text: object) -> float | None:
    """Plocka ut max-höjd i cm från kund-fritext som 'Bygg på höjden Max 180 cm'."""
    if not isinstance(text, str):
        return None
    m = _HEIGHT_RE_CM.search(text)
    if m:
        return float(m.group(1))
    m = _HEIGHT_RE_M.search(text)
    if m:
        return float(m.group(1).replace(",", ".")) * 100
    return None


def _filter_mg(df: pd.DataFrame, kund_col: str) -> pd.DataFrame:
    df = df[df["Bolag"] == "MG"].copy()
    df = df[~df[kund_col].astype(str).str.strip().isin(EXCLUDE_CUSTOMERS)]
    return df


def _to_num(s: pd.Series) -> pd.Series:
    """Konvertera svensk-formaterad numerisk sträng (komma som decimal) till float."""
    return pd.to_numeric(s.astype(str).str.replace(",", ".", regex=False), errors="coerce").fillna(0)


def _extract_postnr_digits(s: pd.Series) -> pd.Series:
    """Keep only digits from postal-code style strings."""
    digits = s.fillna("").astype(str).str.replace(r"\D+", "", regex=True)
    return digits.where(digits.ne(""), "")


def _postnr_prefix(s: pd.Series, width: int) -> pd.Series:
    digits = _extract_postnr_digits(s)
    prefix = digits.where(digits.str.len() >= width, "").str[:width]
    return pd.to_numeric(prefix, errors="coerce").fillna(0.0)


def _clean_transportor(s: pd.Series) -> pd.Series:
    """Plocka ut transportörnamnet från 'Freja Örebro - 09:00 - Stycke' -> 'Freja Örebro'."""
    return s.astype(str).str.split(" - ").str[0].str.strip()


def load_orders() -> pd.DataFrame:
    """Ladda 24 dags-snapshots av orderdetaljer och dedupe på (Order nr, Rad).

    OBS: snapshots staplas - samma orderrad kan förekomma i flera filer (skapad
    13 mars, syns i alla snapshots tills plockad). Utan dedupe blir features
    (sum/count) systematiskt inflaterade vs label från dispatch (engångshändelse).
    Behåller SENASTE snapshot per orderrad (mest aktuella status).
    """
    files = sorted(DATA_FORE.glob("v_ask_customer_order_details_all-*.csv"))
    parts = []
    for f in files:
        df = pd.read_csv(f, sep="\t", encoding="utf-8-sig", dtype=str, low_memory=False)
        df["__src"] = f.name  # filename innehåller timestamp - sort-nyckel
        parts.append(df)
    df = pd.concat(parts, ignore_index=True)
    df = _filter_mg(df, "Kund")
    # Dedupe: samma (Order nr, Rad) = samma orderrad, behåll senaste snapshot
    df = df.sort_values(["Order nr", "Rad", "__src"], na_position="last")
    df = df.drop_duplicates(["Order nr", "Rad"], keep="last")
    df = df.drop(columns=["__src"])
    df["Beställt"] = _to_num(df["Beställt"])
    return df


def load_dispatch() -> pd.DataFrame:
    f = next(DATA_EFTER.glob("v_ask_dispatch_pallet-*.csv"))
    df = pd.read_csv(f, sep="\t", encoding="utf-8-sig", dtype=str, low_memory=False)
    df = _filter_mg(df, "Kundnr.")
    for col in ("Flakmeter", "Vikt", "Kolli", "Rader", "Bredd", "Längd", "Höjd"):
        df[col] = _to_num(df[col])
    df["transportor"] = _clean_transportor(df["Transportör"])
    df["staplingsbar_yn"] = df["Staplingsbar"].astype(str).str.upper().eq("Y")
    df["pallplatser"] = df["Palltyp"].astype(str).str.strip().map(PALLTYP_TO_PALLPLATSER).fillna(0.0)
    return df


def load_picklog() -> pd.DataFrame:
    f = next(DATA_EFTER.glob("v_ask_pick_log_full-*.csv"))
    df = pd.read_csv(f, sep="\t", encoding="utf-8-sig", dtype=str, low_memory=False)
    return _filter_mg(df, "Kundnr")


def load_order_overview() -> pd.DataFrame:
    """Order-huvud: ger Transportör, Ordertyp, Sändningsnr, Multi per Ordernr.

    Detta finns vid förprognos-tid (orderhuvudet skapas före plock) → ingen leakage.
    Filtrerar Bolag=MG, exkl 40002/90002, och Ordertyp=HIB.
    Dedupar på Ordernr (senaste snapshot vinner).
    """
    files = sorted(DATA_FORE.glob("v_ask_order_overview-*.csv"))
    if not files:
        return pd.DataFrame(columns=["Ordernr", "order_transportor", "order_typ"])
    parts = []
    for f in files:
        df = pd.read_csv(f, sep="\t", encoding="utf-8-sig", dtype=str, low_memory=False)
        df["__src"] = f.name
        parts.append(df)
    df = pd.concat(parts, ignore_index=True)
    df = df[df["Bolag"] == "MG"]
    df = df[~df["Kund nr"].astype(str).str.strip().isin(EXCLUDE_CUSTOMERS)]
    # Ordertyp-filter: HIB exkluderas (intern hanteringstyp - inte vanliga kundorder)
    df = df[df["Ordertyp"].astype(str).str.strip().str.upper() != "HIB"]
    df = df.sort_values(["Ordernr", "__src"]).drop_duplicates("Ordernr", keep="last")
    sandningsnr = df["Sändningsnr"].fillna("").astype(str).str.strip()
    multi_raw = df["Multi"].fillna("").astype(str).str.strip()
    multi_key = multi_raw.where(multi_raw.ne(""), sandningsnr)
    multi_counts = multi_key[multi_key.ne("")].value_counts()
    multi_size = multi_key.map(multi_counts).fillna(1.0)
    out = pd.DataFrame({
        "Ordernr": df["Ordernr"],
        "order_transportor": _clean_transportor(df["Transportör"]),
        "order_sandningsnr": df["Sändningsnr"],
        "order_typ": df["Ordertyp"],
        "order_multi": multi_size.gt(1),
        "order_multi_size": multi_size.astype(float),
        "order_volym_huvud": _to_num(df["Volym"]),
        "order_vikt_huvud": _to_num(df["Vikt"]),
        "order_antal_huvud": _to_num(df["Antal"]),
        "order_rader_huvud": _to_num(df["Rader"]),
    })
    return out


def load_items() -> pd.DataFrame:
    """Item-master: per artikel + palltyp-master för fysisk pall-/flakmeter-signal."""
    files = sorted(DATA_FORE.glob("item-*.csv"))
    if not files:
        return pd.DataFrame(
            columns=[
                "Artikel",
                "per_pall",
                "vikt_brutto",
                "volym",
                "item_palltyp",
                "item_robot",
                "item_staplingsbar",
                "item_pack_klass",
                "item_pall_flakmeter",
                "item_pall_langd",
                "item_pall_bredd",
                "item_pall_hojd",
                "item_pall_langgods",
                "item_pall_extra_lang",
            ]
        )
    df = pd.read_csv(files[-1], sep="\t", encoding="utf-8-sig", dtype=str, low_memory=False)
    df = df[df["Bolag"] == "MG"].copy()
    out = pd.DataFrame({
        "Artikel": df["Artikel"],
        "per_pall": _to_num(df["Per pall"]),
        "vikt_brutto": _to_num(df["Vikt brutto"]),
        "volym": _to_num(df["Volym"]),
        "item_palltyp": df["Palltyp"].fillna("").astype(str).str.strip().str.upper(),
        "item_robot": df["Robot"].astype(str).str.upper().isin(["Y", "TRUE", "1"]),
        "item_staplingsbar": df["Staplingsbar"].astype(str).str.upper().isin(["Y", "TRUE", "1"]),
        "item_pack_klass": df["Pack klass"].fillna(""),
    })
    out = out.drop_duplicates("Artikel")
    return out.merge(load_pallet_types(), on="item_palltyp", how="left")


def load_dimension_master() -> pd.DataFrame:
    """Dimensionsregister: längd/bredd/höjd per dimension-id."""
    files = sorted(DATA_FORE.glob("dimension-*.csv"))
    if not files:
        return pd.DataFrame(columns=["dimension_id", "palltype_langd", "palltype_bredd", "palltype_hojd"])
    df = pd.read_csv(files[-1], sep="\t", encoding="utf-8-sig", dtype=str, low_memory=False)
    out = pd.DataFrame({
        "dimension_id": df["Dimension Id"].fillna("").astype(str).str.strip(),
        "palltype_langd": _to_num(df["Längd"]),
        "palltype_bredd": _to_num(df["Bredd"]),
        "palltype_hojd": _to_num(df["Höjd"]),
    })
    return out.drop_duplicates("dimension_id")


def load_pallet_types() -> pd.DataFrame:
    """Palltyp-master: flakmeter och fysiska mått per palltyp."""
    files = sorted(DATA_FORE.glob("pallet_type-*.csv"))
    if not files:
        return pd.DataFrame(
            columns=[
                "item_palltyp",
                "item_pall_flakmeter",
                "item_pall_langd",
                "item_pall_bredd",
                "item_pall_hojd",
                "item_pall_langgods",
                "item_pall_extra_lang",
            ]
        )
    df = pd.read_csv(files[-1], sep="\t", encoding="utf-8-sig", dtype=str, low_memory=False)
    out = pd.DataFrame({
        "palltyp_id": df["Palltyp"].fillna("").astype(str).str.strip().str.upper(),
        "lookup_key": df["Inköpstyp"].fillna("").astype(str).str.strip().str.upper(),
        "dimension_id": df["Dimension"].fillna("").astype(str).str.strip(),
        "item_pall_flakmeter": _to_num(df["Flakmeter"]),
        "item_pall_master_hojd": _to_num(df["Höjd"]),
    })
    out = out.merge(load_dimension_master(), on="dimension_id", how="left")
    out["item_pall_langd"] = out["palltype_langd"].fillna(0)
    out["item_pall_bredd"] = out["palltype_bredd"].fillna(0)
    out["item_pall_hojd"] = out["palltype_hojd"].where(
        out["palltype_hojd"].fillna(0) > 0,
        out["item_pall_master_hojd"].fillna(0),
    )
    out["item_pall_langgods"] = out["item_pall_langd"] >= 140
    out["item_pall_extra_lang"] = out["item_pall_langd"] >= 220
    key_frames = []
    text_rows = out[out["lookup_key"].ne("")].copy()
    if not text_rows.empty:
        text_rows["item_palltyp"] = text_rows["lookup_key"]
        key_frames.append(text_rows)
    id_rows = out[out["palltyp_id"].ne("")].copy()
    if not id_rows.empty:
        id_rows["item_palltyp"] = id_rows["palltyp_id"]
        key_frames.append(id_rows)

    # Historiska item-exporter använder ibland kortkoden "E" för engångspall.
    engangs_alias = out[out["lookup_key"].eq("EIG")].copy()
    if not engangs_alias.empty:
        engangs_alias["item_palltyp"] = "E"
        key_frames.append(engangs_alias)

    keyed = pd.concat(key_frames, ignore_index=True) if key_frames else out.assign(item_palltyp="")
    return keyed[
        [
            "item_palltyp",
            "item_pall_flakmeter",
            "item_pall_langd",
            "item_pall_bredd",
            "item_pall_hojd",
            "item_pall_langgods",
            "item_pall_extra_lang",
        ]
    ].drop_duplicates("item_palltyp")


def load_item_dimensions() -> pd.DataFrame:
    """Item-alias dimensioner per artikel (Längd, Bredd, Höjd). Kan vara glest ifyllt."""
    files = sorted(DATA_FORE.glob("item_alias-*.csv"))
    if not files:
        return pd.DataFrame(columns=["Artikel", "art_langd", "art_bredd", "art_hojd"])
    df = pd.read_csv(files[-1], sep="\t", encoding="utf-8-sig", dtype=str, low_memory=False)
    df = df[df["Bolag"] == "MG"].copy()
    df["art_langd"] = _to_num(df["Längd"])
    df["art_bredd"] = _to_num(df["Bredd"])
    df["art_hojd"] = _to_num(df["Höjd"])
    # Många rader har NaN dimensioner - ta största per artikel
    return (df.groupby("Artikel")[["art_langd", "art_bredd", "art_hojd"]].max().reset_index())


def load_item_options() -> pd.DataFrame:
    """Item-options: artikelregler. Mest värdefullt: Ej staplingsbar + Helpalls avvikelse %."""
    files = sorted(DATA_FORE.glob("item_option-*.csv"))
    if not files:
        return pd.DataFrame(columns=["Artikel", "opt_ej_staplingsbar", "opt_helpalls_avvikelse_pct", "opt_plockzon"])
    df = pd.read_csv(files[-1], sep="\t", encoding="utf-8-sig", dtype=str, low_memory=False)
    df = df[df["Bolag"] == "MG"].copy()
    out = pd.DataFrame({
        "Artikel": df["Artikel"],
        "opt_ej_staplingsbar": df["Ej staplingsbar"].astype(str).str.upper().isin(["Y", "TRUE", "1"]),
        "opt_helpalls_avvikelse_pct": _to_num(df["Helpalls avvikelse %"]),
        "opt_plockzon": df["Plockzon"].fillna(""),
        "opt_robot": df["Automatiserat robotplock"].astype(str).str.upper().isin(["Y", "TRUE", "1"]),
    })
    return out.drop_duplicates("Artikel")


def load_buffert_pallets() -> pd.DataFrame:
    """Buffertpallar: hur många hela pallar finns per artikel i bufferten."""
    files = sorted(DATA_FORE.glob("v_ask_article_buffertpallet-*.csv"))
    if not files:
        return pd.DataFrame(columns=["Artikel", "buffert_n_pallar", "buffert_total_antal"])
    df = pd.read_csv(files[-1], sep="\t", encoding="utf-8-sig", dtype=str, low_memory=False)
    df = df[df["Bolag"] == "MG"].copy()
    df["Antal"] = _to_num(df["Antal"])
    return df.groupby("Artikel").agg(
        buffert_n_pallar=("Pallid", "nunique"),
        buffert_total_antal=("Antal", "sum"),
    ).reset_index()


def load_customers() -> pd.DataFrame:
    """Kundmaster med max-höjd. Höjd tas i prioritetsordning:
    Pallhöjd (numerisk) > Mellanpalls höjd (numerisk) > regex på Pack instr-fritext."""
    files = sorted(DATA_FORE.glob("custom-*.csv"))
    if not files:
        return pd.DataFrame(
            columns=[
                "Kund",
                "kund_max_hojd",
                "kund_postnr_prefix2",
                "kund_postnr_prefix3",
                "kund_postnr_missing",
                "kund_is_foreign",
                "kund_standard_transportornr",
                "kund_has_standard_transportor",
                "kund_requires_lift",
                "kund_special_delivery_text",
            ]
        )
    df = pd.read_csv(files[-1], sep="\t", encoding="utf-8-sig", dtype=str, low_memory=False)
    df = df[df["Bolag"] == "MG"].copy()
    pall = pd.to_numeric(df["Pallhöjd"], errors="coerce")
    mell = pd.to_numeric(df["Mellanpalls höjd"], errors="coerce")
    text = df["Pack instr"].apply(_extract_height_cm)
    land = df["Land"].fillna("").astype(str).str.strip().str.upper()
    postnr = df["Post nr"]
    leverans_text = df["Leverans text"].fillna("").astype(str).str.strip().str.lower()
    standard_transportor = pd.to_numeric(df["Standard Transportörsnr"], errors="coerce").fillna(0)
    df["kund_max_hojd"] = pall.where(pall > 0).fillna(mell.where(mell > 0)).fillna(text)
    df["kund_postnr_prefix2"] = _postnr_prefix(postnr, 2)
    df["kund_postnr_prefix3"] = _postnr_prefix(postnr, 3)
    df["kund_postnr_missing"] = _extract_postnr_digits(postnr).eq("").astype(float)
    df["kund_is_foreign"] = (~land.isin(["", "SE", "SWE", "SVERIGE"])).astype(float)
    df["kund_standard_transportornr"] = standard_transportor.astype(float)
    df["kund_has_standard_transportor"] = (standard_transportor > 0).astype(float)
    df["kund_requires_lift"] = leverans_text.str.contains("lift", regex=False).astype(float)
    df["kund_special_delivery_text"] = leverans_text.ne("").astype(float)
    return df[
        [
            "Kund",
            "kund_max_hojd",
            "kund_postnr_prefix2",
            "kund_postnr_prefix3",
            "kund_postnr_missing",
            "kund_is_foreign",
            "kund_standard_transportornr",
            "kund_has_standard_transportor",
            "kund_requires_lift",
            "kund_special_delivery_text",
        ]
    ].drop_duplicates("Kund")


def build_order_to_pall(picklog: pd.DataFrame) -> pd.DataFrame:
    """Mappa Ordernr -> Plockpallsnr via plocklog. En order kan hamna i flera pallar."""
    return picklog[["Ordernr", "Plockpallsnr"]].dropna().drop_duplicates()


def build_training_data() -> pd.DataFrame:
    """Bygg training-data per (Kund, Orderdatum)-grupp - inte per Sändning.

    Multi-regel: alla ordrar med samma kundnr+orderdatum slås ihop på plock.
    Gruppen är vår prediktionsenhet. Label = total pallplatser för pallar som
    innehåller ordrar från gruppen (delade pallar attribueras till varje grupp).
    """
    use_cache = os.environ.get(USE_TRAINING_CACHE_ENV, "").strip().lower() in {"1", "true", "yes"}
    if use_cache and _training_cache_is_fresh():
        return pd.read_parquet(TRAINING_CACHE)

    orders = load_orders()
    dispatch = load_dispatch()
    picklog = load_picklog()
    customers = load_customers()
    items = load_items()
    dims = load_item_dimensions()
    item_opts = load_item_options()
    buffert = load_buffert_pallets()
    order_overview = load_order_overview()

    order_to_pall = build_order_to_pall(picklog)

    orders = orders.rename(columns={"Order nr": "Ordernr"})

    # HIB-filter via inner join på order_overview (HIB är redan filtrerat där)
    orders = orders.merge(order_overview, on="Ordernr", how="inner")

    # Definiera gruppen - kund+orderdatum
    orders["grupp"] = orders["Kund"].astype(str).str.strip() + "+" + orders["Orderdatum"].astype(str).str.strip()

    # Order-radens Robot-kolumn är ofta tom i MG-exporten, så item-master
    # används som huvudsignal med råflaggor som extra override.
    orders["is_robot_raw"] = orders["Robot"].astype(str).str.upper().isin(["Y", "TRUE", "1"])

    # Kund-master och item-master in på orderrad-nivå
    orders = orders.merge(customers, on="Kund", how="left")
    orders = orders.merge(items, on="Artikel", how="left")
    orders = orders.merge(dims, on="Artikel", how="left")
    orders = orders.merge(item_opts, on="Artikel", how="left")
    orders = orders.merge(buffert, on="Artikel", how="left")
    orders["is_robot"] = (
        orders["is_robot_raw"].fillna(False)
        | orders["item_robot"].fillna(False)
        | orders["opt_robot"].fillna(False)
    )
    orders["bestallt_robot"] = orders["Beställt"] * orders["is_robot"].astype(int)
    orders["bestallt_manual"] = orders["Beställt"] - orders["bestallt_robot"]

    # Per-rad estimat
    orders["pall_estimate_rad"] = (orders["Beställt"] / orders["per_pall"].replace(0, pd.NA)).fillna(0)
    orders["rad_vikt"] = orders["Beställt"] * orders["vikt_brutto"]
    orders["rad_volym"] = orders["Beställt"] * orders["volym"]
    orders["effective_langd"] = orders[["art_langd", "item_pall_langd"]].fillna(0).max(axis=1)
    orders["is_skrymmande"] = orders["effective_langd"] > 140
    orders["is_staplingsbar"] = orders["item_staplingsbar"].fillna(False)
    # opt_ej_staplingsbar är mer auktoritärt än item_staplingsbar
    orders["is_ej_staplingsbar"] = orders["opt_ej_staplingsbar"].fillna(False)
    orders["item_pall_langgods"] = orders["item_pall_langgods"].fillna(False)
    orders["item_pall_extra_lang"] = orders["item_pall_extra_lang"].fillna(False)
    orders["palltype_flakmeter_est_rad"] = orders["pall_estimate_rad"] * orders["item_pall_flakmeter"].fillna(0)
    orders["longpall_estimate_rad"] = orders["pall_estimate_rad"] * orders["item_pall_langgods"].astype(int)
    orders["extra_lang_pall_estimate_rad"] = orders["pall_estimate_rad"] * orders["item_pall_extra_lang"].astype(int)
    orders["bestallt_x_helpalls_avvik"] = orders["Beställt"] * orders["opt_helpalls_avvikelse_pct"].fillna(0) / 100
    # Buffert-coverage: kan denna orderrad uppfyllas från buffert?
    orders["buffert_coverage_ratio"] = (
        orders["buffert_total_antal"].fillna(0) / orders["Beställt"].replace(0, pd.NA)
    ).fillna(0).clip(upper=10)  # cap för outliers

    # Status-flaggor (30 = ej plockad än, 32-38 = plockade i olika faser)
    s = orders["Status"].astype(str).str.strip()
    orders["status_30"] = s.eq("30")
    orders["status_35"] = s.eq("35")
    orders["status_other_picked"] = s.isin(["32", "33", "34", "36", "37", "38"])
    orders["is_ar_plockad"] = orders["Är plockad"].astype(str).str.strip().eq("1")

    # Aggregera features per grupp (Kund+Orderdatum)
    feats = orders.groupby("grupp").agg(
        kund=("Kund", "first"),
        orderdatum=("Orderdatum", "first"),
        n_rader=("Ordernr", "size"),
        n_ordrar=("Ordernr", "nunique"),
        n_artiklar=("Artikel", "nunique"),
        sum_bestallt=("Beställt", "sum"),
        sum_bestallt_robot=("bestallt_robot", "sum"),
        sum_bestallt_manual=("bestallt_manual", "sum"),
        n_robot_rader=("is_robot", "sum"),
        n_zoner=("Zon", "nunique"),
        n_packklasser=("Pack klass", "nunique"),
        kund_max_hojd=("kund_max_hojd", "first"),
        kund_postnr_prefix2=("kund_postnr_prefix2", "first"),
        kund_postnr_prefix3=("kund_postnr_prefix3", "first"),
        kund_postnr_missing=("kund_postnr_missing", "first"),
        kund_is_foreign=("kund_is_foreign", "first"),
        kund_standard_transportornr=("kund_standard_transportornr", "first"),
        kund_has_standard_transportor=("kund_has_standard_transportor", "first"),
        kund_requires_lift=("kund_requires_lift", "first"),
        kund_special_delivery_text=("kund_special_delivery_text", "first"),
        pall_estimate=("pall_estimate_rad", "sum"),
        sum_vikt_brutto=("rad_vikt", "sum"),
        sum_volym=("rad_volym", "sum"),
        n_skrymmande_rader=("is_skrymmande", "sum"),
        n_staplingsbara_rader=("is_staplingsbar", "sum"),
        n_unika_palltyper=("item_palltyp", "nunique"),
        max_art_langd=("art_langd", "max"),
        max_art_hojd=("art_hojd", "max"),
        sum_palltype_flakmeter_est=("palltype_flakmeter_est_rad", "sum"),
        n_langpall_rader=("item_pall_langgods", "sum"),
        n_extra_langa_pallrader=("item_pall_extra_lang", "sum"),
        sum_langpall_estimate=("longpall_estimate_rad", "sum"),
        sum_extra_langa_pall_estimate=("extra_lang_pall_estimate_rad", "sum"),
        max_palltype_langd=("item_pall_langd", "max"),
        # Från order_overview (huvudnivå - mer auktoritärt än orderrad-aggregat)
        order_volym_huvud=("order_volym_huvud", "sum"),
        order_vikt_huvud=("order_vikt_huvud", "sum"),
        order_antal_huvud=("order_antal_huvud", "sum"),
        order_rader_huvud=("order_rader_huvud", "sum"),
        n_multi_huvud=("order_multi", "sum"),
        avg_multi_size_huvud=("order_multi_size", "mean"),
        max_multi_size_huvud=("order_multi_size", "max"),
        # item_option-features
        n_ej_staplingsbara=("is_ej_staplingsbar", "sum"),
        sum_helpalls_avvik=("bestallt_x_helpalls_avvik", "sum"),
        # buffertpallet-features
        avg_buffert_coverage=("buffert_coverage_ratio", "mean"),
        max_buffert_coverage=("buffert_coverage_ratio", "max"),
        n_artiklar_med_buffert=("buffert_n_pallar", lambda s: (s.fillna(0) > 0).sum()),
        # status-features (kan indikera plock-progress vid förprognos-tid)
        n_status_30=("status_30", "sum"),
        n_status_35=("status_35", "sum"),
        n_status_other_picked=("status_other_picked", "sum"),
        n_ar_plockad=("is_ar_plockad", "sum"),
    ).reset_index()
    feats["kund_max_hojd"] = feats["kund_max_hojd"].fillna(280)
    feats["kund_postnr_prefix2"] = feats["kund_postnr_prefix2"].fillna(0)
    feats["kund_postnr_prefix3"] = feats["kund_postnr_prefix3"].fillna(0)
    feats["kund_postnr_missing"] = feats["kund_postnr_missing"].fillna(1.0)
    feats["kund_is_foreign"] = feats["kund_is_foreign"].fillna(0.0)
    feats["kund_standard_transportornr"] = feats["kund_standard_transportornr"].fillna(0.0)
    feats["kund_has_standard_transportor"] = feats["kund_has_standard_transportor"].fillna(0.0)
    feats["kund_requires_lift"] = feats["kund_requires_lift"].fillna(0.0)
    feats["kund_special_delivery_text"] = feats["kund_special_delivery_text"].fillna(0.0)
    feats["max_art_langd"] = feats["max_art_langd"].fillna(0)
    feats["max_art_hojd"] = feats["max_art_hojd"].fillna(0)
    feats["max_palltype_langd"] = feats["max_palltype_langd"].fillna(0)

    # Bridge: grupp -> alla pallar som innehåller ordrar från gruppen
    orders_grupp = orders[["grupp", "Ordernr"]].drop_duplicates()
    grupp_to_pall_raw = orders_grupp.merge(order_to_pall, on="Ordernr", how="inner")

    # Datahygien: dropp grupper där NÅGON order saknar plocklog-match
    # (annars blir labelen felaktigt låg eftersom bara plockade ordrar bidrar till pallar)
    matched_orders = set(order_to_pall["Ordernr"])
    rena_grupper = (
        orders_grupp.groupby("grupp")["Ordernr"]
        .apply(lambda s: all(o in matched_orders for o in s))
    )
    rena_grupper = set(rena_grupper[rena_grupper].index)
    grupp_to_pall = grupp_to_pall_raw[grupp_to_pall_raw["grupp"].isin(rena_grupper)]
    grupp_to_pall = grupp_to_pall[["grupp", "Plockpallsnr"]].drop_duplicates()

    # Pall-info från dispatch (pallplatser per pall + dominant transportör)
    pall_info = dispatch[["Plockpallsnr.", "pallplatser", "transportor"]].rename(
        columns={"Plockpallsnr.": "Plockpallsnr"}
    )

    grupp_pallar = grupp_to_pall.merge(pall_info, on="Plockpallsnr", how="inner")

    # Label per grupp: summa pallplatser (delade pallar attribueras till varje grupp)
    # + dominant transportör
    label = grupp_pallar.groupby("grupp").agg(
        pallplatser=("pallplatser", "sum"),
        n_pallar=("Plockpallsnr", "nunique"),
    ).reset_index()

    # Transportör HÄMTAS FRÅN ORDER-SIDAN (order_overview), inte dispatch.
    # Dispatch.transportör är data leakage (inte tillgänglig vid förprognos).
    transportor = (
        orders.groupby(["grupp", "order_transportor"]).size().reset_index(name="n")
        .sort_values(["grupp", "n"], ascending=[True, False])
        .drop_duplicates("grupp")[["grupp", "order_transportor"]]
        .rename(columns={"order_transportor": "transportor"})
    )

    # Stöd-features från dispatch (label-only)
    dispatch_with_grupp = grupp_to_pall.merge(
        dispatch[["Plockpallsnr.", "Flakmeter", "Vikt", "Höjd"]].rename(columns={"Plockpallsnr.": "Plockpallsnr"}),
        on="Plockpallsnr", how="inner"
    )
    extra_label = dispatch_with_grupp.groupby("grupp").agg(
        flakmeter=("Flakmeter", "sum"),
        sum_vikt=("Vikt", "sum"),
        max_pall_hojd=("Höjd", "max"),
    ).reset_index()

    df = feats.merge(transportor, on="grupp", how="left")
    df = df.merge(label, on="grupp", how="inner")
    df = df.merge(extra_label, on="grupp", how="left")

    # orderdatum till datetime så LLM kan använda .dt.dayofweek etc. direkt
    df["orderdatum"] = pd.to_datetime(df["orderdatum"], errors="coerce")

    # Säkerställ float-dtype på alla numeriska kolumner (annars havererar np.log1p mm.)
    num_cols = ["n_rader", "n_ordrar", "n_artiklar", "sum_bestallt", "sum_bestallt_robot",
                "sum_bestallt_manual", "n_robot_rader", "n_zoner", "n_packklasser",
                "kund_max_hojd", "kund_postnr_prefix2", "kund_postnr_prefix3",
                "kund_postnr_missing", "kund_is_foreign", "kund_standard_transportornr",
                "kund_has_standard_transportor", "kund_requires_lift", "kund_special_delivery_text",
                "pall_estimate", "sum_vikt_brutto", "sum_volym",
                "n_skrymmande_rader", "n_staplingsbara_rader", "n_unika_palltyper",
                "max_art_langd", "max_art_hojd", "sum_palltype_flakmeter_est",
                "n_langpall_rader", "n_extra_langa_pallrader", "sum_langpall_estimate",
                "sum_extra_langa_pall_estimate", "max_palltype_langd",
                "pallplatser", "n_pallar",
                "flakmeter", "sum_vikt", "max_pall_hojd",
                "order_volym_huvud", "order_vikt_huvud", "order_antal_huvud",
                "order_rader_huvud", "n_multi_huvud", "avg_multi_size_huvud",
                "max_multi_size_huvud", "n_ej_staplingsbara",
                "sum_helpalls_avvik", "avg_buffert_coverage", "max_buffert_coverage",
                "n_artiklar_med_buffert",
                "n_status_30", "n_status_35", "n_status_other_picked", "n_ar_plockad"]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0).astype(float)
    if use_cache:
        df.to_parquet(TRAINING_CACHE)
    return df


# Label-kolumner - kommer från dispatch-sidan (ground truth) och får INTE
# användas som input-feature (data leakage).
LABEL_COLS = ["pallplatser", "flakmeter", "n_pallar", "sum_vikt", "max_pall_hojd"]


def features_and_labels(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Splitta i features (det predictor får se) och label (pallplatser).

    Behåller 'grupp', 'kund', 'orderdatum' som ID-kolumner i features för spårbarhet
    men predict() ska normalt inte använda dem för pattern-matching (per-rad info).
    """
    features = df.drop(columns=[c for c in LABEL_COLS if c in df.columns])
    labels = df["pallplatser"]
    return features, labels


def transportor_height_table(dispatch: pd.DataFrame) -> pd.DataFrame:
    """Härled max-höjd per transportör från dispatch (proxy för fordonets maxhöjd)."""
    return (
        dispatch.groupby("transportor")
        .agg(max_hojd=("Höjd", "max"), p95_hojd=("Höjd", lambda s: s.quantile(0.95)), n=("Höjd", "size"))
        .reset_index()
        .sort_values("n", ascending=False)
    )


def split(df: pd.DataFrame, test_frac: float = 0.2, seed: int = 42):
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(df))
    n_test = int(len(df) * test_frac)
    test = df.iloc[idx[:n_test]].reset_index(drop=True)
    train = df.iloc[idx[n_test:]].reset_index(drop=True)
    return train, test


if __name__ == "__main__":
    df = build_training_data()
    print(f"Grupper (Kund+Orderdatum) med både features och label: {len(df):,}")
    print(f"\nPallplatser-statistik:")
    print(df["pallplatser"].describe())
    print(f"\nTop transportörer:")
    print(df["transportor"].value_counts().head(10))
    df.to_parquet(Path(__file__).parent / "training.parquet")
    print(f"\nSparat: training.parquet")

"""Inferens pa framtida ordrar - tar ny orderdetalj-CSV och predikterar pallplatser per grupp.

Anvander samma feature-extraktion som training-pipelinen, men hoppar over bridge
(plocklog/dispatch) eftersom de inte finns for nya ordrar.

Anvandning:
    python forecast.py <orderdetalj.csv> [transportor]
    python forecast.py <orderdetalj.csv> --xlsx[=<utfil.xlsx>] [--fore-dir=<mapp>]

    transportor ar valfri default-transportor om orderna saknar info.
    --fore-dir kan peka pa en alternativ mapp med supportfiler for inferens.
"""
from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
import os
import shutil
import sys
import unicodedata
from pathlib import Path

import pandas as pd

from . import pipeline
from .pipeline import (
    EXCLUDE_CUSTOMERS,
    _filter_mg,
    _to_num,
    load_buffert_pallets,
    load_customers,
    load_item_dimensions,
    load_item_options,
    load_items,
    load_order_overview,
)

REQUIRED_FORECAST_FILES = OrderedDict(
    [
        ("orders", "Orderdetaljer: v_ask_customer_order_details_all-*.csv"),
        ("overview", "Orderhuvud: v_ask_order_overview-*.csv"),
        ("custom", "Kundmaster: custom-*.csv"),
        ("item", "Artikelmaster: item-*.csv"),
        ("item_alias", "Artikeldimensioner: item_alias-*.csv"),
        ("dimension", "Dimensionsmaster: dimension-*.csv"),
        ("pallet_type", "Palltyper: pallet_type-*.csv"),
        ("item_option", "Artikelregler: item_option-*.csv"),
        ("buffert", "Buffertpallar: v_ask_article_buffertpallet-*.csv"),
    ]
)

SUPPORT_FILE_TYPES = tuple(k for k in REQUIRED_FORECAST_FILES if k != "orders")

FILE_TYPE_GLOBS = {
    "overview": "v_ask_order_overview-*.csv",
    "custom": "custom-*.csv",
    "item": "item-*.csv",
    "item_alias": "item_alias-*.csv",
    "dimension": "dimension-*.csv",
    "pallet_type": "pallet_type-*.csv",
    "item_option": "item_option-*.csv",
    "buffert": "v_ask_article_buffertpallet-*.csv",
}

STAGED_SUPPORT_FILENAMES = {
    file_type: pattern.replace("*", "flow")
    for file_type, pattern in FILE_TYPE_GLOBS.items()
}
UNKNOWN_TRANSPORTOR_LABEL = "Okänd"


def _round_for_display(series: pd.Series) -> pd.Series:
    """Keep forecast output numeric, non-negative and consistently rounded to two decimals."""
    return series.astype(float).clip(lower=0).round(2)


def _format_decimal(value: float | int) -> str:
    return f"{float(value):.2f}"


def _clean_transportor(value: object) -> str:
    text = "" if value is None or pd.isna(value) else str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return ""
    return text


def _transportor_or_default(value: object, default_transportor: str) -> str:
    return _clean_transportor(value) or default_transportor


def _transportor_for_result(value: object) -> str:
    return _clean_transportor(value) or UNKNOWN_TRANSPORTOR_LABEL


def _dominant_transportor(series: pd.Series) -> str:
    values = series.dropna().astype(str).str.strip()
    values = values[values.ne("") & ~values.str.lower().isin({"nan", "nat", "none"})]
    if values.empty:
        return ""
    mode = values.mode()
    if mode.empty:
        return ""
    return _clean_transportor(mode.iloc[0])


def _ascii_fold(value: object) -> str:
    text = "" if value is None else str(value)
    return (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
        .strip()
        .lower()
    )


def _read_probe_csv(path: Path, nrows: int = 50) -> pd.DataFrame | None:
    for sep in (None, "\t", ";", ","):
        try:
            df = pd.read_csv(
                path,
                dtype=str,
                nrows=nrows,
                sep=sep,
                engine="python",
                encoding="utf-8-sig",
            )
            if df.shape[1] == 1 and sep is None:
                continue
            return df
        except Exception:
            continue
    return None


def detect_forecast_file_type(path: str | Path) -> str | None:
    """Forsok avgora vilken forecast-fil som laddats in."""
    file_path = Path(path)
    if file_path.suffix.lower() != ".csv":
        return None

    name = file_path.name.lower()
    filename_hints = [
        ("v_ask_customer_order_details_all", "orders"),
        ("v_ask_order_overview", "overview"),
        ("v_ask_article_buffertpallet", "buffert"),
        ("item_option", "item_option"),
        ("item_alias", "item_alias"),
        ("pallet_type", "pallet_type"),
        ("dimension-", "dimension"),
        ("item-", "item"),
        ("custom-", "custom"),
    ]
    for hint, file_type in filename_hints:
        if hint in name:
            return file_type

    df = _read_probe_csv(file_path)
    if df is None:
        return None

    cols = {_ascii_fold(col) for col in df.columns}
    has = cols.__contains__

    if has("bestallt") and has("order nr"):
        return "orders"

    if has("ordernr") and has("orderdatum") and (has("transportor") or has("sandningsnr")):
        return "overview"

    if has("kund") and (has("pack instr") or has("pallhojd") or has("mellanpalls hojd")):
        return "custom"

    if has("artikel") and has("per pall") and has("vikt brutto") and has("volym"):
        return "item"

    if has("artikel") and has("langd") and has("bredd") and has("hojd"):
        return "item_alias"

    if has("dimension id") and has("langd") and has("bredd") and has("hojd"):
        return "dimension"

    if has("palltyp") and has("dimension") and has("flakmeter"):
        return "pallet_type"

    if has("artikel") and (has("ej staplingsbar") or has("helpalls avvikelse %") or has("plockzon")):
        return "item_option"

    if has("artikel") and has("pallid") and has("antal"):
        return "buffert"

    return None


def _candidate_sort_key(path: Path) -> tuple[str, float, str]:
    stem = path.stem
    timestamp = ""
    if "-" in stem:
        timestamp = stem.rsplit("-", 1)[-1]
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (timestamp, mtime, path.name.lower())


def choose_latest_file(paths: list[Path]) -> Path:
    if not paths:
        raise ValueError("No paths supplied")
    return sorted(paths, key=_candidate_sort_key)[-1]


def classify_forecast_files(
    paths: list[str | Path],
) -> tuple[dict[str, Path], list[str], list[Path], list[str]]:
    """Klassificera droppade filer och valj basta kandidat per filtyp."""
    candidates: dict[str, list[Path]] = {k: [] for k in REQUIRED_FORECAST_FILES}
    unknown: list[Path] = []
    notes: list[str] = []
    seen: set[str] = set()

    for raw_path in paths:
        path = Path(raw_path)
        try:
            key = str(path.resolve()).lower()
        except OSError:
            key = str(path).lower()
        if key in seen or not path.exists() or not path.is_file():
            continue
        seen.add(key)
        file_type = detect_forecast_file_type(path)
        if file_type in candidates:
            candidates[file_type].append(path)
        else:
            unknown.append(path)

    selected: dict[str, Path] = {}
    for file_type, file_paths in candidates.items():
        if not file_paths:
            continue
        chosen = choose_latest_file(file_paths)
        selected[file_type] = chosen
        if len(file_paths) > 1:
            notes.append(
                f"Flera filer matchade {REQUIRED_FORECAST_FILES[file_type]}. Valde senaste: {chosen.name}"
            )

    missing = [file_type for file_type in REQUIRED_FORECAST_FILES if file_type not in selected]
    return selected, missing, unknown, notes


def describe_required_forecast_files() -> str:
    lines = [
        "Ladda eller slapp in dessa CSV-filer samtidigt:",
        "",
    ]
    for label in REQUIRED_FORECAST_FILES.values():
        lines.append(f"- {label}")
    lines.extend(
        [
            "",
            "Appen valjer automatiskt senaste filen om flera matchar samma typ.",
            "Prognosen sparas som en ny Excel-fil bredvid orderdetaljfilen.",
        ]
    )
    return "\n".join(lines)


def stage_support_files(file_map: dict[str, Path], staging_root: str | Path) -> Path:
    """Kopiera supportfiler till en tillfallig Fore-mapp for inferens."""
    staging_root = Path(staging_root)
    fore_dir = staging_root / "Fore"
    fore_dir.mkdir(parents=True, exist_ok=True)
    for file_type in SUPPORT_FILE_TYPES:
        src = file_map[file_type]
        shutil.copy2(src, fore_dir / STAGED_SUPPORT_FILENAMES.get(file_type, src.name))
    return fore_dir


@contextmanager
def _override_fore_dir(data_fore: Path | None):
    if data_fore is None:
        yield
        return

    original_fore = pipeline.DATA_FORE
    pipeline.DATA_FORE = Path(data_fore)
    try:
        yield
    finally:
        pipeline.DATA_FORE = original_fore


def _load_new_orders(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t", encoding="utf-8-sig", dtype=str, low_memory=False)
    if "Beställt" not in df.columns or "Order nr" not in df.columns:
        filename = path.name
        if "order_overview" in filename:
            raise SystemExit(
                f"\n  FEL: '{filename}' ar ett ORDERHUVUD (en rad per order).\n"
                f"  forecast.py vill ha ORDERDETALJER (en rad per artikel).\n"
                f"  Anvand en fil med namn som borjar 'v_ask_customer_order_details_all-...'"
            )
        raise SystemExit(
            f"\n  FEL: '{filename}' saknar forvantade kolumner ('Bestallt', 'Order nr').\n"
            f"  Ar det en orderdetalj-CSV fran ASK?"
        )
    df = _filter_mg(df, "Kund")
    df["Beställt"] = _to_num(df["Beställt"])
    return df


def build_inference_features(
    orders_path: Path,
    default_transportor: str = "Schenker",
    data_fore: Path | None = None,
) -> pd.DataFrame:
    """Build features per Sandningsnr from a new order detail CSV."""
    orders = _load_new_orders(orders_path)

    with _override_fore_dir(data_fore):
        customers = load_customers()
        items = load_items()
        dims = load_item_dimensions()
        item_opts = load_item_options()
        buffert = load_buffert_pallets()
        order_overview = load_order_overview()

    orders = orders.rename(columns={"Order nr": "Ordernr"})
    orders = orders.merge(order_overview, on="Ordernr", how="inner")
    orders["Sändningsnr"] = orders["order_sandningsnr"].astype(str).str.strip()
    orders = orders[orders["Sändningsnr"].ne("") & orders["Sändningsnr"].str.lower().ne("nan")].copy()
    if orders.empty:
        raise ValueError("Forecasten hittade inga rader med Sändningsnr efter matchning mot order overview.")
    orders["grupp"] = orders["Sändningsnr"]

    orders["is_robot_raw"] = orders["Robot"].astype(str).str.upper().isin(["Y", "TRUE", "1"])

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

    orders["pall_estimate_rad"] = (orders["Beställt"] / orders["per_pall"].replace(0, pd.NA)).fillna(0)
    orders["rad_vikt"] = orders["Beställt"] * orders["vikt_brutto"]
    orders["rad_volym"] = orders["Beställt"] * orders["volym"]
    orders["effective_langd"] = orders[["art_langd", "item_pall_langd"]].fillna(0).max(axis=1)
    orders["is_skrymmande"] = orders["effective_langd"] > 140
    orders["is_staplingsbar"] = orders["item_staplingsbar"].fillna(False)
    orders["is_ej_staplingsbar"] = orders["opt_ej_staplingsbar"].fillna(False)
    orders["item_pall_langgods"] = orders["item_pall_langgods"].fillna(False)
    orders["item_pall_extra_lang"] = orders["item_pall_extra_lang"].fillna(False)
    orders["palltype_flakmeter_est_rad"] = orders["pall_estimate_rad"] * orders["item_pall_flakmeter"].fillna(0)
    orders["longpall_estimate_rad"] = orders["pall_estimate_rad"] * orders["item_pall_langgods"].astype(int)
    orders["extra_lang_pall_estimate_rad"] = orders["pall_estimate_rad"] * orders["item_pall_extra_lang"].astype(int)
    orders["bestallt_x_helpalls_avvik"] = orders["Beställt"] * orders["opt_helpalls_avvikelse_pct"].fillna(0) / 100
    orders["buffert_coverage_ratio"] = (
        orders["buffert_total_antal"].fillna(0) / orders["Beställt"].replace(0, pd.NA)
    ).fillna(0).clip(upper=10)

    status_series = orders["Status"].astype(str).str.strip()
    orders["status_30"] = status_series.eq("30")
    orders["status_35"] = status_series.eq("35")
    orders["status_other_picked"] = status_series.isin(["32", "33", "34", "36", "37", "38"])
    orders["is_ar_plockad"] = orders["Är plockad"].astype(str).str.strip().eq("1")

    feats = orders.groupby("grupp").agg(
        kund=("Kund", "first"),
        orderdatum=("Orderdatum", "first"),
        ordernummer=("Ordernr", lambda s: ", ".join(sorted({str(v).strip() for v in s.dropna() if str(v).strip()}))),
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
        order_volym_huvud=("order_volym_huvud", "sum"),
        order_vikt_huvud=("order_vikt_huvud", "sum"),
        order_antal_huvud=("order_antal_huvud", "sum"),
        order_rader_huvud=("order_rader_huvud", "sum"),
        n_multi_huvud=("order_multi", "sum"),
        avg_multi_size_huvud=("order_multi_size", "mean"),
        max_multi_size_huvud=("order_multi_size", "max"),
        n_ej_staplingsbara=("is_ej_staplingsbar", "sum"),
        sum_helpalls_avvik=("bestallt_x_helpalls_avvik", "sum"),
        avg_buffert_coverage=("buffert_coverage_ratio", "mean"),
        max_buffert_coverage=("buffert_coverage_ratio", "max"),
        n_artiklar_med_buffert=("buffert_n_pallar", lambda s: (s.fillna(0) > 0).sum()),
        n_status_30=("status_30", "sum"),
        n_status_35=("status_35", "sum"),
        n_status_other_picked=("status_other_picked", "sum"),
        n_ar_plockad=("is_ar_plockad", "sum"),
        transportor=(
            "order_transportor",
            lambda s: _transportor_or_default(_dominant_transportor(s), default_transportor),
        ),
        transportor_result=(
            "order_transportor",
            lambda s: _transportor_for_result(_dominant_transportor(s)),
        ),
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
    feats["transportor"] = feats["transportor"].map(
        lambda value: _transportor_or_default(value, default_transportor)
    )
    feats["transportor_result"] = feats["transportor_result"].map(_transportor_for_result)
    feats["orderdatum"] = pd.to_datetime(feats["orderdatum"], errors="coerce")

    num_cols = [
        "n_rader",
        "n_ordrar",
        "n_artiklar",
        "sum_bestallt",
        "sum_bestallt_robot",
        "sum_bestallt_manual",
        "n_robot_rader",
        "n_zoner",
        "n_packklasser",
        "kund_max_hojd",
        "kund_postnr_prefix2",
        "kund_postnr_prefix3",
        "kund_postnr_missing",
        "kund_is_foreign",
        "kund_standard_transportornr",
        "kund_has_standard_transportor",
        "kund_requires_lift",
        "kund_special_delivery_text",
        "pall_estimate",
        "sum_vikt_brutto",
        "sum_volym",
        "n_skrymmande_rader",
        "n_staplingsbara_rader",
        "n_unika_palltyper",
        "max_art_langd",
        "max_art_hojd",
        "sum_palltype_flakmeter_est",
        "n_langpall_rader",
        "n_extra_langa_pallrader",
        "sum_langpall_estimate",
        "sum_extra_langa_pall_estimate",
        "max_palltype_langd",
        "order_volym_huvud",
        "order_vikt_huvud",
        "order_antal_huvud",
        "order_rader_huvud",
        "n_multi_huvud",
        "avg_multi_size_huvud",
        "max_multi_size_huvud",
        "n_ej_staplingsbara",
        "sum_helpalls_avvik",
        "avg_buffert_coverage",
        "max_buffert_coverage",
        "n_artiklar_med_buffert",
        "n_status_30",
        "n_status_35",
        "n_status_other_picked",
        "n_ar_plockad",
    ]
    for col_name in num_cols:
        if col_name in feats.columns:
            feats[col_name] = pd.to_numeric(feats[col_name], errors="coerce").fillna(0.0).astype(float)
    return feats


def _predict(features: pd.DataFrame) -> pd.Series:
    # Importera modellen forst nar vi faktiskt kor en prognos, sa GUI:t startar snabbt.
    os.environ.setdefault("MESTERGRUPPEN_USE_TRAINING_CACHE", "1")
    from . import predict

    return predict.predict(features)


def _summarize_output(out: pd.DataFrame) -> dict[str, float | int]:
    values = out["predikterad_pallplatser"]
    return {
        "antal_grupper": int(len(out)),
        "summa_pallplatser": float(round(values.sum(), 2)) if len(out) else 0.0,
        "medel_pallplatser": float(round(values.mean(), 2)) if len(out) else 0.0,
        "median_pallplatser": float(round(values.median(), 2)) if len(out) else 0.0,
        "max_pallplatser": float(round(values.max(), 2)) if len(out) else 0.0,
    }


def export_forecast_to_excel(out: pd.DataFrame, summary: dict[str, float | int], xlsx_out: Path) -> None:
    with pd.ExcelWriter(xlsx_out, engine="openpyxl") as writer:
        out.to_excel(writer, sheet_name="Prognos", index=False)
        summary_df = pd.DataFrame(
            {
                "Matt": [
                    "Antal grupper",
                    "Summa predikterade pallplatser",
                    "Medel pallplatser/grupp",
                    "Median pallplatser/grupp",
                    "Max pallplatser/grupp",
                ],
                "Varde": [
                    summary["antal_grupper"],
                    summary["summa_pallplatser"],
                    summary["medel_pallplatser"],
                    summary["median_pallplatser"],
                    summary["max_pallplatser"],
                ],
            }
        )
        summary_df.to_excel(writer, sheet_name="Sammanfattning", index=False)

        forecast_sheet = writer.sheets["Prognos"]
        forecast_col = out.columns.get_loc("predikterad_pallplatser") + 1
        for row_idx in range(2, forecast_sheet.max_row + 1):
            forecast_sheet.cell(row=row_idx, column=forecast_col).number_format = "0.00"

        summary_sheet = writer.sheets["Sammanfattning"]
        for row_idx in range(2, summary_sheet.max_row + 1):
            metric = summary_sheet.cell(row=row_idx, column=1).value
            if metric != "Antal grupper":
                summary_sheet.cell(row=row_idx, column=2).number_format = "0.00"


def run_forecast(
    orders_path: str | Path,
    *,
    xlsx_out: str | Path | None = None,
    default_transportor: str = "Schenker",
    data_fore: str | Path | None = None,
) -> tuple[pd.DataFrame, dict[str, float | int]]:
    """Kor forecast-workflow och returnera resultatdata samt sammanfattning."""
    orders_path = Path(orders_path)
    fore_dir = Path(data_fore) if data_fore is not None else None

    features = build_inference_features(
        orders_path=orders_path,
        default_transportor=default_transportor,
        data_fore=fore_dir,
    )
    yhat = _predict(features)
    features["predikterad_rå"] = _round_for_display(yhat)
    features["predikterad_pallplatser"] = _round_for_display(yhat)

    out_cols = [
        "grupp",
        "kund",
        "orderdatum",
        "ordernummer",
        "n_ordrar",
        "n_rader",
        "transportor_result",
        "predikterad_pallplatser",
    ]
    out = features[out_cols].sort_values(["orderdatum", "kund", "grupp"]).reset_index(drop=True)
    out["orderdatum"] = out["orderdatum"].dt.strftime("%Y-%m-%d").fillna("")
    summary = _summarize_output(out)

    if xlsx_out is not None:
        export_forecast_to_excel(out, summary, Path(xlsx_out))

    out = out.rename(
        columns={
            "grupp": "Sändningsnr",
            "kund": "Kund",
            "orderdatum": "Orderdatum",
            "ordernummer": "Ordernummer",
            "n_ordrar": "Antal order",
            "n_rader": "Rader",
            "transportor_result": "Transportör",
            "predikterad_pallplatser": "Predikterade pallplatser",
        }
    )
    return out, summary


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    path = Path(sys.argv[1])
    xlsx_out: Path | None = None
    fore_dir: Path | None = None
    default_transportor = "Schenker"

    for arg in sys.argv[2:]:
        if arg.startswith("--xlsx="):
            xlsx_out = Path(arg.split("=", 1)[1])
        elif arg == "--xlsx":
            xlsx_out = path.with_name(f"prognos_{path.stem}.xlsx")
        elif arg.startswith("--fore-dir="):
            fore_dir = Path(arg.split("=", 1)[1])
        else:
            default_transportor = arg

    if not path.exists():
        print(f"Fil hittades inte: {path}", file=sys.stderr)
        sys.exit(1)

    out, summary = run_forecast(
        orders_path=path,
        xlsx_out=xlsx_out,
        default_transportor=default_transportor,
        data_fore=fore_dir,
    )

    if xlsx_out:
        print(f"Sparat: {xlsx_out}")
        print(
            f"Totalt: {summary['antal_grupper']} grupper, "
            f"summa predikterade pallplatser: {_format_decimal(summary['summa_pallplatser'])}"
        )
    else:
        display_out = out.copy()
        display_out["predikterad_pallplatser"] = display_out["predikterad_pallplatser"].map(_format_decimal)
        print(display_out.to_string(index=False))
        print(
            f"\nTotalt: {summary['antal_grupper']} grupper, "
            f"summa predikterade pallplatser: {_format_decimal(summary['summa_pallplatser'])}"
        )


if __name__ == "__main__":
    main()

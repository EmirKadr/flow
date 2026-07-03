#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
allokering12.1.py
---------------
Denna version (12.1) bygger vidare på tidigare versioner och lägger till
ytterligare förbättrad HIB‑koppling och cache‑hantering.

**Nyheter i version 12.1**

* **Förbättrad matchning av HIB‑ordrar**: Programmet matchar nu varje
  HIB‑orders sändningsnummer **och kundnamn** mot butikens ordrar. Om en
  butiksorder har samma sändningsnummer **och tillhör samma butik** (identiskt
  kundnamn) väljs den som referens (den tidigaste om flera finns). Om ingen
  sådan order finns matchas endast på sändningsnummer. I sista hand används
  den äldsta giltiga butiksordern som fallback.

  Denna version korrigerar även ett problem där HIB‑ordrar felaktigt
  föreslogs kopplas om till en annan butik när butikens order med rätt
  sändningsnummer hade status ≥ 34 och därför inte räknades som giltig. Nu
  används **alla butiksordrar** (oavsett status) för att hitta matchning på
  sändningsnummer och kundnamn. Endast om ingen sådan matchning hittas
  används fallback‑butiken.

* **Statushantering för butiksorder**: Butiksorder som saknar status i
  orderdetaljerna behandlas som giltiga (status 0) istället för att uteslutas.

* **Rensning av dispatchpallar vid cache‑reset**: När man väljer “Rensa
  cache” i GUI:et rensas nu även den valda dispatchpallsfilen och alla
  temporära dispatchresultat. Detta förhindrar att en gammal dispatchfil
  ligger kvar i minnet efter att man bytt dataset.

* **Övriga förbättringar från version 10.7** behålls, såsom robust
  kolumnmatchning, förbättrat GUI för filuppladdning och mer intuitiv
  statusvisning. Multi‑reglerna (fel zon, saknad multi) gäller bara när det
  finns mer än en HIB‑order per kundnummer. Med endast en HIB‑order sätts
  inte multi. Instruktionerna för ändringsordning skrivs ut i loggen och
  exportfilen. Kolumnmatchningen i orderöversikten är robust mot olika
  ordning och namn. Indata‑filvalet använder tydliga statusrutor med text
  ("Uppladdad" med grön bakgrund respektive "Ej fil" med grå bakgrund) och en
  röd borttagningsknapp. Drag‑och‑släpp‑zonen kan även klickas för att välja
  flera filer samtidigt. Fixar från 10.6 för korrekt initiering av
  statusikoner gäller fortsatt.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import platform
import queue
import re
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import os
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Deque, Dict, List, Tuple, Optional
import importlib.util
from pathlib import Path

from collections import defaultdict, deque
import pandas as pd
import tempfile
import sys
import subprocess
import numpy as np

from app_info import (
    APP_NAME,
    APP_TITLE,
    APP_VERSION,
)
from update_service import UpdateInfo, check_for_update, download_update_installer


def _parse_boolish(value: object) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "ja", "on"}:
        return True
    if text in {"0", "false", "no", "nej", "off"}:
        return False
    return None


def _app_config_path() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home())
    return Path(appdata) / "flow" / "warehouse_tools_config.json"


def _load_app_config() -> dict:
    path = _app_config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_app_config(config: dict) -> None:
    path = _app_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(config, indent=2, ensure_ascii=False, sort_keys=True)
    path.write_text(payload, encoding="utf-8")


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


def _runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _resource_path(*parts: str) -> Path:
    return _bundle_root().joinpath(*parts)


LOWFREQDATA_DIR = "lowfreqdata"
BUFFERPALL_DIR = "buffertpall"
ITEM_OPTION_DIR = "item-option"
BUFFERPALL_PATH_PARTS = (LOWFREQDATA_DIR, BUFFERPALL_DIR)
DEFAULT_OBSERVATIONS_BUSINESS_CODE = "STIGAMO"


def _bufferpall_resource_path(*parts: str) -> Path:
    return _resource_path(*BUFFERPALL_PATH_PARTS, *parts)


def _bufferpall_runtime_dir() -> Path:
    return _runtime_root().joinpath(*BUFFERPALL_PATH_PARTS)


def _bufferpall_source_dir() -> Path:
    return Path(__file__).resolve().parent.joinpath(*BUFFERPALL_PATH_PARTS)


def _normalise_observations_business_code(business_code: Optional[str] = None) -> str:
    value = str(business_code or DEFAULT_OBSERVATIONS_BUSINESS_CODE).strip().upper()
    return value or DEFAULT_OBSERVATIONS_BUSINESS_CODE


def _business_path_segment(business_code: Optional[str] = None) -> str:
    code = _normalise_observations_business_code(business_code)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", code).strip("._-").lower()
    return safe or "business"


def _business_bufferpall_runtime_dir(business_code: Optional[str] = None) -> Path:
    segment = _business_path_segment(business_code)
    root = _bufferpall_runtime_dir()
    return root / segment if segment else root


def _business_bufferpall_resource_path(business_code: Optional[str], filename: str) -> Path:
    segment = _business_path_segment(business_code)
    return _bufferpall_resource_path(segment, filename)


def _legacy_default_bufferpall_resource_path(business_code: Optional[str], filename: str) -> Optional[Path]:
    if _normalise_observations_business_code(business_code) != DEFAULT_OBSERVATIONS_BUSINESS_CODE:
        return None
    return _bufferpall_resource_path(filename)


def _seed_bufferpall_runtime_file(filename: str, business_code: Optional[str] = None) -> Path:
    runtime_path = _business_bufferpall_runtime_dir(business_code) / filename
    runtime_path.parent.mkdir(parents=True, exist_ok=True)

    resource_paths = [_business_bufferpall_resource_path(business_code, filename)]
    legacy_default_path = _legacy_default_bufferpall_resource_path(business_code, filename)
    if legacy_default_path is not None:
        resource_paths.append(legacy_default_path)
    for resource_path in resource_paths:
        if not runtime_path.exists() and resource_path.exists() and resource_path.resolve() != runtime_path.resolve():
            shutil.copy2(resource_path, runtime_path)
            break
    return runtime_path

def read_prognos_xlsx(path: str) -> pd.DataFrame:
    """
    Läser en prognos (XLSX) och returnerar ett normaliserat DataFrame.
    Steg:
      1) Ta bort de tre första raderna (index 0,1,3) om de finns.
      2) Ta bort kolumn A (första kolumnen).
      3) Använd första kvarvarande rad som rubriker och plocka ut relevanta kolumner.

    Returnerar DataFrame med kolumner:
      - Artikelnummer (str)
      - Beskrivning (str)
      - Antal styck (int)
      - Antal rader (int)
      - Antal butiker (int)
    """
    df = pd.read_excel(path, header=None, dtype=str, engine="openpyxl")
    if df.empty:
        return pd.DataFrame(columns=["Artikelnummer", "Beskrivning", "Antal styck", "Antal rader", "Antal butiker"])
    drop_idx = [i for i in (0, 1, 3) if i < len(df.index)]
    df = df.drop(index=drop_idx, errors="ignore").reset_index(drop=True)
    if df.shape[1] > 0:
        df = df.drop(columns=[df.columns[0]]).reset_index(drop=True)
    if df.empty:
        return pd.DataFrame(columns=["Artikelnummer", "Beskrivning", "Antal styck", "Antal rader", "Antal butiker"])
    header = df.iloc[0].astype(str).str.strip().tolist()
    df = df.iloc[1:].reset_index(drop=True)
    df.columns = header
    def _ci_match(name: str) -> str:
        return "".join(c.lower() for c in str(name).strip() if c.isalnum())
    def _pick_col(cols: List[str], candidates: List[str]) -> str | None:
        s_cols = { _ci_match(c): c for c in cols }
        for cand in candidates:
            key = _ci_match(cand)
            if key in s_cols:
                return s_cols[key]
        return None
    need_map: Dict[str, List[str]] = {
        "Artikelnummer": ["Product code", "SKU", "Artikelnr", "Artikelnummer"],
        "Beskrivning":   ["Product name", "Name", "Benämning", "Beskrivning"],
        "Antal styck":   ["Antal styck", "Antal stycken", "Qty", "Quantity"],
        "Antal rader":   ["Antal rader", "Rows", "Number of rows"],
        "Antal butiker": ["Antal butiker", "Stores", "Butiker", "Number of stores"],
    }
    picked: Dict[str, str] = {}
    for out_name, candidates in need_map.items():
        col = _pick_col(list(df.columns), candidates)
        if col:
            picked[out_name] = col
    out = pd.DataFrame()
    for out_name in ["Artikelnummer", "Beskrivning", "Antal styck", "Antal rader", "Antal butiker"]:
        if out_name in picked:
            out[out_name] = df[picked[out_name]]
        else:
            out[out_name] = pd.Series([None] * len(df), dtype=object)
    out["Artikelnummer"] = out["Artikelnummer"].astype(str).str.strip()
    out["Beskrivning"]   = out["Beskrivning"].astype(str).str.strip()
    for num_col in ["Antal styck", "Antal rader", "Antal butiker"]:
        out[num_col] = pd.to_numeric(out[num_col], errors="coerce").fillna(0).astype(int)
    mask_keep = out["Artikelnummer"].str.len().gt(0) | out["Beskrivning"].str.len().gt(0)
    out = out.loc[mask_keep].reset_index(drop=True)
    return out


def read_campaign_xlsx(path: str) -> pd.DataFrame:
    """
    Läs och normalisera en kampanjvolymfil (XLSX) enligt en fördefinierad sekvens av borttagningar av rader och kolumner.
    Returnerar ett DataFrame med kolumnerna:
      - Artikelnummer (str)
      - Antal styck (int)
    """
    df = pd.read_excel(path, header=None, dtype=str, engine="openpyxl")
    if df.empty:
        return pd.DataFrame(columns=["Artikelnummer", "Antal styck"])
    if len(df.index) > 4:
        df = df.drop(index=[4])
    drop_idx = [i for i in (0, 1, 2) if i < len(df.index)]
    df = df.drop(index=drop_idx)
    df = df.reset_index(drop=True)
    keep_cols = [c for c in df.columns if c <= 6]
    df = df.loc[:, keep_cols]
    if 5 in df.columns:
        df = df.drop(columns=[5])
    if 4 in df.columns:
        df = df.drop(columns=[4])
    if 3 in df.columns:
        df = df.drop(columns=[3])
    if 1 in df.columns:
        df = df.drop(columns=[1])
    if 0 in df.columns:
        df = df.drop(columns=[0])
    if df.shape[1] != 2:
        return pd.DataFrame(columns=["Artikelnummer", "Antal styck"])
    df = df.reset_index(drop=True)
    df.columns = ["Artikelnummer", "Antal styck"]
    df["Artikelnummer"] = df["Artikelnummer"].astype(str).str.strip()
    df["Antal styck"] = pd.to_numeric(df["Antal styck"], errors="coerce").fillna(0).astype(int)
    df = df.loc[df["Artikelnummer"].astype(str).str.len().gt(0)].reset_index(drop=True)
    if not df.empty and str(df.loc[0, "Artikelnummer"]).lower() in ("produktkod", "#"):
        df = df.drop(index=[0]).reset_index(drop=True)
    return df


# Uppdaterad programversion 12.1
DEFAULT_OUTPUT = "allocated_orders.csv"

INVALID_LOC_PREFIXES: Tuple[str, ...] = ("AA",)
INVALID_LOC_EXACT: set[str] = {"TRANSIT", "TRANSIT_ERROR", "MISSING", "UT2"}

ALLOC_BUFFER_STATUSES: set[int] = {29, 30, 32}
REFILL_BUFFER_STATUSES: set[int] = {29, 30}
ORDER_MAX_ALLOCATABLE_STATUS = 33

# Vecka 27 - tak/hus -> tillåtna matchande gräsklippare (per order krävs minst lika många gräsklippare som tak)
VECKA27_ROOF_TO_MOWERS: dict[str, frozenset[str]] = {
    "2002039": frozenset({"2003511", "2003512", "2002034", "2002035", "2002036"}),
    "2001926": frozenset({"2003708", "2003709"}),
    "2005080": frozenset({"2003482", "2003483", "2003484", "2003485", "2003486"}),
    "2001928": frozenset({"2001921", "2001922", "2001923"}),
    "2003711": frozenset({"2003710"}),
}

NEAR_MISS_PCT: float = 0.30  # 30 % över behov

# Artiklar som undantas från R-räkningen i compute_pallet_spaces
RF_PALLPLATS_EXCLUDE_ARTICLES: set[str] = {
    "1075621","1154474","1265531","1265532","1265533","1265534","1265535","1265536","1265537","1265539",
    "1265541","1265542","1265543","1265545","1265547","1265548","1265549","1265550","1265551","1265552",
    "1265553","1265554","1265555","1265557","1265558","1265559","1265560","1265561","1265562","1265563",
    "1265564","1265565","1265566","1265567","1265568","1265569","1265570","1265571","1265572","1265573",
    "1265575","1265576","1265578","1265579","1265580","1265581","1265582","1265583","1265584","1265585",
    "1265586","1265588","1265589","1265590","1265591","1265592","1265593","1265594","1265595","1265596",
    "1265598","1265601","1265602","1265603","1265604","1265605","1265606","1265607","1265608","1265609",
    "1265610","1265612","1265613","1265614","1265615","1265617","1265618","1265619","1265620","1265621",
    "1265622","1265623","1265624","1265625","1265626","1265627","1265628","1265629","1265630","1265631",
    "1265632","1265633","1265634","1265635","1265636","1265637","1265638","1265639","1265640","1265641",
    "1265642","1265643","1265644","1265645","1265646","1265651","1265652","1265653","1265654","1265655",
    "1265656","1265657","1265658","1265659","1265660","1265661","1265662","1265663","1265664","1265665",
    "1265666","1265667","1265669","1265671","1265672","1265673","1265674","1265675","1265676","1265677",
    "1265678","1265679","1265680","1265681","1265682","1265683","1265684","1265685","1265687","1265689",
    "1265690","1265692","1265693","1265694","1265695","1265696","1265697","1265698","1265699","1265700",
    "1265701","1265702","1265703","1265704","1265705","1265706","1265707","1265708","1265709","1265710",
    "1265711","1265712","1265713","1265714","1265715","1265716","1265717","1265718","1265719","1265720",
    "1265721","1265722","1265723","1265724","1265725","1265727","1265728","1265729","1265730","1265731",
    "1265733","1265734","1265735","1265737","1265738","1265739","1265740","1265741","1265742","1265743",
    "1265744","1265745","1265746","1265747","1265748","1265749","1265750","1265751","1265754","1265755",
    "1265756","1265757","1265760","1265762","1265763","1265764","1265765","1265766","1265768","1265770",
    "1265771","1265772","1265773","1265774","1265775","1265778","1265779","1265780","1265781","1265782",
    "1265783","1265784","1265785","1265786","1265787","1265788","1265789","1265790","1265791","1265793",
    "1265794","1265795","1265797","1265798","1265799","1265800","1265801","1265802","1265803","1265804",
    "1265805","1265806","1265807","1265808","1265809","1265810","1265811","1265812","1265813","1265814",
    "1265815","1265816","1265817","1265818","1265821","1265822","1265823","1265826","1265827","1265828",
    "1265829","1265830","1265832","1265833","1265834","1265835","1265837","1265838","1265839","1265840",
    "1265841","1265842","1265843","1265844","1265846","1265847","1265848","1265849","1265850","1265851",
    "1265852","1265853","1265854","1265855","1265856","1265857","1265858","1265859","1265860","1265861",
    "1265862","1265863","1265864","1265865","1265866","1265867","1265868","1265869","1265870","1265871",
    "1265872","1265873","1265874","1265876","1265877","1265878","1265879","1265880","1265881","1265882",
    "1265883","1265884","1265885","1265886","1265887","1265888","1265889","1265890","1265891","1265892",
    "1265894","1265895","1265896","1265897","1265899","1265900","1265902","1265903","1265904","1265905",
    "1265906","1265907","1265908","1265909","1265910","1265911","1265912","1265913","1265915","1265916",
    "1265917","1265918","1265919","1265920","1265921","1265923","1265924","1265925","1265926","1265927",
    "1265928","1265929","1265930","1265931","1265932","1265933","1265934","1265935","1265936","1265937",
    "1265938","1265939","1265940","1265941","1265942","1265943","1265944","1265945","1265946","1265947",
    "1265948","1265951","1265952","1265953","1265954","1265955","1265956","1265957","1265958","1265959",
    "1265960","1265961","1265963","1265965","1265966","1265967","1265968","1265969","1265970","1265971",
    "1265972","1265973","1265974","1265975","1265976","1265977","1265978","1265979","1265980","1265981",
    "1265983","1265984","1265985","1265986","1265987","1265988","1265989","1265991","1265992","1265993",
    "1265994","1265995","1265996","1265997","1265998","1265999","1266000","1266001","1266002","1266003",
    "1266004","1266005","1266006","1266008","1266009","1266010","1266011","1266012","1266013","1266014",
    "1266015","1266017","1266018","1266019","1266020","1266021","1266022","1266023","1266024","1266025",
    "1266026","1266027","1266034","1266035","1266036","1266037","1266038","1266039","1266040","1266041",
    "1266042","1266043","1266044","1266045","1266046","1266047","1266048","1266049","1266050","1266051",
    "1266052","1266053","1266054","1266056","1266057","1266058","1266059","1266060","1266061","1266062",
    "1266063","1266065","1266066","1266067","1266068","1266069","1266070","1266072","1266073","1266074",
    "1266075","1266076","1266077","1266078","1266079","1266081","1266082","1266084","1266085","1266086",
    "1266087","1266088","1266089","1266091","1266093","1266094","1266095","1266096","1266097","1266099",
    "1266100","1266101","1266102","1266231","1266233","1266234","1266236","1266237","1266238","1266239",
    "1266240","1266241","1266242","1266244","1266245","1266246","1266247","1266248","1266249","1266251",
    "1266252","1266253","1266254","1266255","1266256","1266257","1266260","1266261","1266262","1266263",
    "1266264","1266265","1266266","1266268","1266270","1266271","1266272","1266273","1266274","1266275",
    "1266276","1266277","1266279","1266280","1266283","1266284","1266285","1266863","1266864","1266865",
    "1266866","1266868","1266872","1266873","1266874","1266875","1266876","1267022","1267023","1267024",
    "1267025","1267031","1267033","1267034","1267043","1267044","1267045","1267046","1267048","1267050",
    "1267054","1267055","1267059","1267064","1267067","1267086","1267090","1267093","1267104","1267116",
    "1267119","1267121","1267122","1267124","1267127","1268095","1268097","1268167","1268168","1268169",
    "1268170","1268171","1268172","1268173","1268174","1268175","1268176","1268177","1268178","1268179",
    "1268180","1268181","1268182","1268183","1268184","1269119","1269120","1269189","1269190","1269191",
    "1269192","1269193","1269194","1269195","1269196","1269197","1269198","1269199","1269200","1269201",
    "1269202","1269203","1269204","1269205","1269206","1269207","1269208","1269239","1269243","1269244",
    "1269245","1269246","1269247","1269250","1269251","1269252","1269253","1269254","1269255","1269256",
    "1269258","1269259","1269260","1269263","1269264","1269265","1269267","1269268","1269270","1269271",
    "1269272","1269273","1270087","1270088","1270089","1270090","1270091","1270092","1270093","1270094",
    "1270095","1270096","1270097","1270098","1270099","1270100","1270101","1270102","1270103","1270104",
    "1270105","1270106","1270107","1270108","1270109","1270110","1270111","1270112","1270113","1270114",
    "1270115","1270116","1270117","1270118","1270119","1270120","1270121","1270122","1270123","1270124",
    "1270125","1270126","1270127","1270128","1270129","1270130","1270131","1270132","1270133","1270134",
    "1270135","1270136","1270137","1270138","1270139","1270140","1270141","1270142","1270143","1270144",
    "1270145","1270146","1270147","1270148","1270149","1270150","1270151","1270152","1270153","1270154",
    "1270155","1270156","1270157","1270158","1270159","1270160","1270161","1270162","1270163","1270164",
    "1270165","1270166","1270167","1270168","1270169","1270170","1270171","1270172","1270173","1270174",
    "1270175","1270176","1270177","1270178","1270179","1270180","1270181","1270182","1270183","1270184",
    "1270185","1270186","1270187","1270188","1270189","1270190","1270191","1270192","1270193","1270194",
    "1270195","1270196","1270197","1270198","1270199","1270200","1270201","1270202","1270203","1270204",
    "1270205","1270206","1270207","1270208","1270209","1270210","1270211","1270212","1270213","1270214",
    "1270215","1270216","1270217","1270218","1270219","1270220","1270221","1270222","1270223","1270224",
    "1270225","1270226","1270227","1270228","1270229","1270230","1270231","1270232","1270233","1270234",
    "1270235","1270547","1270548","1270549","1270550","1270551","1270552","1270553","1270554","1270555",
    "1270556","1270557","1270558","1270559","1270560","1270561","1270634","2001334","2001335","2001336",
    "2001337","2001338","2001339","2001340","2001341","2001342","2001343","2001344","2001345","2001346",
    "2001347","2001348","2001349","2001350","2001351","2001352","2001353","2001354","2001355","2001356",
    "2001357","2001358","2001359","2001360","2001361","2001362","2001363","2001364","2001365","2001366",
    "2001367","2001368","2001369","2001370","2001371","2001372","2001373","2001374","2001375","2001376",
    "2001377","2001378","2001379","2001380","2001381","2001382","2001433","2001434","2001435","2001436",
    "2003381","2003382","2003383","2003384","2003385","2003386","2003387","2003388","2003389","2003390",
    "2003391","2003392","2003393","2003394","2003395","2003396","2003397","2003398","2003399","2003400",
    "2003401","2003402","2003403","2003404","2003405","2003406","2003407","2003408","2003409","2003410",
    "2003411","2003412","2003413","2003414","2003415","2003416","2003417","2003418","2003419","2003420",
    "2003423","2003424","2003425","2003426","2003427","2003428","2003429","2003430","2003431","2003432",
    "2003433","2003434","2003435","2003436","2003437","2003438","2003439","2003440","2003441","2003442",
    "2003443","2003444","2003445","2003448","2003449","2003450","2003451","2003452","2003453","2003454",
    "2003455","2003456","2003457","2003458","2003459","2003460","2003461","2003462","2003463","2003464",
    "2003465","2003466","2003467","2003514","2003515","1169745","1267354","1267355","1169747","1169746",
    "1267358","1267357","1267356",
}


ORDER_SCHEMA: Dict[str, List[str]] = {
    "artikel": ["artikel", "artikelnummer", "sku", "article", "artnr", "art.nr"],
    "qty":     ["beställt", "antal", "qty", "quantity", "bestalld", "order qty"],
    "status":  ["status", "radstatus", "orderstatus", "state"],
    "ordid":   ["ordernr", "order nr", "order number", "kund", "kundnr"],
    "radid":   ["radnr", "rad nr", "line id", "rad", "struktur", "radsnr"],
}
BUFFER_SCHEMA: Dict[str, List[str]] = {
    "artikel": ["artikel", "article", "artnr", "art.nr", "artikelnummer"],
    "qty":     ["antal", "qty", "quantity", "pallantal", "colli", "units"],
    "loc":     ["lagerplats", "plats", "location", "bin", "hyllplats"],
    "dt":      ["datum/tid", "datum", "mottagen", "received", "inleverans", "inleveransdatum", "timestamp", "arrival"],
    "id":      ["pallid", "pall id", "id", "sscc", "etikett", "batch", "lpn"],
    "status":  ["status", "pallstatus", "state"],
}

NOT_PUTAWAY_SCHEMA: Dict[str, List[str]] = {
    "artikel":  ["artikel", "artnr", "art.nr", "artikelnummer"],
    "namn":     ["artikelnamn", "artikelbenämning", "benämning", "produktnamn", "namn", "artikel.1"],
    "antal":    ["antal", "qty", "quantity", "kolli"],
    "status":   ["status"],
    "pallnr":   ["pall nr", "pallid", "pall id", "pall"],
    "sscc":     ["sscc"],
    "andrad":   ["ändrad", "senast ändrad", "timestamp"],
    "utgang":   ["utgång", "bäst före", "utgångsdatum", "utgangsdatum", "best före"],
}

SALDO_SCHEMA: Dict[str, List[str]] = {
    "artikel":    ["artikel", "artnr", "art.nr", "artikelnummer", "sku", "article"],
    "plocksaldo": ["plocksaldo", "plock saldo", "plock-saldo", "saldo", "pick saldo", "pick qty",
                   "tillgängligt plock", "tillgangligt plock", "available pick", "plock"],
    "plockplats": ["plockplats", "huvudplock", "mainpick", "hyllplats", "bin", "location", "lagerplats"],
}

ITEM_SCHEMA: Dict[str, List[str]] = {
    "artikel": ORDER_SCHEMA["artikel"],  # återanvänd artikel-kandidater från beställningar
    "staplingsbar": [
        "staplingsbar", "staplings bar", "staplbar", "stackable",
        "ej staplingsbar", "ejstaplingsbar", "ej_staplingsbar", "non stackable"
    ]
}


# -----------------------------------------------
# Ny funktion för HIB‑koppling
# Denna funktion tar beställningsrader och orderöversikt och räknar ut vilka HIB‑ordrar
# som behöver uppdateras. Resultatet returneras som ett DataFrame med kolumnerna
# "ordernummer", "Orderdatum", "sändningsnummer", "Zon" och "Multi". Endast
# ordrar med minst en ändring inkluderas i resultatet. Zonuppdateringar anges alltid
# som "F" om någon orderrad inte ligger i zon F/H/R. Multi sätts till "MULTI"
# om antingen flera olika multi‑nummer finns för kundens HIB‑ordrar i zon F, om
# något multi‑nummer saknas eller om någon HIB‑order behöver zonuppdatering.

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

def _clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ta bort BOM/whitespace i kolumnnamn för robustare kolumnmatchning."""
    try:
        df.rename(columns=lambda c: str(c).replace("\ufeff", "").strip(), inplace=True)
    except Exception:
        pass
    return df

def smart_to_datetime(s) -> pd.Series:
    """Robust datumtolkning (ISO→dayfirst=False, annars True; fallback tvärtom)."""
    try:
        ser = pd.Series(s) if not isinstance(s, pd.Series) else s
        vals = ser.dropna().astype(str).str.strip()
        sample = vals.head(50)
        numeric_like = (sample.str.match(r"^\d{8}$").sum() >= max(1, int(len(sample) * 0.6)))
        if numeric_like:
            dt = pd.to_datetime(ser, format="%Y%m%d", errors="coerce")
            if not dt.isna().all():
                return dt
        iso_like = (sample.str.match(r"^\d{4}-\d{2}-\d{2}").sum() >= max(1, int(len(sample) * 0.6)))
        primary_dayfirst = False if iso_like else True
        dt = pd.to_datetime(ser, errors="coerce", dayfirst=primary_dayfirst)
        if hasattr(dt, "isna") and getattr(dt, "isna")().all():
            dt = pd.to_datetime(ser, errors="coerce", dayfirst=not primary_dayfirst)
        return dt
    except Exception:
        try: return pd.to_datetime(s, errors="coerce", dayfirst=True)
        except Exception: return pd.to_datetime(s, errors="coerce", dayfirst=False)

def to_num(x) -> float:
    if pd.isna(x): return 0.0
    s = str(x).replace(" ", "").replace(",", ".")
    m = re.search(r"[-+]?\d*\.?\d+", s)
    return float(m.group()) if m else 0.0

def find_col(df: pd.DataFrame, candidates: List[str], required: bool = True, default=None) -> str:
    """Hitta en kolumn genom exakt eller substring-match mot kandidatnamn (case-insensitive)."""
    cols = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in cols: return cols[cand.lower()]
    for key, orig in cols.items():
        for cand in candidates:
            if cand.lower() in key: return orig
    if required and default is None:
        raise KeyError(f"Hittar inte kolumnerna {candidates} i {list(df.columns)}")
    return default

def _find_lyx_max_csv() -> Optional[Path]:
    candidates = [
        business_artikel_max_path(DEFAULT_OBSERVATIONS_BUSINESS_CODE),
        _business_bufferpall_resource_path(DEFAULT_OBSERVATIONS_BUSINESS_CODE, "artikel_max.csv"),
        _legacy_default_bufferpall_resource_path(DEFAULT_OBSERVATIONS_BUSINESS_CODE, "artikel_max.csv"),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.exists():
            return candidate
    return None


ORDERSALDO_COLUMN_CANDIDATES: Dict[str, List[str]] = {
    "order": ["ordernr", "ordernummer", "order number", "order no", "orderid", "order"],
    "article": ["artikel", "artikelnr", "artikelnummer", "artnr", "sku", "item", "productcode"],
    "demand": ["beställt", "bestalld", "ordered", "orderqty", "qty", "quantity", "antal"],
    "pick": ["plock", "plocksaldo", "saldo", "available", "stock", "qtyavailable", "saldo autoplock"],
}

PAFYLLNADSPRIO_COLUMNS: List[str] = ["ALLA", "PRIO 1", "PRIO 2", "PRIO 3", "PRIO 4", "PRIO 5"]
LASTNINGSFONSTER_PRIO_COLUMNS: List[str] = ["PRIO", "LASTNINGSFÖNSTER"]
LASTNINGSFONSTER_UNKNOWN_SORT = pd.Timestamp("2262-04-11 23:47:00")
LASTNINGSFONSTER_UNKNOWN_LABEL = "Saknar lastningsfönster"


def _ordersaldo_norm(value: str) -> str:
    """Normalisera kolumnnamn för robust matchning."""
    txt = str(value).lower()
    txt = txt.replace("å", "a").replace("ä", "a").replace("ö", "o")
    txt = re.sub(r"[^a-z0-9]+", "", txt)
    return txt


def _ordersaldo_find_col(df: pd.DataFrame, candidates: List[str], used_cols: set[str]) -> Optional[str]:
    """Hitta kolumn via exakt/fuzzy match mot kandidater."""
    cols = [str(c) for c in df.columns]
    norm_cols = {col: _ordersaldo_norm(col) for col in cols}
    cand_norm = [_ordersaldo_norm(c) for c in candidates]
    for cand in cand_norm:
        for col, norm_col in norm_cols.items():
            if col in used_cols:
                continue
            if norm_col == cand:
                return col
    for cand in cand_norm:
        for col, norm_col in norm_cols.items():
            if col in used_cols:
                continue
            if cand and cand in norm_col:
                return col
    return None


def _find_ordersaldo_columns(
    df: pd.DataFrame,
    column_candidates: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Optional[str]]:
    candidates = column_candidates or ORDERSALDO_COLUMN_CANDIDATES
    used: set[str] = set()
    order_col = _ordersaldo_find_col(df, candidates["order"], used)
    if order_col:
        used.add(order_col)
    article_col = _ordersaldo_find_col(df, candidates["article"], used)
    if article_col:
        used.add(article_col)
    demand_col = _ordersaldo_find_col(df, candidates["demand"], used)
    if demand_col:
        used.add(demand_col)
    pick_col = _ordersaldo_find_col(df, candidates["pick"], used)
    return {
        "order": order_col,
        "article": article_col,
        "demand": demand_col,
        "pick": pick_col,
    }


def compute_ordersaldo_data(
    df: pd.DataFrame,
    utbest_map: Optional[Dict[str, float]] = None,
    column_names: Optional[Dict[str, Optional[str]]] = None,
) -> Tuple[list[str], pd.DataFrame]:
    """
    Beräkna ordersaldo-listor och underskottsdata per artikel från beställningslinjer.

    Returnerar (kompletta_ordrar, underskott_df) där underskott_df har index=artikelnummer
    och kolumnerna Total beställt, Tillgängligt saldo (Plock), Utbeställt, Underskott.
    """
    empty = pd.DataFrame(
        columns=["Total beställt", "Tillgängligt saldo (Plock)", "Utbeställt", "Underskott"]
    )
    if not isinstance(df, pd.DataFrame) or df.empty:
        return [], empty

    calc_df = _clean_columns(df.copy())
    cols = column_names or _find_ordersaldo_columns(calc_df)
    order_col = cols.get("order")
    article_col = cols.get("article")
    demand_col = cols.get("demand")
    pick_col = cols.get("pick")
    if not order_col or not article_col or not demand_col or not pick_col:
        raise KeyError("Hittar inte order-, artikel-, antal- eller plockkolumn i beställningsfilen.")

    calc_df[order_col] = calc_df[order_col].astype(str).str.strip()
    calc_df[article_col] = calc_df[article_col].astype(str).str.strip()
    calc_df[demand_col] = calc_df[demand_col].map(to_num).astype(float)
    calc_df[pick_col] = calc_df[pick_col].map(to_num).astype(float)

    calc_df["_enough_row"] = calc_df[pick_col] >= calc_df[demand_col]
    complete_mask = calc_df.groupby(order_col)["_enough_row"].all()
    complete_orders = sorted(complete_mask[complete_mask].index.astype(str).tolist())

    demand_by_art = calc_df.groupby(article_col)[demand_col].sum(min_count=1)
    stock_by_art = calc_df.groupby(article_col)[pick_col].max()
    holistic = pd.DataFrame({
        "Total beställt": demand_by_art,
        "Tillgängligt saldo (Plock)": stock_by_art,
    }).fillna(0)
    holistic.index = holistic.index.map(lambda value: str(value).strip())

    if utbest_map is None:
        utbest_map = {}
    holistic["Utbeställt"] = holistic.index.to_series().map(utbest_map).fillna(0.0)
    holistic["Underskott"] = (
        holistic["Total beställt"] + holistic["Utbeställt"] - holistic["Tillgängligt saldo (Plock)"]
    ).clip(lower=0)
    holistic_short = holistic[holistic["Underskott"] > 0].copy().sort_index()
    return complete_orders, holistic_short


def _build_article_max_map(max_df: pd.DataFrame) -> Dict[str, float]:
    max_df = _clean_columns(max_df.copy())
    max_art_col = find_col(max_df, ["artikelnummer", "artikel", "artnr", "art.nr", "sku"])
    max_val_col = find_col(max_df, ["max"])
    tmp = pd.DataFrame({
        "_art": _safe_str_series(max_df[max_art_col]),
        "_max": max_df[max_val_col].map(to_num),
    })
    tmp = tmp[tmp["_art"].ne("")].dropna(subset=["_max"])
    return tmp.drop_duplicates(subset="_art").set_index("_art")["_max"].to_dict()


def _classify_pafyllnadsprio(underskott: float, reference_value: float) -> Tuple[str, bool]:
    try:
        reference = float(reference_value)
    except Exception:
        reference = 0.0
    if pd.isna(reference) or reference <= 0:
        return "PRIO 5", True

    ratio = float(underskott) / reference
    if ratio <= 0.25:
        return "PRIO 1", False
    if ratio <= 0.40:
        return "PRIO 2", False
    if ratio <= 0.55:
        return "PRIO 3", False
    if ratio <= 0.70:
        return "PRIO 4", False
    return "PRIO 5", False


def _build_pafyllnadsprio_dataframe(groups: Dict[str, List[str]]) -> pd.DataFrame:
    max_len = max((len(values) for values in groups.values()), default=0)
    padded = {
        column: values + [""] * (max_len - len(values))
        for column, values in groups.items()
    }
    return pd.DataFrame(padded, columns=PAFYLLNADSPRIO_COLUMNS)


def build_pafyllnadsprio_report(shortage_df: pd.DataFrame, max_df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """Bygg enkel fallback-rapport för Påfyllnadsprio utan lastningsfönster."""
    groups = {column: [] for column in PAFYLLNADSPRIO_COLUMNS}
    if not isinstance(shortage_df, pd.DataFrame) or shortage_df.empty:
        return pd.DataFrame(columns=PAFYLLNADSPRIO_COLUMNS), 0

    max_map = _build_article_max_map(max_df)
    missing_reference_count = 0
    work = shortage_df.copy()
    work.index = work.index.map(lambda value: str(value).strip())
    work = work[work.index != ""].sort_index()

    for article, row in work.iterrows():
        groups["ALLA"].append(article)
        reference_value = max_map.get(article, 0.0)
        prio, missing_reference = _classify_pafyllnadsprio(to_num(row.get("Underskott", 0.0)), reference_value)
        if missing_reference:
            missing_reference_count += 1
        groups[prio].append(article)

    return _build_pafyllnadsprio_dataframe(groups), missing_reference_count


def _combine_orderdatum_and_laststart(orderdatum_value: object, laststart_value: object) -> pd.Timestamp | pd.NaT:
    """Kombinera datum från Orderdatum med klockslag från Laststarttid."""
    order_ts = pd.to_datetime(orderdatum_value, errors="coerce", dayfirst=False)
    if pd.isna(order_ts):
        return pd.NaT
    match = re.search(r"(\d{1,2}):(\d{2})", str(laststart_value or "").strip())
    if not match:
        return pd.NaT
    hour = int(match.group(1))
    minute = int(match.group(2))
    try:
        return pd.Timestamp(
            year=int(order_ts.year),
            month=int(order_ts.month),
            day=int(order_ts.day),
            hour=hour,
            minute=minute,
        )
    except Exception:
        return pd.NaT


def _format_lastningsfonster_label(window_ts: pd.Timestamp) -> str:
    if pd.isna(window_ts):
        return LASTNINGSFONSTER_UNKNOWN_LABEL
    return pd.Timestamp(window_ts).strftime("%Y-%m-%d %H:%M")


def _prepare_lastningsfonster_overview(overview_df: pd.DataFrame) -> pd.DataFrame:
    """Normalisera orderöversikten till en order -> lastningsfönster-tabell."""
    overview = _clean_columns(overview_df.copy())
    order_col = find_col(overview, ["ordernr", "ordernummer", "order number", "order no", "orderid", "order"])
    orderdatum_col = find_col(overview, ["orderdatum", "order datum", "order date", "orderdate"])
    laststart_col = find_col(
        overview,
        ["laststarttid", "laststart tid", "laststart", "laststart time", "last start time"],
    )

    tmp = pd.DataFrame({
        "_order": overview[order_col].astype(str).str.strip(),
        "_orderdatum": overview[orderdatum_col],
        "_laststart": overview[laststart_col],
    })
    tmp = tmp[tmp["_order"] != ""].copy()
    if tmp.empty:
        return pd.DataFrame(columns=["_order", "_window_sort", "_window_label", "_prio", "_missing_window"])

    tmp["_window_sort"] = [
        _combine_orderdatum_and_laststart(orderdatum_value, laststart_value)
        for orderdatum_value, laststart_value in zip(tmp["_orderdatum"], tmp["_laststart"])
    ]

    rows: List[dict] = []
    for order, grp in tmp.groupby("_order", sort=True):
        valid = grp.dropna(subset=["_window_sort"]).sort_values("_window_sort")
        if not valid.empty:
            window_ts = pd.Timestamp(valid.iloc[0]["_window_sort"])
            rows.append({
                "_order": str(order).strip(),
                "_window_sort": window_ts,
                "_window_label": _format_lastningsfonster_label(window_ts),
                "_missing_window": False,
            })
        else:
            rows.append({
                "_order": str(order).strip(),
                "_window_sort": LASTNINGSFONSTER_UNKNOWN_SORT,
                "_window_label": LASTNINGSFONSTER_UNKNOWN_LABEL,
                "_missing_window": True,
            })

    out = pd.DataFrame(rows)
    valid_windows = sorted(
        {pd.Timestamp(value) for value in out.loc[~out["_missing_window"], "_window_sort"].tolist()}
    )
    prio_map: Dict[pd.Timestamp, str] = {}
    for idx, window_ts in enumerate(valid_windows):
        prio_map[window_ts] = f"PRIO {idx + 1}" if idx < 4 else "PRIO 5"
    out["_prio"] = out["_window_sort"].map(prio_map).fillna("PRIO 5")
    return out[["_order", "_window_sort", "_window_label", "_prio", "_missing_window"]]


def _build_lastningsfonster_prio_dataframe(overview_windows: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    """Bygg en enkel översikt över vilka lastningsfönster som motsvarar PRIO 1-4."""
    if not isinstance(overview_windows, pd.DataFrame) or overview_windows.empty:
        return pd.DataFrame(columns=LASTNINGSFONSTER_PRIO_COLUMNS), []

    prio_map = (
        overview_windows.loc[
            (~overview_windows["_missing_window"]) & (overview_windows["_prio"].isin(PAFYLLNADSPRIO_COLUMNS[1:5])),
            ["_window_sort", "_window_label", "_prio"],
        ]
        .drop_duplicates()
        .sort_values(["_window_sort", "_prio", "_window_label"])
    )
    if prio_map.empty:
        return pd.DataFrame(columns=LASTNINGSFONSTER_PRIO_COLUMNS), []

    rows: List[dict] = []
    log_lines: List[str] = []
    for _, row in prio_map.iterrows():
        prio = str(row["_prio"]).strip()
        label = str(row["_window_label"]).strip()
        rows.append({"PRIO": prio, "LASTNINGSFÖNSTER": label})
        log_lines.append(f"{prio} = {label}")

    return pd.DataFrame(rows, columns=LASTNINGSFONSTER_PRIO_COLUMNS), log_lines


def build_pafyllnadsprio_lastningsfonster_report(
    orders_df: pd.DataFrame,
    shortage_df: pd.DataFrame,
    overview_df: pd.DataFrame,
    max_df: pd.DataFrame,
    *,
    column_names: Optional[Dict[str, Optional[str]]] = None,
) -> Tuple[pd.DataFrame, set[tuple[int, int]], List[str], int, pd.DataFrame]:
    """Bygg Påfyllnadsprio med lastningsfönster där samma artikel kan ligga i flera PRIO-kolumner."""
    groups = {column: [] for column in PAFYLLNADSPRIO_COLUMNS}
    empty_window_map = pd.DataFrame(columns=LASTNINGSFONSTER_PRIO_COLUMNS)
    if not isinstance(shortage_df, pd.DataFrame) or shortage_df.empty:
        return pd.DataFrame(columns=PAFYLLNADSPRIO_COLUMNS), set(), [], 0, empty_window_map

    orders_work = _clean_columns(orders_df.copy())
    cols = column_names or _find_ordersaldo_columns(orders_work)
    order_col = cols.get("order")
    article_col = cols.get("article")
    demand_col = cols.get("demand")
    if not order_col or not article_col or not demand_col:
        raise KeyError("Hittar inte order-, artikel- eller antalskolumn i beställningsfilen.")

    overview_windows = _prepare_lastningsfonster_overview(overview_df)
    demand_rows = pd.DataFrame({
        "_order": orders_work[order_col].astype(str).str.strip(),
        "_article": orders_work[article_col].astype(str).str.strip(),
        "_qty": orders_work[demand_col].map(to_num).astype(float),
    })
    demand_rows = demand_rows[(demand_rows["_article"] != "") & (demand_rows["_qty"] > 0)].copy()
    if demand_rows.empty:
        return pd.DataFrame(columns=PAFYLLNADSPRIO_COLUMNS), set(), [], 0, empty_window_map

    demand_rows = demand_rows.merge(
        overview_windows,
        how="left",
        left_on="_order",
        right_on="_order",
    )
    demand_rows["_window_sort"] = pd.to_datetime(demand_rows["_window_sort"], errors="coerce")
    demand_rows["_window_sort"] = demand_rows["_window_sort"].fillna(LASTNINGSFONSTER_UNKNOWN_SORT)
    demand_rows["_window_label"] = demand_rows["_window_label"].fillna(LASTNINGSFONSTER_UNKNOWN_LABEL)
    demand_rows["_prio"] = demand_rows["_prio"].fillna("PRIO 5")
    demand_by_window = (
        demand_rows.groupby(["_article", "_window_sort", "_window_label", "_prio"], as_index=False)["_qty"]
        .sum()
        .sort_values(["_article", "_window_sort", "_window_label"])
    )
    window_map_df, window_map_log_lines = _build_lastningsfonster_prio_dataframe(overview_windows)

    max_map = _build_article_max_map(max_df)
    prio_counts: Dict[str, Dict[str, int]] = {prio: {} for prio in PAFYLLNADSPRIO_COLUMNS[1:]}
    log_lines: List[str] = []
    missing_reference_count = 0

    work = shortage_df.copy()
    work.index = work.index.map(lambda value: str(value).strip())
    work = work[work.index != ""].sort_index()

    for article, row in work.iterrows():
        groups["ALLA"].append(article)
        reference_value = max_map.get(article, 0.0)
        try:
            reference_float = float(reference_value)
        except Exception:
            reference_float = 0.0
        if pd.isna(reference_float) or reference_float <= 0:
            missing_reference_count += 1
            prio_counts["PRIO 5"][article] = max(prio_counts["PRIO 5"].get(article, 0), 1)
            log_lines.append(f"Artikel {article} saknar referensvärde och placerades i PRIO 5.")
            continue

        article_windows = demand_by_window[demand_by_window["_article"] == article].copy()
        if article_windows.empty:
            prio_counts["PRIO 5"][article] = max(prio_counts["PRIO 5"].get(article, 0), 1)
            log_lines.append(f"Artikel {article} saknar matchning mot lastningsfönster och placerades i PRIO 5.")
            continue

        available_start = float(to_num(row.get("Tillgängligt saldo (Plock)", 0.0))) - float(
            to_num(row.get("Utbeställt", 0.0))
        )
        cumulative_need = 0.0
        previous_total_pallets = 0
        event_found = False

        for _, window_row in article_windows.iterrows():
            qty = float(window_row["_qty"])
            if qty <= 0:
                continue
            cumulative_need += qty
            cumulative_shortage = max(0.0, cumulative_need - available_start)
            total_pallets = int(math.ceil(cumulative_shortage / reference_float)) if cumulative_shortage > 0 else 0
            new_pallets = max(0, total_pallets - previous_total_pallets)
            previous_total_pallets = total_pallets
            if new_pallets <= 0:
                continue

            event_found = True
            prio = str(window_row["_prio"])
            prio_counts[prio][article] = max(prio_counts[prio].get(article, 0), new_pallets)
            pall_text = "pall" if new_pallets == 1 else "pallar"
            log_lines.append(
                f"Artikel {article} behöver {new_pallets} {pall_text} i lastningsfönster "
                f"{window_row['_window_label']} ({prio})."
            )

        if not event_found:
            prio_counts["PRIO 5"][article] = max(prio_counts["PRIO 5"].get(article, 0), 1)
            log_lines.append(f"Artikel {article} saknar beräknat påfyllningsfönster och placerades i PRIO 5.")

    bold_cells: set[tuple[int, int]] = set()
    for col_idx, prio in enumerate(PAFYLLNADSPRIO_COLUMNS[1:], start=1):
        counts = prio_counts[prio]
        multi_articles = sorted(
            [article for article, pallet_count in counts.items() if pallet_count > 1],
            key=lambda article: (-counts[article], article),
        )
        single_articles = sorted(article for article, pallet_count in counts.items() if pallet_count <= 1)
        ordered_articles = multi_articles + single_articles
        groups[prio] = ordered_articles
        for row_idx, article in enumerate(ordered_articles):
            if counts.get(article, 0) > 1:
                bold_cells.add((row_idx, col_idx))

    if window_map_log_lines:
        log_lines.append("Lastningsfönster per prio:")
        log_lines.extend(window_map_log_lines)

    return _build_pafyllnadsprio_dataframe(groups), bold_cells, log_lines, missing_reference_count, window_map_df


# ----------------------------------------------------------------------
# Observations (crowdsourcad pallid-historik) + GitHub-sync
# ----------------------------------------------------------------------

OBSERVATIONS_FILENAME = "observations.csv.gz"
OBSERVATIONS_COLS = ["artikelnummer", "pallid", "antal"]
GITHUB_REPO = "EmirKadr/flow"
GITHUB_OBS_BRANCH = "data/community-observations"
GITHUB_OBS_DIR = "warehouse_tools/vendor/lowfreqdata/buffertpall"
GITHUB_OBS_FILE = f"{GITHUB_OBS_DIR}/{_business_path_segment(DEFAULT_OBSERVATIONS_BUSINESS_CODE)}/observations.csv.gz"


def _observations_path() -> Path:
    """Returnera lokalt path for observations.csv.gz."""
    return business_observations_path(DEFAULT_OBSERVATIONS_BUSINESS_CODE)


def _artikel_max_path() -> Path:
    return business_artikel_max_path(DEFAULT_OBSERVATIONS_BUSINESS_CODE)


def _ensure_empty_observations(path: Path) -> Path:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=OBSERVATIONS_COLS).to_csv(
            path, index=False, compression="gzip"
        )
    return path


def _ensure_empty_artikel_max(path: Path) -> Path:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=["artikelnummer", "max", "pallid"]).to_csv(
            path, index=False, encoding="utf-8-sig"
        )
    return path


def business_observations_path(business_code: Optional[str] = None) -> Path:
    path = _seed_bufferpall_runtime_file(OBSERVATIONS_FILENAME, business_code)
    return _ensure_empty_observations(path)


def business_artikel_max_path(business_code: Optional[str] = None) -> Path:
    path = _seed_bufferpall_runtime_file("artikel_max.csv", business_code)
    return _ensure_empty_artikel_max(path)


def ensure_business_allocation_data_files(business_code: Optional[str] = None) -> Dict[str, str]:
    return {
        "observations_path": str(business_observations_path(business_code)),
        "article_max_path": str(business_artikel_max_path(business_code)),
    }


def _github_business_dir(business_code: Optional[str] = None) -> str:
    segment = _business_path_segment(business_code)
    return f"{GITHUB_OBS_DIR}/{segment}"


def _read_observations(path: Path) -> pd.DataFrame:
    if path.exists() and path.stat().st_size > 0:
        df = pd.read_csv(path, dtype=str)
        for col in OBSERVATIONS_COLS:
            if col not in df.columns:
                df[col] = ""
        return df[OBSERVATIONS_COLS]
    return pd.DataFrame(columns=OBSERVATIONS_COLS)


def _max_utan_outlier(grupp: pd.DataFrame) -> Tuple[float, str]:
    """Returnera (max, pallid) efter Tukey IQR-outlier-filter.

    grupp ska ha kolumner 'antal' och 'pallid' med unikt index.
    Filtret aktiveras bara nar gruppen har >2 pallar.
    """
    if len(grupp) > 2:
        q1, q3 = np.percentile(grupp["antal"], [25, 75])
        ovre = q3 + 1.5 * (q3 - q1)
        sub = grupp[grupp["antal"] <= ovre]
        if not sub.empty:
            row = sub.loc[sub["antal"].idxmax()]
            return float(row["antal"]), str(row["pallid"])
    row = grupp.loc[grupp["antal"].idxmax()]
    return float(row["antal"]), str(row["pallid"])


def _recompute_artikel_max(observations: pd.DataFrame, ut_path: Path) -> int:
    """Racka om artikel_max.csv fran observations. Returnerar antal artiklar."""
    if observations.empty:
        pd.DataFrame(columns=["artikelnummer", "max", "pallid"]).to_csv(
            ut_path, index=False, encoding="utf-8-sig"
        )
        return 0

    df = observations.copy()
    df["antal"] = pd.to_numeric(df["antal"], errors="coerce")
    df = df.dropna(subset=["artikelnummer", "antal", "pallid"])
    df["artikelnummer"] = df["artikelnummer"].astype(str).str.strip()
    df["pallid"] = df["pallid"].astype(str).str.strip()
    df = df.drop_duplicates(subset="pallid").reset_index(drop=True)

    rader = []
    for art, grupp in df.groupby("artikelnummer"):
        max_val, pall_id = _max_utan_outlier(grupp)
        rader.append({"artikelnummer": art, "max": max_val, "pallid": pall_id})

    pd.DataFrame(rader, columns=["artikelnummer", "max", "pallid"]).to_csv(
        ut_path, index=False, encoding="utf-8-sig"
    )
    return len(rader)


def _read_artikel_max(path: Path) -> pd.DataFrame:
    cols = ["artikelnummer", "max", "pallid"]
    if path.exists() and path.stat().st_size > 0:
        try:
            df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
        except Exception:
            return pd.DataFrame(columns=cols)
        for col in cols:
            if col not in df.columns:
                df[col] = ""
        return df[cols]
    return pd.DataFrame(columns=cols)


def _normalise_artikel_max_for_compare(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["artikelnummer", "max", "pallid"]
    if df is None or df.empty:
        return pd.DataFrame(columns=cols).set_index("artikelnummer")
    out = df.copy()
    for col in cols:
        if col not in out.columns:
            out[col] = ""
    out = out[cols]
    out["artikelnummer"] = out["artikelnummer"].astype(str).str.strip()
    out["pallid"] = out["pallid"].astype(str).str.strip()
    out["max"] = pd.to_numeric(out["max"], errors="coerce")
    out = out[out["artikelnummer"] != ""]
    return out.drop_duplicates(subset="artikelnummer", keep="first").set_index("artikelnummer")


def _same_article_max_value(before: float, after: float) -> bool:
    if pd.isna(before) and pd.isna(after):
        return True
    if pd.isna(before) or pd.isna(after):
        return False
    return float(before) == float(after)


def _format_article_max_value(value: float) -> str:
    if pd.isna(value):
        return ""
    value = float(value)
    return str(int(value)) if value.is_integer() else str(value)


def _artikel_max_change_summary(before: pd.DataFrame, after: pd.DataFrame) -> Dict[str, object]:
    before_norm = _normalise_artikel_max_for_compare(before)
    after_norm = _normalise_artikel_max_for_compare(after)
    before_articles = set(before_norm.index)
    after_articles = set(after_norm.index)
    common_articles = sorted(before_articles & after_articles)
    changed = []
    increased = 0
    decreased = 0

    for article in common_articles:
        before_value = before_norm.at[article, "max"]
        after_value = after_norm.at[article, "max"]
        if _same_article_max_value(before_value, after_value):
            continue
        if not pd.isna(before_value) and not pd.isna(after_value):
            if float(after_value) > float(before_value):
                increased += 1
            elif float(after_value) < float(before_value):
                decreased += 1
        changed.append({
            "artikelnummer": str(article),
            "before_max": _format_article_max_value(before_value),
            "after_max": _format_article_max_value(after_value),
            "before_pallid": str(before_norm.at[article, "pallid"]),
            "after_pallid": str(after_norm.at[article, "pallid"]),
        })

    return {
        "changed_rows": int(len(changed)),
        "increased_rows": int(increased),
        "decreased_rows": int(decreased),
        "new_article_rows": int(len(after_articles - before_articles)),
        "removed_article_rows": int(len(before_articles - after_articles)),
        "examples": changed[:5],
    }


def update_observations_from_buffer(
    buffer_raw: pd.DataFrame,
    observations_path: Optional[Path] = None,
    artikel_max_path: Optional[Path] = None,
) -> Tuple[int, pd.DataFrame]:
    """Lagg till nya status-30-pallid i observations.csv.gz och racka om artikel_max.csv.

    Returnerar (antal_nya, dataframe_med_endast_nya_rader).
    Endast pallar med Status == 30 sparas.
    """
    art_col = find_col(buffer_raw, BUFFER_SCHEMA["artikel"], required=False)
    qty_col = find_col(buffer_raw, BUFFER_SCHEMA["qty"], required=False)
    id_col = find_col(buffer_raw, BUFFER_SCHEMA["id"], required=False)
    status_col = find_col(buffer_raw, BUFFER_SCHEMA["status"], required=False)
    if not all([art_col, qty_col, id_col, status_col]):
        return 0, pd.DataFrame(columns=OBSERVATIONS_COLS)

    df = buffer_raw[[art_col, qty_col, id_col, status_col]].copy()
    df.columns = ["artikelnummer", "antal", "pallid", "status"]
    df["antal"] = pd.to_numeric(df["antal"], errors="coerce")
    df["status"] = pd.to_numeric(df["status"], errors="coerce")
    df = df.dropna(subset=["artikelnummer", "antal", "pallid", "status"])
    df = df[df["status"] == 30]
    df["artikelnummer"] = df["artikelnummer"].astype(str).str.strip()
    df["pallid"] = df["pallid"].astype(str).str.strip()
    df["antal"] = df["antal"].astype(int).astype(str)
    df = df[["artikelnummer", "pallid", "antal"]].drop_duplicates(subset="pallid")

    obs_path = Path(observations_path) if observations_path else _observations_path()
    max_path = Path(artikel_max_path) if artikel_max_path else _artikel_max_path()
    obs_path.parent.mkdir(parents=True, exist_ok=True)
    max_path.parent.mkdir(parents=True, exist_ok=True)
    befintliga = _read_observations(obs_path)
    befintliga_ids = set(befintliga["pallid"].astype(str))

    nya = df[~df["pallid"].isin(befintliga_ids)]
    if nya.empty:
        return 0, nya

    kombinerat = pd.concat([befintliga, nya], ignore_index=True)
    kombinerat.to_csv(obs_path, index=False, compression="gzip")
    _recompute_artikel_max(kombinerat, max_path)
    return len(nya), nya


def _github_token_path() -> Path:
    return _app_config_path()


def _load_github_token() -> Optional[str]:
    for env_key in ("OBSERVATIONS_GITHUB_TOKEN", "FLOW_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        token = os.environ.get(env_key, "").strip()
        if token:
            return token

    p = _github_token_path()
    if not p.exists():
        return None
    try:
        # utf-8-sig hanterar UTF-8 med BOM (PowerShell Out-File -Encoding utf8 skriver BOM)
        cfg = json.loads(p.read_text(encoding="utf-8-sig"))
        token = cfg.get("github_token", "").strip()
        return token or None
    except Exception:
        return None


def _github_request(url: str, method: str = "GET", token: Optional[str] = None,
                    payload: Optional[dict] = None, timeout: int = 15) -> Tuple[int, dict]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "flow-app"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
        except Exception:
            body = {}
        return e.code, body


def push_new_observations_to_github(nya: pd.DataFrame, business_code: Optional[str] = None) -> bool:
    """Pusha nya observationer till GitHub som en sessions-CSV. Tyst no-op om token saknas."""
    if nya is None or nya.empty:
        return False
    token = _load_github_token()
    if not token:
        return False
    try:
        from io import BytesIO
        import gzip
        buf = BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            gz.write(nya.to_csv(index=False).encode("utf-8"))
        gz_bytes = buf.getvalue()
    except Exception:
        return False

    user = re.sub(r"[^A-Za-z0-9_-]", "_", os.environ.get("USERNAME") or "user")
    ts = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    remote_dir = _github_business_dir(business_code)
    remote_name = f"{remote_dir}/observations_{user}_{ts}.csv.gz"
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{urllib.parse.quote(remote_name)}"
    business = _normalise_observations_business_code(business_code)
    payload = {
        "message": f"User observations {business} {user} {ts}",
        "content": base64.b64encode(gz_bytes).decode("ascii"),
        "branch": GITHUB_OBS_BRANCH,
    }
    status, _ = _github_request(api_url, method="PUT", token=token, payload=payload)
    return 200 <= status < 300


def fetch_observations_from_github(
    observations_path: Optional[Path] = None,
    artikel_max_path: Optional[Path] = None,
    remote_file: Optional[str] = None,
    push_orphaned: bool = True,
    business_code: Optional[str] = None,
) -> Tuple[int, int]:
    """Tvavags-sync med GitHub master:
    1. Hamta nya rader fran master och merga in i lokal observations.csv.gz
    2. Hitta orphaned lokala pallid (sparade offline / push misslyckats) och push:a dem

    Returnerar (antal_hamtade, antal_pushade_orphaned).
    Tyst no-op pa natfel, JSON-fel eller saknade kolumner.
    """
    if remote_file:
        remote_path = Path(remote_file)
        if not remote_path.exists():
            raise FileNotFoundError(f"Filen finns inte: {remote_path}")
        try:
            compression = "gzip" if remote_path.suffix.lower() == ".gz" else "infer"
            remote = pd.read_csv(remote_path, compression=compression, dtype=str)
        except Exception:
            return 0, 0
    else:
        github_file = f"{_github_business_dir(business_code)}/{OBSERVATIONS_FILENAME}"
        raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_OBS_BRANCH}/{github_file}"
        token = _load_github_token()
        headers = {"User-Agent": "flow-app"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(raw_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
        except Exception:
            return 0, 0

        from io import BytesIO
        try:
            remote = pd.read_csv(BytesIO(data), compression="gzip", dtype=str)
        except Exception:
            return 0, 0
    for col in OBSERVATIONS_COLS:
        if col not in remote.columns:
            return 0, 0
    remote = remote[OBSERVATIONS_COLS]

    obs_path = Path(observations_path) if observations_path else business_observations_path(business_code)
    max_path = Path(artikel_max_path) if artikel_max_path else business_artikel_max_path(business_code)
    obs_path.parent.mkdir(parents=True, exist_ok=True)
    max_path.parent.mkdir(parents=True, exist_ok=True)
    lokal = _read_observations(obs_path)
    remote_ids = set(remote["pallid"].astype(str))
    lokal_ids = set(lokal["pallid"].astype(str))

    # 1. Hamta nya rader fran master
    nya_fran_remote = remote[~remote["pallid"].astype(str).isin(lokal_ids)]
    n_hamtade = len(nya_fran_remote)
    if n_hamtade:
        kombinerat = pd.concat([lokal, nya_fran_remote], ignore_index=True)
        kombinerat.to_csv(obs_path, index=False, compression="gzip")
        _recompute_artikel_max(kombinerat, max_path)
        lokal = kombinerat

    # 2. Hitta orphaned lokala (finns lokalt, inte pa master) och push:a dem
    orphaned = lokal[~lokal["pallid"].astype(str).isin(remote_ids)]
    n_pushade = 0
    if push_orphaned and not orphaned.empty:
        try:
            if push_new_observations_to_github(orphaned, business_code=business_code):
                n_pushade = len(orphaned)
        except Exception:
            pass

    return n_hamtade, n_pushade


def utbest_per_article(saldo_df: pd.DataFrame) -> Dict[str, float]:
    """Summera 'utbeställt' per artikel från saldofilen.

    Returnerar tom dict om artikel- eller utbest-kolumn saknas.
    Inga bolagsfilter — alla rader summeras.
    """
    df = _clean_columns(saldo_df.copy())
    art_col = find_col(df, ["artikel", "artnr", "art.nr", "artikelnummer", "sku"], required=False)
    utbest_col = find_col(df, ["utbeställt", "utbestallt"], required=False)
    if not art_col or not utbest_col:
        return {}
    tmp = pd.DataFrame({
        "_art": _safe_str_series(df[art_col]),
        "_utbest": df[utbest_col].map(to_num).fillna(0.0),
    })
    return tmp.groupby("_art")["_utbest"].sum().to_dict()


def compute_lyx_articles(saldo_df: pd.DataFrame, max_df: pd.DataFrame) -> Tuple[list[str], int]:
    """
    Returnera artikelnummer där (plocksaldo + utbeställt) är högst 20 % av
    max buffertantalet. Returvärdet är (artikellista, antal filtrerade rader).
    """
    saldo_df = _clean_columns(saldo_df.copy())
    max_df = _clean_columns(max_df.copy())

    art_col = find_col(saldo_df, ["artikel", "artnr", "art.nr", "artikelnummer", "sku"])
    saldo_col = find_col(
        saldo_df,
        ["plocksaldo", "plock saldo", "plock-saldo", "tillgängligt plock", "tillgangligt plock", "plock"],
        required=False,
    )
    plats_col = find_col(
        saldo_df,
        ["plockplats", "huvudplock", "mainpick", "hyllplats", "bin", "location", "lagerplats"],
        required=False,
    )
    bolag_col = find_col(saldo_df, ["bolag", "company", "bolagskod"], required=False)
    utbest_col = find_col(saldo_df, ["utbeställt", "utbestallt"], required=False)

    if saldo_col is None:
        raise KeyError("Kunde inte hitta plocksaldo-kolumnen i saldofilen.")

    mask = pd.Series(True, index=saldo_df.index)
    if plats_col:
        mask &= _safe_str_series(saldo_df[plats_col]).ne("")
    if bolag_col:
        mask &= _safe_str_series(saldo_df[bolag_col]).str.upper() == "MG"

    saldo_filt = saldo_df[mask].copy()
    if saldo_filt.empty:
        return [], 0

    saldo_filt["_art"] = _safe_str_series(saldo_filt[art_col])
    saldo_filt["_saldo"] = saldo_filt[saldo_col].map(to_num).fillna(0)
    if utbest_col:
        saldo_filt["_utbest"] = saldo_filt[utbest_col].map(to_num).fillna(0)
    else:
        saldo_filt["_utbest"] = 0.0
    saldo_filt["_total"] = saldo_filt["_saldo"] + saldo_filt["_utbest"]

    max_map = _build_article_max_map(max_df)

    saldo_filt["_max"] = saldo_filt["_art"].map(max_map)
    lyx_mask = saldo_filt["_max"].notna() & (saldo_filt["_total"] <= saldo_filt["_max"] * 0.20)
    lyx_arts = sorted(saldo_filt.loc[lyx_mask, "_art"].unique().tolist())
    return lyx_arts, len(saldo_filt)

def _read_not_putaway_csv(path: str) -> pd.DataFrame:
    """Läs CSV för 'Ej inlagrade'. Försök auto-separator, fallback TAB."""
    try:
        df = pd.read_csv(path, dtype=str, sep=None, engine="python", encoding="utf-8-sig")
        if df.shape[1] == 1 and len(df):
            first = str(df.iloc[0, 0])
            if "\t" in first:
                df = pd.read_csv(path, dtype=str, sep="\t", engine="python", encoding="utf-8-sig")
        return _clean_columns(df)
    except Exception:
        return _clean_columns(pd.read_csv(path, dtype=str, sep="\t", engine="python", encoding="utf-8-sig"))

def normalize_not_putaway(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Mappa 'Ej inlagrade' till enkel struktur. Ingen påverkan på allokering/refill."""
    df = df_raw.copy()
    def col(key: str, required: bool, default=None) -> str:
        return find_col(df, NOT_PUTAWAY_SCHEMA[key], required=required, default=default)
    art_col  = col("artikel", True)
    name_col = col("namn", False, default=None)
    qty_col  = col("antal", True)
    st_col   = col("status", False, default=None)
    pall_col = col("pallnr", False, default=None)
    sscc_col = col("sscc", False, default=None)
    chg_col  = col("andrad", False, default=None)
    exp_col  = col("utgang", False, default=None)
    out = pd.DataFrame({
        "Artikel": df[art_col].astype(str).str.strip(),
        "Namn":    df[name_col].astype(str).str.strip() if name_col else "",
        "Antal":   df[qty_col].map(to_num).astype(float),
        "Status":  pd.to_numeric(df[st_col], errors="coerce") if st_col else pd.Series([np.nan]*len(df)),
        "Pall nr": df[pall_col].astype(str) if pall_col else "",
        "SSCC":    df[sscc_col].astype(str) if sscc_col else "",
        "Ändrad":  smart_to_datetime(df[chg_col]) if chg_col else pd.NaT,
        "Utgång":  smart_to_datetime(df[exp_col]) if exp_col else pd.NaT,
    })
    for c in ["Namn","Pall nr","SSCC"]:
        if c in out.columns: out[c] = out[c].fillna("").astype(str).str.strip()
    return out


def normalize_saldo(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Mappa saldofil till struktur per artikel: Plocksaldo (sum) + Plockplats (första icke-tom)."""
    df = _clean_columns(df_raw.copy())
    def col(key: str, required: bool, default=None) -> str:
        return find_col(df, SALDO_SCHEMA[key], required=required, default=default)
    art_col   = col("artikel", True)
    saldo_col = col("plocksaldo", False, default=None)
    plats_col = col("plockplats", False, default=None)

    if saldo_col is None:
        return pd.DataFrame(columns=["Artikel", "Plocksaldo", "Plockplats"])

    out = pd.DataFrame({
        "Artikel": df[art_col].astype(str).str.strip(),
        "Plocksaldo": pd.to_numeric(df[saldo_col].map(to_num), errors="coerce").fillna(0.0),
        "Plockplats": (df[plats_col].astype(str).str.strip() if plats_col else pd.Series([""]*len(df))),
    })
    agg = (out.groupby("Artikel", as_index=False)
              .agg({"Plocksaldo":"sum","Plockplats":lambda s: next((x for x in s if isinstance(x,str) and x.strip()), "")}))
    return agg


PICK_LOG_SCHEMA: dict[str, list[str]] = {
    "artikel": ["artikel", "artikelnr", "artnr", "art.nr", "artikelnummer", "sku", "article"],
    "antal":   ["plockat", "antal", "quantity", "qty", "picked", "units"],
    "datum":   ["datum", "datumtid", "timestamp", "date", "tid", "time"]
}

def normalize_pick_log(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Normalisera plocklogg.
    Ut: Artikelnummer[str], Artikel[str] (namn eller =Artikelnummer om saknas),
        Plockat[float≥0], Datum[datetime].
    """
    df = _clean_columns(df_raw.copy())

    art_col = find_col(df, PICK_LOG_SCHEMA["artikel"], required=True)
    qty_col = find_col(df, PICK_LOG_SCHEMA["antal"], required=True)
    dt_col  = find_col(df, PICK_LOG_SCHEMA["datum"], required=True)

    name_col = None
    for cand in ["artikelnamn","namn","benämning","artikelbenämning","produktnamn"]:
        try:
            nc = find_col(df, [cand], required=False, default=None)
            if nc:
                name_col = nc
                break
        except KeyError:
            pass

    out = pd.DataFrame({
        "Artikelnummer": df[art_col].astype(str).str.strip(),
        "Plockat": pd.to_numeric(df[qty_col].map(to_num), errors="coerce").fillna(0.0).astype(float),
        "Datum": smart_to_datetime(df[dt_col])
    })

    if name_col:
        out["Artikel"] = df[name_col].astype(str).str.strip()
    else:
        out["Artikel"] = out["Artikelnummer"]

    return out

def compute_sales_metrics(df_norm: pd.DataFrame, today=None) -> pd.DataFrame:
    """
    Beräkna sales-mått per Artikelnummer.
    Kolumner:
      - Artikelnummer, Artikel
      - Total_7, Total_30, Total_90
      - ADV_30 (=Total_30/30), ADV_90 (=Total_90/90)
      - SenastPlockad, DagarSedanSenast
      - UnikaPlockdagar_90 (unika datum med Plockat>0 sista 90)
      - NollraderPerPlockdag_90 (medel antal rader med Plockat=0 per aktiv plockdag sista 90)
      - ABC_klass (Pareto på Total_90; 80/15/5 → A/B/C)
    """
    if df_norm is None or df_norm.empty:
        cols = [
            "Artikelnummer","Artikel","Total_7","Total_30","Total_90","ADV_30","ADV_90",
            "SenastPlockad","DagarSedanSenast","UnikaPlockdagar_90","NollraderPerPlockdag_90","ABC_klass"
        ]
        return pd.DataFrame(columns=cols)

    if today is None:
        today = pd.Timestamp.now().normalize()
    else:
        today = pd.to_datetime(today).normalize()

    df = df_norm.copy()
    df["DatumNorm"] = pd.to_datetime(df["Datum"]).dt.normalize()
    df["Plockat"] = pd.to_numeric(df["Plockat"], errors="coerce").fillna(0.0)

    mask7  = df["DatumNorm"] >= (today - pd.Timedelta(days=7))
    mask30 = df["DatumNorm"] >= (today - pd.Timedelta(days=30))
    mask90 = df["DatumNorm"] >= (today - pd.Timedelta(days=90))

    total7  = df.loc[mask7].groupby("Artikelnummer")["Plockat"].sum()
    total30 = df.loc[mask30].groupby("Artikelnummer")["Plockat"].sum()
    total90 = df.loc[mask90].groupby("Artikelnummer")["Plockat"].sum()

    positive = df[df["Plockat"] > 0]
    last_pick = positive.groupby("Artikelnummer")["DatumNorm"].max() if not positive.empty else pd.Series(dtype="datetime64[ns]")
    last_pick = last_pick.reindex(df["Artikelnummer"].unique())

    days_since = (today - last_pick).dt.days
    days_since = days_since.where(~days_since.isna(), other=pd.NA)

    sub90_pos = df.loc[mask90 & (df["Plockat"] > 0)]
    unique_days_90 = sub90_pos.groupby("Artikelnummer")["DatumNorm"].nunique()

    sub90 = df.loc[mask90].copy()
    zero_rows = (sub90.assign(IsZero=(sub90["Plockat"]==0))
                        .groupby(["Artikelnummer","DatumNorm"])["IsZero"].sum()
                        .rename("ZeroRows"))
    zero_avg = zero_rows.reset_index().groupby("Artikelnummer")["ZeroRows"].mean()
    zero_avg = zero_avg.reindex(df["Artikelnummer"].unique()).fillna(0.0)

    idx = pd.Index(sorted(df["Artikelnummer"].astype(str).unique()), name="Artikelnummer")
    out = pd.DataFrame(index=idx)
    out["Total_7"]  = total7.reindex(idx).fillna(0).round().astype(int)
    out["Total_30"] = total30.reindex(idx).fillna(0).round().astype(int)
    out["Total_90"] = total90.reindex(idx).fillna(0).round().astype(int)
    out["ADV_30"] = (out["Total_30"] / 30.0).astype(float)
    out["ADV_90"] = (out["Total_90"] / 90.0).astype(float)
    out["SenastPlockad"] = last_pick.reindex(idx)
    out["DagarSedanSenast"] = days_since.reindex(idx)
    out["UnikaPlockdagar_90"] = unique_days_90.reindex(idx).fillna(0).astype(int)
    out["NollraderPerPlockdag_90"] = zero_avg.reindex(idx).fillna(0.0).astype(float)

    tmp = out["Total_90"].astype(float).sort_values(ascending=False)
    total_sum = float(tmp.sum())
    if total_sum <= 0:
        out["ABC_klass"] = "C"
    else:
        cum = tmp.cumsum() / total_sum
        cls = pd.Series(index=tmp.index, dtype=object)
        cls[cum <= 0.80] = "A"
        cls[(cum > 0.80) & (cum <= 0.95)] = "B"
        cls[cum > 0.95] = "C"
        out["ABC_klass"] = cls.reindex(out.index).fillna("C")

    out = out.reset_index()

    if "Artikel" in df_norm.columns:
        out = out.merge(df_norm[["Artikelnummer","Artikel"]].drop_duplicates(),
                        on="Artikelnummer", how="left")
    else:
        out["Artikel"] = out["Artikelnummer"]

    cols = ["Artikelnummer","Artikel"] + [c for c in out.columns if c not in ["Artikelnummer","Artikel"]]
    out = out[cols]

    return out


def _open_sales_excel(df_or_dict, label: str = "sales") -> str:
    """Skriv DF eller {blad: DF} till temporär Excel/CSV och öppna (med säkra bladnamn)."""
    import importlib

    def _sanitize_sheet_name(name: str) -> str:
        s = str(name)
        for ch in ['\\', '/', '?', '*', ':', '[', ']']:
            s = s.replace(ch, '-')
        s = s.strip("'")  # ledande/avslutande apostrof ställer också till det
        if not s:
            s = "Sheet"
        return s[:31]

    def _dedupe(name: str, used: set[str]) -> str:
        base = name
        n = 2
        out = name
        while out in used:
            suffix = f" ({n})"
            out = (base[:31 - len(suffix)] + suffix)
            n += 1
        used.add(out)
        return out

    if isinstance(df_or_dict, dict):
        engine = None
        if importlib.util.find_spec("openpyxl"):
            engine = "openpyxl"
        elif importlib.util.find_spec("xlsxwriter"):
            engine = "xlsxwriter"
        else:
            raise RuntimeError("Saknar Excel-skrivare (installera 'openpyxl' eller 'xlsxwriter').")

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{label}.xlsx")
        path = tmp.name; tmp.close()
        used_names: set[str] = set()
        with pd.ExcelWriter(path, engine=engine) as writer:
            for sheet, d in df_or_dict.items():
                safe = _sanitize_sheet_name(sheet)
                safe = _dedupe(safe, used_names)
                dd = d if isinstance(d, pd.DataFrame) else pd.DataFrame(d)
                dd.to_excel(writer, sheet_name=safe, index=False)
    else:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{label}.csv")
        path = tmp.name; tmp.close()
        (df_or_dict if isinstance(df_or_dict, pd.DataFrame) else pd.DataFrame(df_or_dict)).to_csv(path, index=False, encoding="utf-8-sig")

    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass
    return path

def annotate_refill(refill_df: pd.DataFrame, df_metrics: pd.DataFrame) -> pd.DataFrame:
    """
    Lägg på sales-kolumner i refill-blad (påverkar inte logiken). Returnerar nytt DF.
    Adderar: ADV_90, ABC_klass, DagarSedanSenast, UnikaPlockdagar_90, NollraderPerPlockdag_90
    """
    if refill_df is None or refill_df.empty or df_metrics is None or df_metrics.empty:
        return refill_df
    cols = ["Artikel", "ADV_90", "ABC_klass", "DagarSedanSenast", "UnikaPlockdagar_90", "NollraderPerPlockdag_90"]
    cols = [c for c in cols if c in df_metrics.columns or c == "Artikel"]
    out = refill_df.merge(df_metrics[cols], on="Artikel", how="left")
    return out


def normalize_items(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Normalisera item-fil för att extrahera artikelnummer och staplingsbar-flagga.
    Returnerar DataFrame med kolumner ["Artikel", "Staplingsbar"].

    Parametrar:
        df_raw: O-normaliserad DataFrame från item-CSV.
    """
    if df_raw is None or df_raw.empty:
        return pd.DataFrame(columns=["Artikel", "Staplingsbar"])
    df = df_raw.copy()
    df = _clean_columns(df)
    try:
        art_col = find_col(df, ITEM_SCHEMA["artikel"], required=True)
    except Exception:
        art_col = None
    try:
        stap_col = find_col(df, ITEM_SCHEMA["staplingsbar"], required=False, default=None)
    except Exception:
        stap_col = None
    if not art_col:
        return pd.DataFrame(columns=["Artikel", "Staplingsbar"])
    if not stap_col or stap_col not in df.columns:
        tmp = df[[art_col]].copy()
        tmp.columns = ["Artikel"]
        tmp["Ej Staplingsbar"] = ""
        return tmp.drop_duplicates(subset=["Artikel"]).reset_index(drop=True)
    tmp = df[[art_col, stap_col]].copy()
    tmp.columns = ["Artikel", "Ej Staplingsbar"]
    tmp["Artikel"] = tmp["Artikel"].astype(str).str.strip()
    tmp["Ej Staplingsbar"] = tmp["Ej Staplingsbar"].fillna("").astype(str).str.strip()
    return tmp.drop_duplicates(subset=["Artikel"]).reset_index(drop=True)


def compute_pallet_spaces(result_df: pd.DataFrame) -> pd.DataFrame:
    """
    Beräkna pallplatsbehov per kund baserat på allokeringsresultatet.

    Parametrar:
        result_df: DataFrame med allokerade orderrader efter saldofil-omklassificering och item/ej staplingsbar-sammanfogning.

    Returnerar:
        Ett DataFrame med pallplatser per kund, inklusive separata delkolumner for t.ex. Plockpall, autostore och HIB.
        Om nödvändiga kolumner saknas returneras ett tomt DataFrame.
    """
    if result_df is None or result_df.empty:
        return pd.DataFrame(columns=["Kund", "Kund1", "Botten Pallar", "Topp Pallar", "Totalt Pallar", "Pallplatser"])
    df = result_df.copy()
    try:
        kund_col = find_col(df, ["kund", "customer", "kundnr", "kund nr", "kundnummer", "kund-id", "kundid"], required=True)
    except Exception:
        print(f"[compute_pallet_spaces] Kunde inte hitta kund-kolumn. Tillgängliga: {list(df.columns)}")
        return pd.DataFrame(columns=["Kund", "Kund1", "Botten Pallar", "Topp Pallar", "Totalt Pallar", "Pallplatser"])
    try:
        kund1_col = find_col(df, ["kund1", "kund 1", "customer1", "kund.1"], required=False, default=None)
    except Exception:
        kund1_col = None

    # Fallback: om primär kund-kolumn är helt tom men Kund.1 har värden, använd Kund.1 istället
    if kund_col and kund_col in df.columns:
        non_empty = df[kund_col].fillna("").astype(str).str.strip().ne("").sum()
        if non_empty == 0 and kund1_col and kund1_col in df.columns:
            kund_col, kund1_col = kund1_col, None

    zone_col = "Zon (beräknad)" if "Zon (beräknad)" in df.columns else None
    stack_col = None
    try:
        stack_col = find_col(df, ["ej staplingsbar", "ejstaplingsbar", "staplingsbar", "staplings bar"], required=False, default=None)
    except Exception:
        stack_col = None
    palltyp_col = "Palltyp (matchad)" if "Palltyp (matchad)" in df.columns else None
    if zone_col is None or palltyp_col is None:
        print(f"[compute_pallet_spaces] Saknar kolumn: zone_col={zone_col}, palltyp_col={palltyp_col}. Tillgängliga: {list(df.columns)}")
        return pd.DataFrame(columns=["Kund", "Kund1", "Botten Pallar", "Topp Pallar", "Totalt Pallar", "Pallplatser"])

    df[zone_col] = df[zone_col].fillna("").astype(str).str.strip().str.upper()
    if stack_col:
        df[stack_col] = df[stack_col].fillna("").astype(str).str.strip().str.upper()
    else:
        df["_stack_tmp"] = ""
        stack_col = "_stack_tmp"
    df[palltyp_col] = df[palltyp_col].fillna("").astype(str).str.strip().str.upper()

    art_col_ps = None
    try:
        art_col_ps = find_col(df, ORDER_SCHEMA["artikel"], required=False, default=None)
    except Exception:
        art_col_ps = None
    if kund1_col is None:
        groups = df.groupby(kund_col)
    else:
        groups = df.groupby([kund_col, kund1_col])
    records: list[dict] = []
    import math
    for keys, sub in groups:
        if kund1_col is None:
            kund_val = keys
            kund1_val = ""
        else:
            kund_val, kund1_val = keys
        mask_bottom = (sub[zone_col] == "H") & ((sub[stack_col] == "N") | (sub[stack_col] == ""))
        B = int(mask_bottom.sum())
        rows_A = int((sub[zone_col] == "A").sum())
        if rows_A > 0:
            top_A = math.ceil(rows_A / 20.0)
        else:
            top_A = 0
        mask_topH = (sub[zone_col] == "H") & (sub[stack_col] == "Y") & (sub[palltyp_col] != "SJÖ")
        top_H = int(mask_topH.sum())
        rows_F = int((sub[zone_col] == "F").sum())
        if rows_F > 0:
            top_F = math.ceil(rows_F / 20.0)
        else:
            top_F = 0
        mask_rf = sub[zone_col] == "R"
        if art_col_ps and art_col_ps in sub.columns:
            mask_rf = mask_rf & ~sub[art_col_ps].astype(str).str.strip().isin(RF_PALLPLATS_EXCLUDE_ARTICLES)
        rows_R = int(mask_rf.sum())
        if rows_R < 27:
            top_R = 0
        elif rows_R <= 96:
            top_R = 1
        elif rows_R <= 163:
            top_R = 2
        elif rows_R <= 204:
            top_R = 3
        else:
            top_R = 4
        rows_S = int((sub[zone_col] == "S").sum())
        if rows_S == 0:
            top_S = 0
        elif rows_S <= 10:
            top_S = 1
        elif rows_S <= 15:
            top_S = 2
        elif rows_S <= 20:
            top_S = 3
        elif rows_S <= 26:
            top_S = 4
        else:
            top_S = 5
        mask_sjo = (sub[zone_col] == "H") & (sub[palltyp_col] == "SJÖ")
        S_rows = int(mask_sjo.sum())
        T = top_A + top_H + top_R + top_S + top_F
        half_sum = (B + T) / 2.0
        P_component = math.ceil(half_sum)
        max_val = T if T > P_component else P_component
        P = max_val + 2 * S_rows
        total_pallar = B + T + S_rows
        helpall_stapelbar = B
        helpall_ej_stapelbar = top_H
        sjo_pall = S_rows
        skrymme_pallar = top_S
        plockpall = top_A
        autostore_pallar = top_R
        hib_pallar = top_F
        record = {
            "Kund": kund_val,
            "Kund1": kund1_val,
            "hellpall stapelbar": helpall_stapelbar,
            "hellpall ej stapelbar": helpall_ej_stapelbar,
            "Sjö pall": sjo_pall,
            "Skrymme": skrymme_pallar,
            "Plockpall": plockpall,
            "autostore": autostore_pallar,
            "HIB": hib_pallar,
            "Botten Pallar": B,
            "Topp Pallar": T,
            "Totalt Pallar": total_pallar,
            "Pallplatser": P
        }
        records.append(record)
    return pd.DataFrame(records)


def _safe_str_series(s: pd.Series) -> pd.Series:
    """
    Returnera en strängserie där varje värde är trimmat och NaN ersätts med tom sträng.
    """
    return s.fillna("").astype(str).str.strip()


def _str_to_num(x) -> float:
    """
    Extrahera första numeriska värdet ur ett godtyckligt objekt/sträng och returnera som float.
    Saknas numeriskt värde → 0.0.
    """
    import re
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return 0.0
    s = str(x).replace(" ", "").replace(",", ".")
    m = re.search(r"[-+]?\d*\.?\d+", s)
    return float(m.group()) if m else 0.0


def _num_series(s: pd.Series) -> pd.Series:
    """
    Konvertera en Serie till numeriska värden med hjälp av _str_to_num. NaN ersätts med 0.
    """
    return pd.to_numeric(s.map(_str_to_num), errors="coerce").fillna(0)


def _sum_not_putaway(not_putaway_df: Optional[pd.DataFrame]) -> pd.Series:
    """
    Summera kolumnen 'Antal' per artikel i en normaliserad ej-inlagrade-DataFrame.
    Returnerar en Series med artikelnummer som index och summa antal som värde.
    Om underlaget saknas eller fel format returneras en tom Series.
    """
    if not isinstance(not_putaway_df, pd.DataFrame) or not len(not_putaway_df):
        return pd.Series(dtype=float)
    df = not_putaway_df.copy()
    if "Artikel" not in df.columns or "Antal" not in df.columns:
        return pd.Series(dtype=float)
    df["Artikel"] = _safe_str_series(df["Artikel"])
    df["Antal"] = _num_series(df["Antal"])
    return df.groupby("Artikel")["Antal"].sum()


def _collect_exclude_source_ids(allocated_df: Optional[pd.DataFrame]) -> set[str]:
    """
    Samla ihop de käll-ID:n från en allokerad DataFrame som motsvarar HELPALL-rader.
    Dessa ID används för att exkludera källor i refill/FIFO-beräkningen.
    """
    exclude: set[str] = set()
    if isinstance(allocated_df, pd.DataFrame) and not allocated_df.empty:
        if "Källtyp" in allocated_df.columns and "Källa" in allocated_df.columns:
            mask = _safe_str_series(allocated_df["Källtyp"]) == "HELPALL"
            vals = _safe_str_series(allocated_df.loc[mask, "Källa"]).replace("", pd.NA).dropna().unique().tolist()
            exclude = set(vals)
    return exclude


def _fifo_pallar_for_article(buffer_df: Optional[pd.DataFrame], article: str, needed_units: float, exclude_source_ids: Optional[set[str]] = None) -> float:
    """
    FIFO-baserad beräkning för hur många pallar som behövs för att täcka 'needed_units' av en given artikel.
    Filtrerar bufferten enligt REFILL_BUFFER_STATUSES och exkluderar angivna käll-ID.
    Returnerar ett flyttal med antalet pallar (heltal). Om inget behövs → 0. Om underlag saknas → NaN.
    """
    if needed_units <= 0:
        return 0.0
    if not isinstance(buffer_df, pd.DataFrame) or buffer_df.empty:
        return np.nan
    df = buffer_df.copy()
    try:
        df.rename(columns=lambda c: str(c).replace("\ufeff", "").strip(), inplace=True)
    except Exception:
        pass
    try:
        art_col = find_col(df, BUFFER_SCHEMA["artikel"], required=True)
        qty_col = find_col(df, BUFFER_SCHEMA["qty"], required=True)
        dt_col = find_col(df, BUFFER_SCHEMA["dt"], required=False, default=None)
        status_col = find_col(df, BUFFER_SCHEMA["status"], required=False, default=None)
        id_col = find_col(df, BUFFER_SCHEMA["id"], required=False, default=None)
    except Exception:
        return np.nan
    sub = df.loc[_safe_str_series(df[art_col]) == str(article)].copy()
    if sub.empty:
        return 0.0
    if status_col and status_col in sub.columns:
        s = _safe_str_series(sub[status_col])
        s_num = pd.to_numeric(s.str.extract(r"(-?\d+)")[0], errors="coerce")
        allowed_str = {str(x) for x in REFILL_BUFFER_STATUSES}
        sub = sub[s.isin(allowed_str) | s_num.isin(REFILL_BUFFER_STATUSES)].copy()
        if sub.empty:
            return 0.0
    if exclude_source_ids:
        if id_col and id_col in sub.columns:
            sub["_source_id"] = _safe_str_series(sub[id_col])
        else:
            sub["_source_id"] = "SRC-" + sub.index.astype(str)
        sub = sub[~sub["_source_id"].isin(exclude_source_ids)].copy()
        if sub.empty:
            return 0.0
    sub["__qty__"] = _num_series(sub[qty_col])
    if dt_col and dt_col in sub.columns:
        sub = sub.sort_values(dt_col, kind="mergesort", na_position="last")
    acc = 0.0
    pall_count = 0
    for q in sub["__qty__"]:
        if q <= 0:
            continue
        acc += float(q)
        pall_count += 1
        if acc >= float(needed_units):
            break
    if pall_count == 0:
        return 0.0
    return float(pall_count)


def build_prognos_vs_autoplock_report(
    prognos_df: pd.DataFrame,
    saldo_norm_df: Optional[pd.DataFrame] = None,
    buffer_df: Optional[pd.DataFrame] = None,
    *,
    exclude_source_ids: Optional[set[str]] = None,
    allocated_df: Optional[pd.DataFrame] = None,
) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """
    Bygg en rapport som jämför prognosens behov med saldo i autoplock och buffertpallar (FIFO‑baserad
    pallberäkning). Kolumnen för ej inlagrade artiklar (E) har tagits bort.
    Returnerar ett DataFrame med kolumnerna A–D samt F och en meta‑dikt som anger om rapporten är
    partiell och eventuella notes om vad som saknas.
    """
    meta: Dict[str, str] = {"partial": "no", "missing": "", "note": ""}
    missing: List[str] = []
    if not isinstance(prognos_df, pd.DataFrame) or prognos_df.empty:
        empty = pd.DataFrame(columns=[
            "Artikelnummer",
            "Behov i prognosen (antal styck)",
            "Saldo i autoplock",
            "Behov efter saldo",
            "Summa antal i ej inlagrade artiklar",
            "FIFO-baserad beräkning (antal pall)",
        ])
        meta.update({"partial": "yes", "missing": "prognos", "note": "Ingen prognos inläst."})
        return empty, meta
    pr = prognos_df.copy()
    if "Artikelnummer" not in pr.columns or "Antal styck" not in pr.columns:
        rename_map: Dict[str, str] = {}
        for col in pr.columns:
            lc = str(col).strip().lower()
            if lc in ("product code", "artikelnummer", "artnr", "sku", "article"):
                rename_map[col] = "Artikelnummer"
            elif lc in ("antal styck", "antal", "qty", "quantity"):
                rename_map[col] = "Antal styck"
        if rename_map:
            pr = pr.rename(columns=rename_map)
    pr["Artikelnummer"] = _safe_str_series(pr.get("Artikelnummer", ""))
    pr["Antal styck"] = _num_series(pr.get("Antal styck", 0))
    if isinstance(saldo_norm_df, pd.DataFrame) and not saldo_norm_df.empty:
        orig_cols = [str(c).strip().lower() for c in saldo_norm_df.columns]
        has_robot_col = any("robot" == c for c in orig_cols)
        if not has_robot_col:
            missing.append("saldo")
            pr["Robot"] = "N"
            pr["Saldo i autoplock"] = 0.0
        else:
            s = saldo_norm_df.copy()
            if "Artikel" not in s.columns:
                for c in s.columns:
                    lc = str(c).strip().lower()
                    if lc in ("artikel", "artikelnummer", "sku", "artnr", "art.nr", "article"):
                        s = s.rename(columns={c: "Artikel"})
                        break
            if "Robot" not in s.columns:
                s["Robot"] = "N"
            if "Saldo autoplock" not in s.columns:
                s["Saldo autoplock"] = 0.0
            s["Artikel"] = _safe_str_series(s["Artikel"])
            s["Robot"] = _safe_str_series(s["Robot"]).str.upper().map(lambda x: "Y" if x == "Y" else "N")
            s["Saldo autoplock"] = _num_series(s["Saldo autoplock"])
            pr = pr.merge(s[["Artikel", "Robot", "Saldo autoplock"]], left_on="Artikelnummer", right_on="Artikel", how="left")
            pr = pr.drop(columns=["Artikel"], errors="ignore")
            pr["Robot"] = pr["Robot"].fillna("N")
            pr["Saldo i autoplock"] = pr["Saldo autoplock"].fillna(0.0)
    else:
        missing.append("saldo")
        pr["Robot"] = "N"
        pr["Saldo i autoplock"] = 0.0
    pr["Behov i prognosen (antal styck)"] = _num_series(pr["Antal styck"])
    pr["Saldo i autoplock"] = _num_series(pr["Saldo i autoplock"])
    pr["Behov efter saldo"] = (pr["Behov i prognosen (antal styck)"] - pr["Saldo i autoplock"]).clip(lower=0)
    pr["Summa antal i ej inlagrade artiklar"] = 0.0
    shortage = pr["Behov efter saldo"].copy()
    if exclude_source_ids is None and isinstance(allocated_df, pd.DataFrame):
        exclude_source_ids = _collect_exclude_source_ids(allocated_df)
    if not exclude_source_ids:
        exclude_source_ids = None
    if isinstance(buffer_df, pd.DataFrame) and not buffer_df.empty:
        buf = buffer_df.copy()
        try:
            buf.rename(columns=lambda c: str(c).replace("\ufeff", "").strip(), inplace=True)
        except Exception:
            pass
        try:
            art_col = find_col(buf, BUFFER_SCHEMA["artikel"], required=True)
            qty_col = find_col(buf, BUFFER_SCHEMA["qty"], required=True)
            dt_col = find_col(buf, BUFFER_SCHEMA["dt"], required=False, default=None)
            status_col = find_col(buf, BUFFER_SCHEMA["status"], required=False, default=None)
            id_col = find_col(buf, BUFFER_SCHEMA["id"], required=False, default=None)
        except Exception:
            missing.append("buffert")
            pr["FIFO-baserad beräkning (antal pall)"] = np.nan
            pr["Buffertsaldo (status 29,30)"] = 0.0
        if status_col and status_col in buf.columns:
            s_str = _safe_str_series(buf[status_col])
            s_num = pd.to_numeric(s_str.str.extract(r"(-?\d+)")[0], errors="coerce")
            allowed_str = {str(x) for x in REFILL_BUFFER_STATUSES}
            mask_status = s_str.isin(allowed_str) | s_num.isin(REFILL_BUFFER_STATUSES)
            buf = buf.loc[mask_status].copy()
        if exclude_source_ids:
            if id_col and id_col in buf.columns:
                buf["_source_id"] = _safe_str_series(buf[id_col])
            else:
                buf["_source_id"] = "SRC-" + buf.index.astype(str)
            buf = buf[~buf["_source_id"].isin(exclude_source_ids)].copy()
        buf["__qty__"] = _num_series(buf[qty_col])
        prefix_dict: Dict[str, np.ndarray] = {}
        if dt_col and dt_col in buf.columns:
            buf = buf.sort_values([art_col, dt_col], kind="mergesort", na_position="last")
        for art, group in buf.groupby(buf[art_col]):
            qty_vals = group["__qty__"].to_numpy()
            if qty_vals.size == 0:
                continue
            prefix = np.cumsum(qty_vals)
            prefix_dict[str(art)] = prefix

        buffer_sum_series = buf.groupby(buf[art_col])["__qty__"].sum()
        buffer_sum_dict = {str(k): v for k, v in buffer_sum_series.items()}
        pr["Buffertsaldo (status 29,30)"] = pr["Artikelnummer"].map(lambda x: buffer_sum_dict.get(str(x), 0.0))
        def calc_pallar(art: Any, need: float) -> float:
            if need <= 0:
                return 0.0
            pref = prefix_dict.get(str(art))
            if pref is None:
                return 0.0
            idx = np.searchsorted(pref, float(need), side="left")
            if idx >= len(pref):
                return float(len(pref))
            else:
                return float(idx + 1)
        pr["FIFO-baserad beräkning (antal pall)"] = [calc_pallar(a, n) for a, n in zip(pr["Artikelnummer"], shortage)]
    else:
        missing.append("buffert")
        pr["FIFO-baserad beräkning (antal pall)"] = np.nan
        pr["Buffertsaldo (status 29,30)"] = 0.0
    pr = pr.loc[(pr["Robot"].astype(str).str.upper() == "Y") & (pr["Behov efter saldo"] > 0)].copy()
    out_cols = [
        "Artikelnummer",
        "Behov i prognosen (antal styck)",
        "Saldo i autoplock",
        "Behov efter saldo",
        "Buffertsaldo (status 29,30)",
        "FIFO-baserad beräkning (antal pall)",
    ]
    for c in out_cols:
        if c not in pr.columns:
            pr[c] = np.nan if c.startswith("FIFO") else 0.0
    report = pr[out_cols].reset_index(drop=True)
    if missing:
        notes: List[str] = []
        if "saldo" in missing:
            notes.append("Saldo saknas → Saldo i autoplock antas 0 (C=0, D=B).")
        if "buffert" in missing:
            notes.append("Buffert saknas → F kan inte beräknas.")
        meta = {
            "partial": "yes",
            "missing": ",".join(sorted(set(missing))),
            "note": " ".join(notes),
        }
    else:
        meta = {"partial": "no", "missing": "", "note": ""}
    return report, meta




def allocate(orders_raw: pd.DataFrame, buffer_raw: pd.DataFrame, log=None) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Allokera beställningsrader mot buffert enligt HELPALL→AUTOSTORE→HUVUDPLOCK.
    - Buffert filter: status {29,30,32} + platsfilter (ej AA*, TRANSIT, TRANSIT_ERROR, MISSING, UT2).
    - Ignorera orderrader med Status > 33.
    Returnerar (allocated_df, near_miss_df).
    """
    def _log(msg: str):
        if log:
            log(msg)

    order_article_col = find_col(orders_raw, ORDER_SCHEMA["artikel"])
    order_qty_col     = find_col(orders_raw, ORDER_SCHEMA["qty"])
    order_id_col      = find_col(orders_raw, ORDER_SCHEMA["ordid"], required=False, default=None)
    order_line_col    = find_col(orders_raw, ORDER_SCHEMA["radid"], required=False, default=None)
    order_status_col  = find_col(orders_raw, ORDER_SCHEMA["status"], required=False, default=None)

    buff_article_col  = find_col(buffer_raw, BUFFER_SCHEMA["artikel"])
    buff_qty_col      = find_col(buffer_raw, BUFFER_SCHEMA["qty"])
    buff_loc_col      = find_col(buffer_raw, BUFFER_SCHEMA["loc"])
    buff_dt_col       = find_col(buffer_raw, BUFFER_SCHEMA["dt"], required=False, default=None)
    buff_id_col       = find_col(buffer_raw, BUFFER_SCHEMA["id"], required=False, default=None)
    buff_status_col   = find_col(buffer_raw, BUFFER_SCHEMA["status"], required=False, default=None)
    try:
        buff_type_col = find_col(buffer_raw, [
            "palltyp", "pall typ", "pall type"
        ], required=False, default=None)
    except Exception:
        buff_type_col = None

    _log(f"Order-kolumner: Artikel='{order_article_col}', Antal='{order_qty_col}', OrderId='{order_id_col}', Rad='{order_line_col}', Status='{order_status_col}'")
    _log(f"Buffert-kolumner: Artikel='{buff_article_col}', Antal='{buff_qty_col}', Lagerplats='{buff_loc_col}', Tid='{buff_dt_col}', ID='{buff_id_col}', Status='{buff_status_col}'")

    orders = orders_raw.copy()
    orders["_artikel"] = orders[order_article_col].astype(str).str.strip()
    orders["_qty"] = orders[order_qty_col].map(to_num).astype(float)
    orders["_order_id"] = orders[order_id_col].astype(str) if order_id_col and order_id_col in orders.columns else ""
    orders["_order_line"] = orders[order_line_col].astype(str) if order_line_col and order_line_col in orders.columns else orders.index.astype(str)

    if order_status_col and order_status_col in orders.columns:
        _status_str = orders[order_status_col].astype(str).str.strip()
        _status_num = pd.to_numeric(_status_str.str.extract(r"(-?\d+)")[0], errors="coerce")
        _before = len(orders)
        orders = orders[~(_status_num > ORDER_MAX_ALLOCATABLE_STATUS)].copy()
        _removed = _before - len(orders)
        if _removed:
            _log(f"Ignorerar {_removed} orderrad(er) pga Status > {ORDER_MAX_ALLOCATABLE_STATUS}.")
    else:
        _log(f"OBS: Ingen order-statuskolumn hittad; kan inte filtrera Status > {ORDER_MAX_ALLOCATABLE_STATUS}.")

    buffer_df = buffer_raw.copy()
    buffer_df["_artikel"] = buffer_df[buff_article_col].astype(str).str.strip()
    buffer_df["_qty"] = buffer_df[buff_qty_col].map(to_num).astype(float)
    buffer_df["_loc"] = buffer_df[buff_loc_col].astype(str).str.strip()
    buffer_df["_received"] = smart_to_datetime(buffer_df[buff_dt_col]) if buff_dt_col and buff_dt_col in buffer_df.columns else pd.NaT
    buffer_df["_source_id"] = buffer_df[buff_id_col].astype(str) if buff_id_col and buff_id_col in buffer_df.columns else "SRC-" + buffer_df.index.astype(str)
    if buff_type_col and buff_type_col in buffer_df.columns:
        tmp_palltyp = buffer_df[buff_type_col].fillna("").astype(str).str.strip()
        buffer_df["_palltyp"] = tmp_palltyp.replace({"nan": "", "": ""})
    else:
        buffer_df["_palltyp"] = ""

    if buff_status_col and buff_status_col in buffer_df.columns:
        status_series = buffer_df[buff_status_col].astype(str).str.strip()
        status_num = pd.to_numeric(status_series.str.extract(r"(-?\d+)")[0], errors="coerce")
        allowed_str = {str(x) for x in ALLOC_BUFFER_STATUSES}
        mask_allowed = status_series.isin(allowed_str) | status_num.isin(ALLOC_BUFFER_STATUSES)
        removed = int((~mask_allowed).sum())
        if removed:
            _log(f"Filtrerar bort {removed} buffertpall(ar) pga Status ej i {sorted(ALLOC_BUFFER_STATUSES)}.")
        buffer_df = buffer_df[mask_allowed].copy()
    else:
        _log("OBS: Hittade ingen statuskolumn; ingen statusfiltrering tillämpas.")

    loc_upper = buffer_df["_loc"].str.upper()
    mask_exclude = loc_upper.str.startswith(INVALID_LOC_PREFIXES, na=False) | loc_upper.isin(INVALID_LOC_EXACT)
    excluded_count = int(mask_exclude.sum())
    if excluded_count:
        _log(f"Filtrerar bort {excluded_count} rad(er) från bufferten pga lagerplats-regler ({INVALID_LOC_PREFIXES}*, {', '.join(sorted(INVALID_LOC_EXACT))}).")
    buffer_df = buffer_df[~mask_exclude].copy()

    try:
        buffer_df["_artikel"] = buffer_df["_artikel"].astype("category")
    except Exception:
        pass

    buffer_df["_is_autostore"] = buffer_df["_loc"].str.contains("AUTOSTORE", case=False, na=False)
    buffer_df = buffer_df[buffer_df["_qty"] > 0].copy()

    far_future = pd.Timestamp("2262-04-11")
    buffer_df["_received_ord"] = buffer_df["_received"].fillna(far_future)

    pallets = buffer_df[~buffer_df["_is_autostore"]].copy().sort_values(by=["_artikel", "_received_ord", "_source_id"])
    bins = buffer_df[buffer_df["_is_autostore"]].copy().sort_values(by=["_artikel", "_received_ord", "_source_id"])

    pallet_queues: Dict[str, Deque[dict]] = defaultdict(deque)
    for _, r in pallets.iterrows():
        pallet_queues[str(r["_artikel"]).strip()].append({
            "source_id": r["_source_id"],
            "qty": float(r["_qty"]),
            "loc": r["_loc"],
            "received": r["_received"],
            "palltyp": (r.get("_palltyp", "") if pd.notna(r.get("_palltyp", "")) else "")
        })

    bin_queues: Dict[str, Deque[dict]] = defaultdict(deque)
    for _, r in bins.iterrows():
        bin_queues[str(r["_artikel"]).strip()].append({
            "source_id": r["_source_id"],
            "qty": float(r["_qty"]),
            "loc": r["_loc"],
            "received": r["_received"],
            "palltyp": (r.get("_palltyp", "") if pd.notna(r.get("_palltyp", "")) else "")
        })

    allocated_rows: List[dict] = []
    near_miss_rows: List[dict] = []
    near_miss_article_set: set[str] = set()

    def clone_row(orow: pd.Series) -> dict:
        return orow.to_dict()

    def record_near_miss(orow: pd.Series, pal: dict, need: float) -> None:
        """
        Record a near-miss event when a pallet is up to the configured NEAR_MISS_PCT larger than the
        remaining need for an article. To prevent excessive logging when the same article triggers
        multiple near-miss events across many order lines, this function will only record the first
        near-miss for each unique article. Additional near misses for the same article are ignored.
        """
        if need <= 0:
            return
        diff = pal["qty"] - need
        if diff <= 0:
            return
        pct = diff / need
        if pct <= NEAR_MISS_PCT:
            art_id = str(orow["_artikel"]).strip()
            if art_id in near_miss_article_set:
                return
            near_miss_article_set.add(art_id)
            near_miss_rows.append({
                "Artikel": art_id,
                "OrderID": str(orow["_order_id"]),
                "OrderRad": str(orow["_order_line"]),
                "PallID": str(pal["source_id"]),
                "Källplats": str(pal["loc"]),
                "Mottagen": pal["received"],
                "Behov_vid_tillfället": need,
                "Pall_kvantitet": pal["qty"],
                "Skillnad": diff,
                "Procentuell skillnad (%)": pct * 100.0,
                "Anledning": f"Pallen var ≤{int(NEAR_MISS_PCT * 100)}% större än återstående behov (kan ej brytas)",
                "Gäller (INSTEAD R/A)": None
            })

    for _, orow in orders.iterrows():
        art = str(orow["_artikel"]).strip()
        need = float(orow["_qty"])
        if need <= 0:
            continue

        pq = pallet_queues.get(art, deque())
        new_pq = deque()
        tmp = deque(pq)
        any_helpall = False
        while tmp and need > 0:
            pal = tmp.popleft()
            pal_qty = pal["qty"]
            if pal_qty <= need:
                sub = clone_row(orow)
                sub[order_qty_col] = pal_qty
                sub["Zon (beräknad)"] = "H"
                sub["Källtyp"] = "HELPALL"
                sub["Källa"] = pal["source_id"]
                sub["Källplats"] = pal["loc"]
                paltyp_val = pal.get("palltyp", "")
                if not paltyp_val or str(paltyp_val).lower() == "nan":
                    paltyp_val = ""
                sub["Palltyp (matchad)"] = paltyp_val
                allocated_rows.append(sub)
                need -= pal_qty
                any_helpall = True
            else:
                record_near_miss(orow, pal, need)
                new_pq.append(pal)
        while tmp:
            new_pq.append(tmp.popleft())
        pallet_queues[art] = new_pq

        any_autostore = False
        bq = bin_queues.get(art, deque())
        new_bq = deque()
        while bq and need > 0:
            binr = bq.popleft()
            take = min(binr["qty"], need)
            if take > 0:
                sub = clone_row(orow)
                sub[order_qty_col] = take
                sub["Zon (beräknad)"] = "R"
                sub["Källtyp"] = "AUTOSTORE"
                sub["Källa"] = binr["source_id"]
                sub["Källplats"] = binr["loc"]
                bin_palltyp_val = binr.get("palltyp", "")
                if not bin_palltyp_val or str(bin_palltyp_val).lower() == "nan":
                    bin_palltyp_val = ""
                sub["Palltyp (matchad)"] = bin_palltyp_val
                allocated_rows.append(sub)
                binr["qty"] -= take
                need -= take
                any_autostore = True
            if binr["qty"] > 0:
                new_bq.append(binr)
        while bq:
            new_bq.append(bq.popleft())
        bin_queues[art] = new_bq

        any_mainpick = False
        if need > 0:
            sub = clone_row(orow)
            sub[order_qty_col] = need
            sub["Zon (beräknad)"] = "A"
            sub["Källtyp"] = "HUVUDPLOCK"
            sub["Källa"] = ""
            sub["Källplats"] = ""
            sub["Palltyp (matchad)"] = ""
            allocated_rows.append(sub)
            any_mainpick = True
            need = 0.0

        if not any_helpall and (any_autostore or any_mainpick):
            for r in near_miss_rows:
                if r["OrderID"] == str(orow["_order_id"]) and r["OrderRad"] == str(orow["_order_line"]):
                    r["Gäller (INSTEAD R/A)"] = True
        else:
            for r in near_miss_rows:
                if r["OrderID"] == str(orow["_order_id"]) and r["OrderRad"] == str(orow["_order_line"]):
                    r["Gäller (INSTEAD R/A)"] = False

    allocated_df = pd.DataFrame(allocated_rows)

    try:
        if not allocated_df.empty and ("Källtyp" in allocated_df.columns):
            if "Zon (beräknad)" not in allocated_df.columns:
                allocated_df["Zon (beräknad)"] = ""
            low = {c.lower(): c for c in allocated_df.columns}
            art_col_res = None
            for n in ["artikel", "article", "artnr", "art.nr", "artikelnummer", "_artikel"]:
                if n.lower() in low:
                    art_col_res = low[n.lower()]
                    break
            if art_col_res:
                auto_arts = set(allocated_df.loc[allocated_df["Källtyp"].astype(str) == "AUTOSTORE", art_col_res].astype(str).str.strip())
                if auto_arts:
                    mask_same = allocated_df[art_col_res].astype(str).str.strip().isin(auto_arts)
                    mask_change = mask_same & (allocated_df["Källtyp"].astype(str) != "HELPALL")
                    allocated_df.loc[mask_change, "Källtyp"] = "AUTOSTORE"
                    allocated_df.loc[mask_change, "Zon (beräknad)"] = "R"
    except Exception:
        pass

    added_cols = ["Zon (beräknad)", "Källtyp", "Källa", "Källplats", "Palltyp (matchad)"]
    ordered_cols = [c for c in orders_raw.columns] + [c for c in added_cols if c not in orders_raw.columns]
    if not allocated_df.empty:
        allocated_df = allocated_df[ordered_cols]
    else:
        allocated_df = pd.DataFrame(columns=ordered_cols)

    near_miss_df = pd.DataFrame(near_miss_rows)
    return allocated_df, near_miss_df


def calculate_refill(allocated_df: pd.DataFrame,
                     buffer_raw: pd.DataFrame,
                     saldo_df: pd.DataFrame | None = None,
                     not_putaway_df: pd.DataFrame | None = None
                     ) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Beräkna påfyllningspallar.
    - HP-blad inkluderar både HUVUDPLOCK (A) och SKRYMMANDE (S).
    - Plocksaldo dras en gång per artikel och fördelas proportionerligt mellan A och S.
    - 0-rader tas bort.
    - AUTOSTORE-blad (R) oförändrat, men 0-rader tas också bort.
    - Buffert filtreras till status {29,30}. HELPALL-pallar som redan används exkluderas alltid.
    """

    result = allocated_df.copy()
    buff = buffer_raw.copy()

    art_col_res = find_col(result, ORDER_SCHEMA["artikel"])
    qty_col_res = find_col(result, ORDER_SCHEMA["qty"])

    art_col_buf = find_col(buff, BUFFER_SCHEMA["artikel"])
    qty_col_buf = find_col(buff, BUFFER_SCHEMA["qty"])
    dt_col_buf  = find_col(buff, BUFFER_SCHEMA["dt"], required=False, default=None)
    id_col_buf  = find_col(buff, BUFFER_SCHEMA["id"], required=False, default=None)
    status_col_buf = find_col(buff, BUFFER_SCHEMA["status"], required=False, default=None)

    b = buff.copy()
    b["_artikel"] = b[art_col_buf].astype(str).str.strip()
    b["_qty"] = b[qty_col_buf].map(to_num).astype(float)
    b["_received"] = smart_to_datetime(b[dt_col_buf]) if dt_col_buf and dt_col_buf in b.columns else pd.NaT
    b["_source_id"] = b[id_col_buf].astype(str) if id_col_buf and id_col_buf in b.columns else "SRC-" + b.index.astype(str)

    if status_col_buf and status_col_buf in b.columns:
        _s = b[status_col_buf].astype(str).str.strip()
        _snum = pd.to_numeric(_s.str.extract(r"(-?\d+)")[0], errors="coerce")
        allowed_str = {str(x) for x in REFILL_BUFFER_STATUSES}
        b = b[_s.isin(allowed_str) | _snum.isin(REFILL_BUFFER_STATUSES)].copy()

    used_help_ids: set[str] = set()
    if "Källtyp" in result.columns and "Källa" in result.columns:
        used_help_ids = set(result[result["Källtyp"].astype(str) == "HELPALL"]["Källa"].dropna().astype(str).tolist())

    saldo_sum: Dict[str, float] = {}
    plockplats_by_art: Dict[str, str] = {}
    if isinstance(saldo_df, pd.DataFrame) and not saldo_df.empty:
        try:
            s_norm = normalize_saldo(saldo_df)
            for _, r in s_norm.iterrows():
                art = str(r["Artikel"]).strip()
                saldo_sum[art] = float(saldo_sum.get(art, 0.0) + float(r.get("Plocksaldo", 0.0)))
                pp = str(r.get("Plockplats", "") or "").strip()
                if pp and art not in plockplats_by_art:
                    plockplats_by_art[art] = pp
        except Exception:
            saldo_sum = {}
            plockplats_by_art = {}

    npu_sum: Dict[str, float] = {}
    if isinstance(not_putaway_df, pd.DataFrame) and not not_putaway_df.empty:
        try:
            npu = not_putaway_df.copy()
            npu_art_col = find_col(npu, NOT_PUTAWAY_SCHEMA["artikel"])
            npu_qty_col = find_col(npu, NOT_PUTAWAY_SCHEMA["antal"])
            grp = npu.groupby(npu[npu_art_col].astype(str).str.strip())[npu_qty_col].apply(lambda s: float(pd.to_numeric(s, errors="coerce").fillna(0).sum()))
            npu_sum = {str(k): float(v) for k, v in grp.to_dict().items()}
        except Exception:
            npu_sum = {}

    def fifo_for_art(art_key: str) -> pd.DataFrame:
        d = b[b["_artikel"] == art_key].copy()
        if not d.empty and used_help_ids:
            d = d[~d["_source_id"].astype(str).isin(used_help_ids)].copy()
        return d.sort_values("_received")

    hp_like = result[result.get("Källtyp", "").isin(["HUVUDPLOCK", "SKRYMMANDE", "HIB", "EHANDEL"])].copy()
    rows_hp: List[dict] = []
    if not hp_like.empty:
        hp_like["_zon"] = hp_like["Källtyp"].astype(str).map({"SKRYMMANDE": "S", "HIB": "F"}).fillna("A")
        needs = (hp_like
                 .assign(_art=hp_like[art_col_res].astype(str).str.strip(),
                         _qty=pd.to_numeric(hp_like[qty_col_res], errors="coerce").fillna(0.0))
                 .groupby(["_art", "_zon"], as_index=False)["_qty"].sum())

        for art_key, grp_art in needs.groupby("_art"):
            total_need = float(grp_art["_qty"].sum())
            if total_need <= 0:
                continue
            adjusted_total = max(0.0, round(total_need) - float(saldo_sum.get(art_key, 0.0)))

            if adjusted_total <= 0:
                continue  # 0-rad; hoppa över helt

            parts = []
            allocated_sum = 0
            for _, r in grp_art.iterrows():
                zone = str(r["_zon"])
                part = (float(r["_qty"]) / total_need) * adjusted_total if total_need > 0 else 0.0
                val = int(round(part))
                parts.append([zone, val])
                allocated_sum += val
            diff = int(adjusted_total) - int(allocated_sum)
            if parts:
                parts[0][1] += diff

            fifo_df = fifo_for_art(art_key)
            tillgangligt = float(pd.to_numeric(fifo_df["_qty"], errors="coerce").sum()) if not fifo_df.empty else 0.0

            for zone, behov_int in parts:
                behov_int = int(max(0, behov_int))
                if behov_int <= 0:
                    continue  # 0-rad → bort
                behov_kvar = float(behov_int)
                pall_count = 0
                for q in (fifo_df["_qty"].astype(float) if not fifo_df.empty else []):
                    if behov_kvar <= 0:
                        break
                    pall_count += 1
                    behov_kvar -= float(q)

                rows_hp.append({
                    "Artikel": art_key,
                    "Zon": zone,  # A eller S
                    "Behov (kolli)": behov_int,
                    "FIFO-baserad beräkning": int(pall_count),
                    "Tillräckligt tillgängligt saldo i buffert": "Ja" if tillgangligt >= behov_int else "Nej",
                    "Plockplats": plockplats_by_art.get(art_key, ""),
                    "Ej inlagrade (antal)": int(round(npu_sum.get(art_key, 0.0)))
                })

    refill_hp_df = pd.DataFrame(rows_hp)
    if not refill_hp_df.empty:
        refill_hp_df = refill_hp_df.sort_values(["Zon", "FIFO-baserad beräkning"], ascending=[True, False])

    refill_autostore_df = pd.DataFrame()
    try:
        as_df = result.copy()
        if not as_df.empty:
            mask_autostore = as_df["Källtyp"].astype(str) == "AUTOSTORE" if "Källtyp" in as_df.columns else pd.Series(False, index=as_df.index)
            k_blank = as_df["Källa"].isna() | (as_df["Källa"].astype(str).str.strip() == "") if "Källa" in as_df.columns else pd.Series(True, index=as_df.index)
            as_df = as_df[mask_autostore & k_blank].copy()
        if not as_df.empty:
            art_col_res_as = find_col(as_df, ORDER_SCHEMA["artikel"])
            qty_col_res_as = find_col(as_df, ORDER_SCHEMA["qty"])
            behov_per_art_as = as_df.groupby(as_df[art_col_res_as].astype(str).str.strip())[qty_col_res_as] \
                                   .apply(lambda s: float(pd.to_numeric(s, errors="coerce").fillna(0).sum())) \
                                   .to_dict()

            rows_as: List[dict] = []
            for art, behov in behov_per_art_as.items():
                art_key = str(art).strip()
                fifo_df = fifo_for_art(art_key)
                tillgangligt = float(pd.to_numeric(fifo_df["_qty"], errors="coerce").sum()) if not fifo_df.empty else 0.0
                behov_int = int(max(0, round(behov) - float(saldo_sum.get(art_key, 0.0))))
                if behov_int <= 0:
                    continue  # 0-rad bort
                remaining = float(behov_int)
                pall_count = 0
                for q in (fifo_df["_qty"].astype(float) if not fifo_df.empty else []):
                    if remaining <= 0:
                        break
                    pall_count += 1
                    remaining -= float(q)

                rows_as.append({
                    "Artikel": art_key,
                    "Behov (kolli)": behov_int,
                    "FIFO-baserad beräkning": int(pall_count),
                    "Tillräckligt tillgängligt saldo i buffert": "Ja" if tillgangligt >= behov_int else "Nej",
                    "Plockplats": plockplats_by_art.get(art_key, ""),
                    "Ej inlagrade (antal)": int(round(npu_sum.get(art_key, 0.0)))
                })

            refill_autostore_df = pd.DataFrame(rows_as)
            if not refill_autostore_df.empty:
                refill_autostore_df = refill_autostore_df.sort_values("FIFO-baserad beräkning", ascending=False)
    except Exception:
        refill_autostore_df = pd.DataFrame()

    return refill_hp_df, refill_autostore_df


@dataclass
class OverviewCheckResult:
    shipment_df: pd.DataFrame
    hib_df: pd.DataFrame
    missing_hib_cols: list[str]
    log_lines: list[str]


@dataclass
class DispatchCheckResult:
    diff_df: pd.DataFrame
    log_lines: list[str]


@dataclass
class Vecka27CheckResult:
    deviations: list[str]
    report_text: str
    report_df: pd.DataFrame
    log_lines: list[str]


@dataclass
class PrognosReportResult:
    combined_df: pd.DataFrame
    report_df: pd.DataFrame
    meta: dict[str, str]
    log_lines: list[str]


@dataclass
class ChunkedValuesResult:
    report_df: pd.DataFrame
    value_count: int
    chunk_count: int
    chunk_size: int


@dataclass
class ObservationsUpdateResult:
    new_rows_df: pd.DataFrame
    new_row_count: int
    github_sent_rows: int
    article_max_rows: int
    article_max_changed_rows: int
    article_max_increased_rows: int
    article_max_decreased_rows: int
    article_max_new_rows: int
    article_max_removed_rows: int
    article_max_changed_examples: List[Dict[str, str]]
    pushed_to_github: bool
    observations_path: str
    article_max_path: str


@dataclass
class ObservationsSyncResult:
    fetched_rows: int
    pushed_rows: int
    total_observations: int
    article_max_rows: int
    observations_path: str
    article_max_path: str


@dataclass
class UpdateCheckCliResult:
    has_update: bool
    current_version: str
    latest_version: str
    release_url: str
    installer_name: str
    downloaded_path: str


WMS_EXPECTED_FILENAMES: Dict[str, str] = {
    "wms_receive": "v_ask_receive_log.csv",
    "wms_booking": "v_ask_booking_putaway.csv",
    "wms_buffert": "v_ask_article_buffertpallet.csv",
    "wms_trans": "v_ask_trans_log.csv",
    "wms_pick": "v_ask_pick_log_full.csv",
    "wms_correct": "v_ask_correct_log.csv",
}

WMS_EMPTY_COLUMNS: Dict[str, list[str]] = {
    "wms_receive": ["Inköpsnr", "Artikel", "Pallid", "Mottaget", "Ändrad"],
    "wms_booking": ["Pall nr", "Inköpsnr", "Ändrad"],
    "wms_buffert": ["Pallid", "Lagerplats", "Datum/tid"],
    "wms_trans": ["Pallid", "Till", "Timestamp", "Från"],
    "wms_pick": ["Pallid", "Artikelnr", "Plockat", "Ordernr", "Datum"],
    "wms_correct": ["Pallid", "Antal", "Anledning", "Artikel", "Ändrad"],
}

def _vecka27_fmt_qty_value(q: float) -> str:
    try:
        f = float(q)
    except Exception:
        return str(q)
    return str(int(f)) if f.is_integer() else str(f)


def _write_cli_text_report(text: str, path: str, column_name: str = "Rapport") -> str:
    target = Path(path)
    suffix = target.suffix.lower()
    if suffix in {"", ".txt", ".md"}:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return str(target.resolve())
    lines = text.splitlines() if text else [""]
    return _write_cli_dataframe(pd.DataFrame({column_name: lines}), path)


def _find_keywords_column(df: pd.DataFrame, keywords: List[str]) -> Optional[str]:
    for keyword in keywords:
        keyword_norm = keyword.lower().replace(" ", "")
        for col in df.columns:
            if str(col).lower().replace(" ", "") == keyword_norm:
                return str(col)
    for keyword in keywords:
        keyword_lower = keyword.lower()
        for col in df.columns:
            if keyword_lower in str(col).lower():
                return str(col)
    return None


def _find_customer_name_column(df: pd.DataFrame, exclude: Optional[set[str]] = None) -> Optional[str]:
    excluded = exclude or set()
    for col in df.columns:
        if col in excluded:
            continue
        col_norm = str(col).lower().replace(" ", "")
        if "kund" in col_norm and not col_norm.endswith("nr") and not col_norm.endswith("nummer"):
            return str(col)
    return None


def _status_to_int(value: object) -> Optional[int]:
    try:
        raw = str(value).strip().replace(",", ".")
        if not raw:
            return None
        return int(float(raw))
    except Exception:
        return None


def _build_order_to_customer_map(
    details_df: Optional[pd.DataFrame],
    overview_df: pd.DataFrame,
    overview_order_col: Optional[str],
    overview_customer_col: Optional[str],
) -> Dict[str, str]:
    order_to_customer: Dict[str, str] = {}

    if isinstance(details_df, pd.DataFrame) and not details_df.empty:
        details = _clean_columns(details_df.copy())
        details_order_col = _find_keywords_column(details, ["order nr", "ordernr", "ordernummer", "order number", "orderid"])
        details_customer_col = _find_customer_name_column(details, exclude={details_order_col} if details_order_col else set())
        if details_order_col and details_customer_col:
            try:
                order_to_customer = (
                    details.groupby(details_order_col)[details_customer_col]
                    .first()
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .to_dict()
                )
            except Exception:
                order_to_customer = {}

    if order_to_customer or not overview_order_col or not overview_customer_col:
        return order_to_customer

    try:
        return (
            overview_df.groupby(overview_order_col)[overview_customer_col]
            .first()
            .fillna("")
            .astype(str)
            .str.strip()
            .to_dict()
        )
    except Exception:
        return {}


def _empty_prognos_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["Artikelnummer", "Beskrivning", "Antal styck", "Antal rader", "Antal butiker"]
    )


def _normalize_prognos_cli_table(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return _empty_prognos_df()

    work = _clean_columns(df.copy())
    col_map: dict[str, str] = {}
    for col in work.columns:
        col_norm = str(col).strip().lower()
        if col_norm in {"product code", "artikelnummer", "artikelnr", "artnr", "sku", "article"}:
            col_map[col] = "Artikelnummer"
        elif col_norm in {"product name", "name", "benämning", "benamning", "beskrivning"}:
            col_map[col] = "Beskrivning"
        elif col_norm in {"antal styck", "antal", "qty", "quantity"}:
            col_map[col] = "Antal styck"
        elif col_norm in {"antal rader", "rows", "number of rows"}:
            col_map[col] = "Antal rader"
        elif col_norm in {"antal butiker", "stores", "butiker", "number of stores"}:
            col_map[col] = "Antal butiker"
    if col_map:
        work = work.rename(columns=col_map)

    out = _empty_prognos_df()
    for column_name in out.columns:
        if column_name in work.columns:
            out[column_name] = work[column_name]
    out["Artikelnummer"] = out["Artikelnummer"].fillna("").astype(str).str.strip()
    out["Beskrivning"] = out["Beskrivning"].fillna("").astype(str).str.strip()
    for num_col in ["Antal styck", "Antal rader", "Antal butiker"]:
        out[num_col] = pd.to_numeric(out[num_col], errors="coerce").fillna(0).astype(int)
    out = out.loc[out["Artikelnummer"].str.len().gt(0) | out["Beskrivning"].str.len().gt(0)].reset_index(drop=True)
    return out


def _normalize_campaign_cli_table(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=["Artikelnummer", "Antal styck"])

    work = _clean_columns(df.copy())
    col_map: dict[str, str] = {}
    for col in work.columns:
        col_norm = str(col).strip().lower()
        if col_norm in {"artikelnummer", "artikelnr", "artnr", "sku", "article", "product code"}:
            col_map[col] = "Artikelnummer"
        elif col_norm in {"antal styck", "antal", "qty", "quantity"}:
            col_map[col] = "Antal styck"
    if col_map:
        work = work.rename(columns=col_map)

    if "Artikelnummer" not in work.columns or "Antal styck" not in work.columns:
        return pd.DataFrame(columns=["Artikelnummer", "Antal styck"])

    out = work[["Artikelnummer", "Antal styck"]].copy()
    out["Artikelnummer"] = out["Artikelnummer"].fillna("").astype(str).str.strip()
    out["Antal styck"] = pd.to_numeric(out["Antal styck"], errors="coerce").fillna(0).astype(int)
    out = out.loc[out["Artikelnummer"].str.len().gt(0)].reset_index(drop=True)
    return out


def _load_prognos_cli_source(path: str) -> pd.DataFrame:
    suffix = Path(path).suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"}:
        return read_prognos_xlsx(path)
    return _normalize_prognos_cli_table(_read_cli_table(path))


def _load_campaign_cli_source(path: str) -> pd.DataFrame:
    suffix = Path(path).suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"}:
        return read_campaign_xlsx(path)
    return _normalize_campaign_cli_table(_read_cli_table(path))


def _combine_prognos_and_campaign(
    prognos_df: Optional[pd.DataFrame],
    campaign_df: Optional[pd.DataFrame],
    saldo_df: Optional[pd.DataFrame],
) -> pd.DataFrame:
    has_prognos = isinstance(prognos_df, pd.DataFrame) and not prognos_df.empty
    has_campaign = isinstance(campaign_df, pd.DataFrame) and not campaign_df.empty
    if not has_prognos and not has_campaign:
        raise ValueError("Välj och läs in antingen prognosfilen eller kampanjvolymerna först.")

    if has_prognos:
        combined_df = _normalize_prognos_cli_table(prognos_df)
    else:
        combined_df = _empty_prognos_df()

    if not has_campaign:
        return combined_df

    camp_df = _normalize_campaign_cli_table(campaign_df)
    if camp_df.empty:
        return combined_df

    if isinstance(saldo_df, pd.DataFrame) and not saldo_df.empty:
        saldo_work = _clean_columns(saldo_df.copy())
        art_col_sal = None
        robot_col_sal = None
        for col in saldo_work.columns:
            col_norm = str(col).strip().lower()
            if not art_col_sal and col_norm in {"artikel", "artikelnummer", "artnr", "art.nr", "sku", "article"}:
                art_col_sal = str(col)
            if not robot_col_sal and col_norm == "robot":
                robot_col_sal = str(col)
        if art_col_sal and robot_col_sal:
            saldo_work = saldo_work[[art_col_sal, robot_col_sal]].copy()
            saldo_work.columns = ["Artikelnummer", "Robot"]
            saldo_work["Artikelnummer"] = saldo_work["Artikelnummer"].astype(str).str.strip()
            saldo_work["Robot"] = saldo_work["Robot"].astype(str).str.upper().str.strip()
            saldo_work = saldo_work.loc[saldo_work["Robot"] == "Y"]
            if not saldo_work.empty:
                camp_df = camp_df.merge(saldo_work[["Artikelnummer"]], on="Artikelnummer", how="inner")
            else:
                camp_df = camp_df.iloc[0:0]
        else:
            camp_df = camp_df.iloc[0:0]

    if camp_df.empty:
        return combined_df

    vol_by_art = camp_df.groupby("Artikelnummer")["Antal styck"].sum().to_dict()
    combined_df["Artikelnummer"] = combined_df["Artikelnummer"].astype(str).str.strip()
    combined_df["Antal styck"] = pd.to_numeric(
        combined_df.get("Antal styck", 0), errors="coerce"
    ).fillna(0).astype(int)
    existing_arts = set(combined_df["Artikelnummer"].astype(str))
    for art, vol in vol_by_art.items():
        if art in existing_arts:
            mask = combined_df["Artikelnummer"] == art
            combined_df.loc[mask, "Antal styck"] = (
                combined_df.loc[mask, "Antal styck"].astype(int) + int(vol)
            ).astype(int)
        else:
            combined_df = pd.concat(
                [
                    combined_df,
                    pd.DataFrame(
                        {
                            "Artikelnummer": [art],
                            "Beskrivning": [None],
                            "Antal styck": [int(vol)],
                            "Antal rader": [0],
                            "Antal butiker": [0],
                        }
                    ),
                ],
                ignore_index=True,
            )
    return combined_df.reset_index(drop=True)


def _validate_prognos_report_saldo(saldo_df: Optional[pd.DataFrame]) -> pd.DataFrame:
    if not isinstance(saldo_df, pd.DataFrame) or saldo_df.empty:
        raise ValueError("Ladda eller ange Saldo inkl. automation forst. Prognosrapporten filtrerar pa Robot=Y.")

    saldo_work = _clean_columns(saldo_df.copy())
    has_robot_col = any(str(col).strip().lower() == "robot" for col in saldo_work.columns)
    if not has_robot_col:
        raise ValueError("Saldofilen saknar kolumnen Robot. Prognosrapporten filtrerar pa Robot=Y.")
    return saldo_work


def build_prognos_report_result(
    prognos_df: Optional[pd.DataFrame] = None,
    campaign_df: Optional[pd.DataFrame] = None,
    saldo_df: Optional[pd.DataFrame] = None,
    buffer_df: Optional[pd.DataFrame] = None,
) -> PrognosReportResult:
    combined_df = _combine_prognos_and_campaign(prognos_df, campaign_df, saldo_df)
    saldo_df = _validate_prognos_report_saldo(saldo_df)
    report_df, meta = build_prognos_vs_autoplock_report(
        prognos_df=combined_df,
        saldo_norm_df=saldo_df,
        buffer_df=buffer_df,
        exclude_source_ids=None,
        allocated_df=None,
    )
    log_lines = [f"Prognosrapport skapad ({len(report_df)} rader)."]
    if isinstance(meta, dict) and meta.get("partial") == "yes":
        missing = str(meta.get("missing", "")).replace(",", ", ").strip()
        if missing:
            log_lines.append(f"PARTIELL: saknar {missing}.")
        note = str(meta.get("note", "")).strip()
        if note:
            log_lines.append(note)
    return PrognosReportResult(combined_df, report_df, meta, log_lines)


def _build_prognos_report_sheets(result: PrognosReportResult) -> dict[str, pd.DataFrame]:
    sheets: dict[str, pd.DataFrame] = {}
    meta = result.meta if isinstance(result.meta, dict) else {}
    if meta.get("partial") == "yes" or meta.get("note"):
        lines: list[str] = []
        if meta.get("partial") == "yes":
            missing = str(meta.get("missing", "")).strip()
            lines.append("PARTIELL RAPPORT - mer data kravs for fullstandig bild.")
            if missing:
                lines.append(f"Saknar underlag: {missing}.")
        if meta.get("note"):
            lines.append(str(meta["note"]))
        if lines:
            sheets["Info"] = pd.DataFrame({"Info": [" ".join(lines)]})
    sheets["Prognos vs Autoplock"] = result.report_df.copy()
    return sheets


def build_chunked_values_result(values: list[str], chunk_size: int = 2000) -> ChunkedValuesResult:
    cleaned_values = [str(value).strip() for value in values if str(value).strip()]
    if not cleaned_values:
        raise ValueError("Klistra in värden först (en per rad).")
    try:
        chunk_size_int = int(chunk_size)
    except Exception as exc:
        raise ValueError("Antal per kolumn måste vara ett heltal > 0.") from exc
    if chunk_size_int <= 0:
        raise ValueError("Antal per kolumn måste vara ett heltal > 0.")

    chunks = [
        cleaned_values[start:start + chunk_size_int]
        for start in range(0, len(cleaned_values), chunk_size_int)
    ]
    out_cols: dict[str, pd.Series] = {}
    for idx, chunk in enumerate(chunks, start=1):
        out_cols[f"Kolumn {idx}"] = pd.Series([str(value) for value in chunk], dtype="string")
    report_df = pd.DataFrame(out_cols).fillna("")
    return ChunkedValuesResult(report_df, len(cleaned_values), len(chunks), chunk_size_int)


def build_observations_update_result(
    buffer_df: pd.DataFrame,
    observations_path: Optional[str] = None,
    artikel_max_out: Optional[str] = None,
    push_to_github: bool = False,
    business_code: Optional[str] = None,
) -> ObservationsUpdateResult:
    obs_path = Path(observations_path) if observations_path else business_observations_path(business_code)
    max_path = Path(artikel_max_out) if artikel_max_out else business_artikel_max_path(business_code)
    article_max_before = _read_artikel_max(max_path)
    new_row_count, new_rows_df = update_observations_from_buffer(
        buffer_df,
        observations_path=obs_path,
        artikel_max_path=max_path,
    )
    pushed = bool(
        push_to_github
        and new_row_count
        and push_new_observations_to_github(new_rows_df, business_code=business_code)
    )
    github_sent_rows = int(new_row_count) if pushed else 0
    article_max_after = _read_artikel_max(max_path)
    max_changes = _artikel_max_change_summary(article_max_before, article_max_after)
    article_max_rows = 0
    if max_path.exists() and max_path.stat().st_size > 0:
        try:
            article_max_rows = int(len(pd.read_csv(max_path, dtype=str, encoding="utf-8-sig")))
        except Exception:
            article_max_rows = 0
    return ObservationsUpdateResult(
        new_rows_df=new_rows_df,
        new_row_count=int(new_row_count),
        github_sent_rows=github_sent_rows,
        article_max_rows=article_max_rows,
        article_max_changed_rows=int(max_changes["changed_rows"]),
        article_max_increased_rows=int(max_changes["increased_rows"]),
        article_max_decreased_rows=int(max_changes["decreased_rows"]),
        article_max_new_rows=int(max_changes["new_article_rows"]),
        article_max_removed_rows=int(max_changes["removed_article_rows"]),
        article_max_changed_examples=list(max_changes["examples"]),
        pushed_to_github=pushed,
        observations_path=str(obs_path.resolve()),
        article_max_path=str(max_path.resolve()),
    )


def build_observations_sync_result(
    observations_path: Optional[str] = None,
    artikel_max_out: Optional[str] = None,
    remote_file: Optional[str] = None,
    push_orphaned: bool = True,
    business_code: Optional[str] = None,
) -> ObservationsSyncResult:
    obs_path = Path(observations_path) if observations_path else business_observations_path(business_code)
    max_path = Path(artikel_max_out) if artikel_max_out else business_artikel_max_path(business_code)
    fetched_rows, pushed_rows = fetch_observations_from_github(
        observations_path=obs_path,
        artikel_max_path=max_path,
        remote_file=remote_file,
        push_orphaned=push_orphaned,
        business_code=business_code,
    )
    total_observations = int(len(_read_observations(obs_path)))
    article_max_rows = 0
    if max_path.exists() and max_path.stat().st_size > 0:
        try:
            article_max_rows = int(len(pd.read_csv(max_path, dtype=str, encoding="utf-8-sig")))
        except Exception:
            article_max_rows = 0
    return ObservationsSyncResult(
        fetched_rows=int(fetched_rows),
        pushed_rows=int(pushed_rows),
        total_observations=total_observations,
        article_max_rows=article_max_rows,
        observations_path=str(obs_path.resolve()),
        article_max_path=str(max_path.resolve()),
    )


def _build_update_session_from_release_json(path: str):
    release_payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))

    class _StaticResponse:
        def __init__(self, data):
            self._data = data
            self.status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return self._data

    class _StaticSession:
        def __init__(self, data):
            self._response = _StaticResponse(data)

        def get(self, url, **kwargs):
            return self._response

    return _StaticSession(release_payload)


def build_update_check_cli_result(
    release_json_path: Optional[str] = None,
    download_dir: Optional[str] = None,
) -> UpdateCheckCliResult:
    session = _build_update_session_from_release_json(release_json_path) if release_json_path else None
    info = check_for_update(session=session)
    downloaded_path = ""
    if info and download_dir:
        downloaded_path = str(download_update_installer(info, target_dir=Path(download_dir)))
    if not info:
        return UpdateCheckCliResult(
            has_update=False,
            current_version=APP_VERSION,
            latest_version=APP_VERSION,
            release_url="",
            installer_name="",
            downloaded_path=downloaded_path,
        )
    return UpdateCheckCliResult(
        has_update=True,
        current_version=APP_VERSION,
        latest_version=info.version,
        release_url=info.release_url,
        installer_name=info.installer_name,
        downloaded_path=downloaded_path,
    )


def _build_overview_check_sheets(result: OverviewCheckResult) -> dict[str, pd.DataFrame]:
    sheets: dict[str, pd.DataFrame] = {}
    combined_parts: List[pd.DataFrame] = []

    if isinstance(result.shipment_df, pd.DataFrame) and not result.shipment_df.empty:
        shipment_df = result.shipment_df.copy()
        if "Avvikelsetyp" not in shipment_df.columns:
            shipment_df.insert(0, "Avvikelsetyp", "Sändningsnr med flera kunder/transportörer")
        sheets["Sändningskontroll"] = shipment_df.copy()
        combined_parts.append(shipment_df)

    if isinstance(result.hib_df, pd.DataFrame) and not result.hib_df.empty:
        hib_df = result.hib_df.copy()
        if "Avvikelsetyp" not in hib_df.columns:
            hib_df.insert(0, "Avvikelsetyp", "HIB över status 31 utan butikssändning")
        sheets["HIB utan butikssändning"] = hib_df.copy()
        combined_parts.append(hib_df)

    if combined_parts:
        sheets = {
            "Orderkontroll": pd.concat(combined_parts, ignore_index=True, sort=False),
            **sheets,
        }
    elif not sheets:
        sheets["Orderkontroll"] = pd.DataFrame(columns=["Avvikelsetyp"])

    return sheets


def build_overview_check_result(
    overview_df: pd.DataFrame,
    details_df: Optional[pd.DataFrame] = None,
) -> OverviewCheckResult:
    df = _clean_columns(overview_df.copy())
    if df.empty:
        return OverviewCheckResult(pd.DataFrame(), pd.DataFrame(), [], [])

    ship_col = _find_keywords_column(
        df,
        ["sändningsnr", "sändnings nr", "sändningsnummer", "sandningsnr", "sandnings nr", "sandningsnummer"],
    )
    if not ship_col:
        raise KeyError("Kunde inte identifiera sändningsnummer-kolumnen i orderöversikten.")

    cust_col = _find_keywords_column(df, ["kundnr", "kund nr", "kundnummer"])
    if not cust_col:
        cust_col = _find_customer_name_column(df, exclude={ship_col})
    if not cust_col:
        raise KeyError("Kunde inte identifiera kund-kolumnen i orderöversikten.")

    trans_col = _find_keywords_column(df, ["transportör", "transportor", "transportörsnr", "transportorsnr"])
    if not trans_col:
        trans_col = "__transport_dummy__"
        df[trans_col] = ""

    order_col = _find_keywords_column(df, ["ordernr", "order nr", "ordernummer", "order number", "orderid", "order id"])
    if not order_col:
        order_col = _find_keywords_column(df, ["order"])
    ordertype_col = _find_keywords_column(df, ["ordertyp", "ordertype"])
    status_col = _find_keywords_column(df, ["status", "orderstatus", "radstatus", "state"])
    if not status_col:
        status_col = _find_keywords_column(df, ["status"])

    df[ship_col] = df[ship_col].astype(str).str.strip()
    df[cust_col] = df[cust_col].astype(str).str.strip()
    df[trans_col] = df[trans_col].astype(str).str.strip()
    if order_col:
        df[order_col] = df[order_col].astype(str).str.strip()

    df = df[df[ship_col].astype(str).str.len() > 0].copy()
    if df.empty:
        return OverviewCheckResult(pd.DataFrame(), pd.DataFrame(), [], [])

    order_to_customer = _build_order_to_customer_map(details_df, df, order_col, cust_col)

    shipment_diff_rows: List[Dict[str, object]] = []
    for ship, group in df.groupby(ship_col):
        try:
            customers = sorted(set(group[cust_col].dropna().astype(str).str.strip()))
            carriers = sorted(set(group[trans_col].dropna().astype(str).str.strip()))
            customers = [value for value in customers if value]
            carriers = [value for value in carriers if value]

            orders_list: List[str] = []
            if order_col:
                try:
                    order_vals = sorted(set(group[order_col].dropna().astype(str).str.strip()))
                except Exception:
                    order_vals = []
                for order_value in order_vals:
                    customer_name = order_to_customer.get(order_value, "")
                    orders_list.append(f"{order_value} ({customer_name})" if customer_name else order_value)

            if len(customers) > 1 or len(carriers) > 1:
                row: Dict[str, object] = {
                    "Avvikelsetyp": "Sändningsnr med flera kunder/transportörer",
                    "Sändningsnr": ship,
                    "Unika kunder": len(customers),
                    "Kunder": ", ".join(customers),
                    "Unika transportörer": len(carriers),
                    "Transportörer": ", ".join(carriers),
                    "Antal orderrader": int(len(group)),
                }
                if orders_list:
                    row["Ordernr (kundnamn)"] = ", ".join(orders_list)
                shipment_diff_rows.append(row)
        except Exception:
            continue

    shipment_df = pd.DataFrame(shipment_diff_rows) if shipment_diff_rows else pd.DataFrame()

    missing_hib_cols: List[str] = []
    if not order_col:
        missing_hib_cols.append("ordernummer")
    if not ordertype_col:
        missing_hib_cols.append("ordertyp")
    if not status_col:
        missing_hib_cols.append("status")

    hib_rows: List[Dict[str, object]] = []
    if not missing_hib_cols and order_col and ordertype_col and status_col:
        try:
            hib_df = df[[order_col, ship_col, cust_col, ordertype_col, status_col]].copy()
            hib_df["_ordertype_norm"] = hib_df[ordertype_col].astype(str).str.strip().str.upper()
            hib_df["_status_num"] = hib_df[status_col].apply(_status_to_int)

            store_mask = hib_df["_ordertype_norm"].eq("N") | hib_df["_ordertype_norm"].str.contains("BUTIK", na=False)
            store_ships = set(hib_df.loc[store_mask, ship_col].dropna().astype(str).str.strip().tolist())
            store_ships.discard("")

            hib_only_df = hib_df[hib_df["_ordertype_norm"].str.contains("HIB", na=False)].copy()
            for order_number, group in hib_only_df.groupby(order_col):
                order_number_str = str(order_number).strip()
                if not order_number_str:
                    continue
                status_values = [value for value in group["_status_num"].tolist() if value is not None]
                if not status_values:
                    continue
                max_status = max(status_values)
                if max_status <= 31:
                    continue
                hib_ships = sorted(set(group[ship_col].dropna().astype(str).str.strip()))
                hib_ships = [value for value in hib_ships if value]
                if not hib_ships or any(ship_value in store_ships for ship_value in hib_ships):
                    continue

                customer_name = order_to_customer.get(order_number_str, "")
                if not customer_name:
                    try:
                        customers = [value for value in group[cust_col].dropna().astype(str).str.strip().tolist() if value]
                        if customers:
                            customer_name = customers[0]
                    except Exception:
                        customer_name = ""

                row = {
                    "Ordernr": order_number_str,
                    "Sändningsnr": ", ".join(hib_ships),
                    "Ordertyp": "HIB",
                    "Status": int(max_status),
                    "Anmärkning": "HIB-order med status > 31 saknar matchande butikssändning",
                }
                if customer_name:
                    row["Kundnamn"] = customer_name
                hib_rows.append(row)
        except Exception:
            pass

    hib_result_df = pd.DataFrame(hib_rows) if hib_rows else pd.DataFrame()

    log_lines: list[str] = []
    if not shipment_df.empty:
        log_lines.append("Orderöversikt: sändningsnummer med flera kunder eller transportörer:")
        for _, row in shipment_df.iterrows():
            try:
                if int(row.get("Unika kunder", 0)) > 1:
                    log_lines.append(f"  Sändningsnr {row['Sändningsnr']} har flera kunder: {row['Kunder']}")
                if int(row.get("Unika transportörer", 0)) > 1:
                    log_lines.append(f"  Sändningsnr {row['Sändningsnr']} har flera transportörer: {row['Transportörer']}")
            except Exception:
                continue
    if not hib_result_df.empty:
        log_lines.append(f"HIB-ordrar med status > 31 utan matchande butikssändning ({len(hib_result_df)} st):")
        for _, row in hib_result_df.iterrows():
            try:
                name_part = f" ({row['Kundnamn']})" if str(row.get("Kundnamn", "")).strip() else ""
                log_lines.append(f"  Order {row['Ordernr']}{name_part}: sändning {row['Sändningsnr']} (status {row['Status']})")
            except Exception:
                continue
    if missing_hib_cols:
        log_lines.append("HIB-kontrollen kunde inte köras fullt ut (saknar kolumner: " + ", ".join(missing_hib_cols) + ").")

    return OverviewCheckResult(shipment_df, hib_result_df, missing_hib_cols, log_lines)


def build_dispatch_check_result(
    overview_df: pd.DataFrame,
    dispatch_df: pd.DataFrame,
    details_df: Optional[pd.DataFrame] = None,
) -> DispatchCheckResult:
    ov_df = _clean_columns(overview_df.copy())
    dp_df = _clean_columns(dispatch_df.copy())
    if ov_df.empty or dp_df.empty:
        return DispatchCheckResult(pd.DataFrame(), [])

    order_keywords = ["ordernr", "order nr", "ordernummer", "order number", "orderid", "order id"]
    ship_keywords = ["sändningsnr", "sändnings nr", "sändningsnummer", "sandningsnr", "sandnings nr", "sandningsnummer", "shipment"]
    plock_keywords = ["plockpallsnr", "plockpallsnr.", "plockpall", "plockpallnr", "plockpallsnummer", "plockpall nr"]

    ov_order_col = _find_keywords_column(ov_df, order_keywords)
    ov_ship_col = _find_keywords_column(ov_df, ship_keywords)
    if not ov_order_col or not ov_ship_col:
        raise KeyError("Kunde inte identifiera order- eller sändningskolumnen i orderöversikten.")

    dp_order_col = _find_keywords_column(dp_df, order_keywords)
    dp_ship_col = _find_keywords_column(dp_df, ship_keywords)
    plock_col = _find_keywords_column(dp_df, plock_keywords)
    if not dp_order_col or not dp_ship_col or not plock_col:
        raise KeyError("Kunde inte identifiera order-, sändnings- eller plockpallskolumnen i dispatchfilen.")

    ov_df[ov_order_col] = ov_df[ov_order_col].astype(str).str.strip()
    ov_df[ov_ship_col] = ov_df[ov_ship_col].astype(str).str.strip()
    dp_df[dp_order_col] = dp_df[dp_order_col].astype(str).str.strip()
    dp_df[dp_ship_col] = dp_df[dp_ship_col].astype(str).str.strip()
    dp_df[plock_col] = dp_df[plock_col].astype(str).str.strip()

    overview_customer_col = _find_customer_name_column(ov_df, exclude={ov_order_col, ov_ship_col})
    order_to_customer = _build_order_to_customer_map(details_df, ov_df, ov_order_col, overview_customer_col)

    order_to_ship: Dict[str, str] = {}
    try:
        for order_number, sub in ov_df.groupby(ov_order_col):
            ships = [value for value in sub[ov_ship_col] if isinstance(value, str) and value.strip()]
            if ships:
                order_to_ship[str(order_number).strip()] = ships[0].strip()
    except Exception:
        pass

    diff_rows: List[Dict[str, object]] = []
    for _, row in dp_df.iterrows():
        try:
            order_number = str(row[dp_order_col]).strip()
            dispatch_ship = str(row[dp_ship_col]).strip()
            expected_ship = order_to_ship.get(order_number)
            if expected_ship and expected_ship != dispatch_ship:
                diff_rows.append(
                    {
                        "Ordernr": order_number,
                        "Översikt sändningsnr": expected_ship,
                        "Dispatch sändningsnr": dispatch_ship,
                        "Plockpallsnr": str(row[plock_col]).strip(),
                        "kundnamn": order_to_customer.get(order_number, ""),
                    }
                )
        except Exception:
            continue

    diff_df = pd.DataFrame(diff_rows) if diff_rows else pd.DataFrame()

    log_lines: list[str] = []
    if not diff_df.empty:
        log_lines.append("Dispatchkontrollen har hittat avvikelser mellan orderöversikten och dispatchpallar:")
        for _, row in diff_df.iterrows():
            try:
                name_part = f" ({row['kundnamn']})" if str(row.get("kundnamn", "")).strip() else ""
                log_lines.append(
                    "Order "
                    f"{row['Ordernr']}{name_part} har sändningsnr {row['Översikt sändningsnr']} "
                    f"i översikten men {row['Dispatch sändningsnr']} i dispatch "
                    f"(plockpall {row['Plockpallsnr']})"
                )
            except Exception:
                continue

    return DispatchCheckResult(diff_df, log_lines)


def build_vecka27_check_result(orders_df: pd.DataFrame) -> Vecka27CheckResult:
    if not isinstance(orders_df, pd.DataFrame) or orders_df.empty:
        return Vecka27CheckResult([], "", pd.DataFrame(columns=["Avvikelse"]), [])

    work_df = _clean_columns(orders_df.copy())
    cols = _find_ordersaldo_columns(work_df)
    order_col = cols.get("order")
    article_col = cols.get("article")
    demand_col = cols.get("demand")
    if not order_col or not article_col or not demand_col:
        raise KeyError("Hittar inte order-, artikel- eller antalskolumn i beställningsfilen.")

    work = work_df[[order_col, article_col, demand_col]].copy()
    work[order_col] = work[order_col].astype(str).str.strip()
    work[article_col] = work[article_col].astype(str).str.strip()
    work[demand_col] = work[demand_col].map(to_num).astype(float)

    grouped = work.groupby([order_col, article_col])[demand_col].sum(min_count=1)
    deviations: list[str] = []
    for order_id, sub in grouped.groupby(level=0):
        if not str(order_id).upper().startswith("PR"):
            continue
        art_qty: dict[str, float] = {}
        for (_, art), qty in sub.items():
            if pd.notna(qty):
                art_qty[str(art)] = float(qty)
        for roof, mowers in VECKA27_ROOF_TO_MOWERS.items():
            roof_qty = art_qty.get(roof, 0.0)
            if roof_qty <= 0:
                continue
            mower_qty = sum(art_qty.get(mower, 0.0) for mower in mowers)
            if mower_qty < roof_qty:
                mower_list = "/".join(sorted(mowers))
                deviations.append(
                    f"Order {order_id} har {_vecka27_fmt_qty_value(roof_qty)} st av {roof} "
                    f"men endast {_vecka27_fmt_qty_value(mower_qty)} st gräsklippare av {mower_list}."
                )

    if not deviations:
        return Vecka27CheckResult([], "", pd.DataFrame(columns=["Avvikelse"]), ["Vecka 27: inga avvikelser."])

    report_text = "Hej Lina!\n" + "\n".join(deviations) + "\nHur gör vi med denna/dessa?\n"
    report_df = pd.DataFrame({"Avvikelse": deviations})
    log_lines = [f"Vecka 27: {len(deviations)} avvikelse(r).", *deviations]
    return Vecka27CheckResult(deviations, report_text, report_df, log_lines)


# Toppnivafunktioner lyfta ur App-klassen sa servern (warehouse_tools.engine)
# kan anvanda dem utan GUI:t. Se flows.py/engine.py.

def detect_file_type(path: str) -> str | None:
    """Försök avgöra vilken sorts fil det är (orders, buffer, automation, item, prognos, campaign).
    Returnerar en sträng med typen eller None om okänd.
    """
    import os
    import pandas as _pd
    ext = os.path.splitext(path)[1].lower().lstrip('.')
    base_name = os.path.basename(path).lower()
    wms_name_hints = {
        "v_ask_receive_log": "wms_receive",
        "v_ask_booking_putaway": "wms_booking",
        "v_ask_article_buffertpallet": "buffer",
        "v_ask_trans_log": "wms_trans",
        "v_ask_pick_log_full": "wms_pick",
        "v_ask_correct_log": "wms_correct",
    }
    for hint, file_type in wms_name_hints.items():
        if hint in base_name:
            return file_type
    # Filename hint fallback for buffer exports with varying schemas.
    generic_buffer_name_hints = (
        "buffertpall",
        "buffertpallet",
        "buffert_pall",
        "bufferpall",
        "bufferpallet",
        "buffer_pallet",
    )
    if any(hint in base_name for hint in generic_buffer_name_hints):
        return "buffer"
    if ext in ("xlsx", "xlsm", "xls"):
        try:
            df_c = read_campaign_xlsx(path)
            if isinstance(df_c, _pd.DataFrame) and not df_c.empty and list(df_c.columns) == ["Artikelnummer", "Antal styck"]:
                return "campaign"
        except Exception:
            pass
        try:
            df_p = read_prognos_xlsx(path)
            if isinstance(df_p, _pd.DataFrame) and not df_p.empty and len(df_p.columns) >= 3 and any(str(c).strip().lower() in ("antal styck", "quantity", "qty") for c in df_p.columns):
                return "prognos"
        except Exception:
            pass
        return None
    try:
        df = _pd.read_csv(path, dtype=str, nrows=50, sep=None, engine="python", encoding="utf-8-sig")
        if df.shape[1] == 1:
            df = _pd.read_csv(path, dtype=str, nrows=50, sep="\t", engine="python", encoding="utf-8-sig")
    except Exception:
        try:
            df = _pd.read_csv(path, dtype=str, nrows=50, sep="\t", engine="python", encoding="utf-8-sig")
        except Exception:
            return None
    cols = [str(c).strip().lower() for c in df.columns]
    has_art = any(c in ("artikel", "artikelnummer", "artnr", "art.nr", "sku", "article") for c in cols)
    has_qty = any(c in ("beställt", "antal", "qty", "quantity", "bestalld", "order qty", "antal styck") for c in cols)
    has_ord = any(c in ("ordernr", "order nr", "order number", "kund", "kundnr", "order id") for c in cols)
    has_rad = any(c in ("radnr", "rad nr", "line id", "rad", "struktur", "radsnr") for c in cols)
    if has_art and has_qty and (has_ord or has_rad):
        return "orders"
    has_lagerplats = any("lagerplats" in c or "plats" == c or "location" == c or "bin" == c for c in cols)
    has_pallid = any(c in ("pallid", "pall id", "id", "sscc", "etikett", "batch") for c in cols)
    has_status = any(c == "status" for c in cols)
    has_inkop = any("inköpsnr" in c or "inkopsnr" in c for c in cols)
    has_mottaget = any("mottaget" in c for c in cols)
    has_pallnr = any("pall nr" in c or "pallnr" in c for c in cols)
    has_till = any(c == "till" or c.endswith(" till") or c.startswith("till ") for c in cols)
    has_fran = any("från" in c or "fran" in c for c in cols)
    has_plockat = any("plockat" in c for c in cols)
    has_anledning = any("anledning" in c for c in cols)

    if has_inkop and has_art and has_pallid and has_mottaget:
        return "wms_receive"
    if has_inkop and (has_pallnr or has_pallid) and not has_mottaget and not has_plockat:
        return "wms_booking"
    if has_lagerplats and has_pallid and has_inkop:
        return "buffer"
    if has_pallid and has_till and has_fran:
        return "wms_trans"
    if has_pallid and has_plockat and has_ord:
        return "wms_pick"
    if has_anledning and has_qty:
        return "wms_correct"

    if has_art and has_qty and has_lagerplats:
        return "buffer"
    # Buffer exports can include saldo-like columns. Keep buffer precedence.
    buffer_marker_count = sum(
        1 for flag in (has_lagerplats, has_pallid, has_status, has_inkop, has_mottaget, has_pallnr) if flag
    )
    if has_art and (has_qty or has_pallid) and buffer_marker_count >= 2:
        return "buffer"
    has_pack = any("pack klass" in c or "staplingsbar" in c for c in cols)
    # Om filen innehåller pack‑relaterade kolumner ("pack klass" eller "staplingsbar"),
    # kontrollera först om den också motsvarar en dispatchfil. Dispatchfiler har
    # plockpallskolumn samt både ordernummer och sändningsinformation. Utan denna
    # kontroll klassificerades dispatchpallar felaktigt som item.
    if has_pack:
        # dispatch‑indikatorer
        has_plockpall = any("plockpall" in c for c in cols)
        has_dispatch_order = any(c in ("ordernr", "order nr", "order number", "ordernummer") for c in cols)
        has_dispatch_ship = any(
            ("sändnings" in c) or ("sandnings" in c) or ("sändningsnr" in c) or ("sandningsnr" in c) or ("sändningsnr." in c) or ("sandningsnr." in c)
            for c in cols
        )
        # om dispatchindikatorer hittas, återgå "dispatch" istället för "item"
        if has_plockpall and has_dispatch_order and has_dispatch_ship:
            return "dispatch"
        return "item"
    # Ny detektering för orderöversikt (overview)
    has_ordernr = any(c in ("ordernr", "order nr", "order number") for c in cols)
    has_orderdatum = any("orderdatum" in c for c in cols)
    has_sandning = any("sändningsnr" in c or "sandningsnr" in c or "sändningsnr." in c or "sandnr" in c for c in cols)
    has_ordertyp = any("ordertyp" in c for c in cols)
    has_multi = any("multi" == c for c in cols)
    # kräver flera av dessa kolumner för att identifiera en orderöversikt
    if has_ordernr and has_orderdatum and has_sandning and has_ordertyp:
        return "overview"
    # Ny detektering för dispatchpallar (dispatch)
    has_plockpall = any("plockpall" in c for c in cols)
    has_dispatch_order = any(c in ("ordernr", "order nr", "order number", "ordernummer") for c in cols)
    has_dispatch_ship = any(
        ("sändnings" in c) or ("sandnings" in c) or ("sändningsnr" in c) or ("sandningsnr" in c) or ("sändningsnr." in c) or ("sandningsnr." in c)
        for c in cols
    )
    if has_plockpall and has_dispatch_order and has_dispatch_ship:
        return "dispatch"
    has_robot = any(c == "robot" for c in cols)
    has_saldo = any(("saldo autoplock" in c) or (c == "plocksaldo") or (c == "plock saldo") for c in cols)
    if has_art and (has_robot or has_saldo):
        return "automation"
    return None


def reclassify_skrymmande(result_df: pd.DataFrame, saldo_norm: pd.DataFrame | None) -> pd.DataFrame:
    """
    Omklassificera rader utifrån orderfilens zonkod.

    Efter att HELPALL‑ och AUTOSTORE‑allokeringar är bestämda (dvs. Källtyp
    "HELPALL" respektive "AUTOSTORE"), sätts Källtyp och "Zon (beräknad)"
    för övriga rader baserat på den befintliga "Zon"‑kolumnen i
    beställningsfilen. Följande mappning används (zon → (källtyp, zon)):

      * "S" → ("SKRYMMANDE",   "S")
      * "E" → ("EHANDEL",      "E")
      * "A" → ("HUVUDPLOCK",   "A")
      * "Q" → ("EHANDEL",      "Q")
      * "O" → ("SKRYMMANDE",   "O")
      * "F" → ("HIB",          "F")

    Rader vars Källtyp redan är "HELPALL" eller "AUTOSTORE" lämnas
    oförändrade. Om ingen "Zon"‑kolumn hittas returneras oförändrat DataFrame.
    Den medskickade saldofil används inte i denna metod.
    """
    if result_df is None or result_df.empty:
        return result_df
    res = result_df.copy()
    zon_col = None
    for c in res.columns:
        if str(c).strip().lower() == "zon":
            zon_col = c
            break
    if not zon_col:
        return res
    if "Zon (beräknad)" not in res.columns:
        res["Zon (beräknad)"] = ""
    ktyp_series = res.get("Källtyp", pd.Series("", index=res.index)).astype(str)
    mask_to_change = ~(ktyp_series.isin(["HELPALL", "AUTOSTORE"]))
    if not mask_to_change.any():
        return res
    mapping: Dict[str, Tuple[str, str]] = {
        "S": ("SKRYMMANDE",   "S"),
        "E": ("EHANDEL",      "E"),
        "A": ("HUVUDPLOCK",   "A"),
        "Q": ("EHANDEL",      "Q"),
        "O": ("SKRYMMANDE",   "O"),
        "F": ("HIB",          "F"),
        "D": ("DISPLAY",      "D"),
    }
    zones = res.loc[mask_to_change, zon_col].astype(str).str.strip().str.upper()
    for zone_code, (ktyp_val, zon_val) in mapping.items():
        idx = res.loc[mask_to_change].index[zones == zone_code]
        if len(idx) > 0:
            res.loc[idx, "Källtyp"] = ktyp_val
            res.loc[idx, "Zon (beräknad)"] = zon_val
    return res


def _read_cli_table(path: str) -> pd.DataFrame:
    """Las en tabellfil for CLI-kommandon och normalisera kolumnnamn."""
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"Filen finns inte: {target}")

    suffix = target.suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"}:
        return _clean_columns(pd.read_excel(target, dtype=str))

    try:
        df = pd.read_csv(target, dtype=str, sep=None, engine="python", encoding="utf-8-sig")
        if df.shape[1] == 1 and len(df):
            first = str(df.iloc[0, 0])
            if "\t" in first:
                df = pd.read_csv(target, dtype=str, sep="\t", engine="python", encoding="utf-8-sig")
    except Exception:
        df = pd.read_csv(target, dtype=str, sep="\t", engine="python", encoding="utf-8-sig")
    return _clean_columns(df)


def _write_cli_dataframe(df: pd.DataFrame, path: str) -> str:
    """Skriv DataFrame till CSV/XLSX/JSON beroende pa filandelse."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    suffix = target.suffix.lower()

    if suffix == ".xlsx":
        df.to_excel(target, index=False, engine="openpyxl")
    elif suffix == ".json":
        target.write_text(df.to_json(orient="records", force_ascii=False, indent=2), encoding="utf-8")
    else:
        df.to_csv(target, index=False, encoding="utf-8-sig")
    return str(target.resolve())


def _write_cli_workbook(sheets: Dict[str, pd.DataFrame], path: str) -> str:
    """Skriv flera blad till en Excel-fil."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() != ".xlsx":
        raise ValueError("Flerbladsutskrift kraver .xlsx som utfil.")
    with pd.ExcelWriter(target, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=str(sheet_name)[:31] or "Sheet1", index=False)
    return str(target.resolve())


def _write_cli_list(values: list[str], path: str, column_name: str) -> str:
    """Skriv en lista till TXT, CSV, XLSX eller JSON."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    suffix = target.suffix.lower()

    if suffix in {"", ".txt"}:
        target.write_text("\n".join(str(value) for value in values), encoding="utf-8")
        return str(target.resolve())
    if suffix == ".json":
        target.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(target.resolve())
    return _write_cli_dataframe(pd.DataFrame({column_name: values}), str(target))


def _emit_cli_summary(summary: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(summary, ensure_ascii=True))
        return
    for key, value in summary.items():
        print(f"{key}: {value}")


def _load_utbest_map_from_saldo_path(path: Optional[str]) -> Dict[str, float]:
    if not path:
        return {}
    saldo_df = _read_cli_table(path)
    return utbest_per_article(saldo_df)


def _df_with_named_index(df: pd.DataFrame, index_name: str) -> pd.DataFrame:
    out = df.copy()
    out.index = out.index.map(lambda value: str(value).strip())
    return out.reset_index().rename(columns={"index": index_name})


def _merge_item_flags(result_df: pd.DataFrame, item_norm: pd.DataFrame | None) -> pd.DataFrame:
    if not isinstance(result_df, pd.DataFrame) or result_df.empty:
        return result_df

    result = result_df.copy()
    if not isinstance(item_norm, pd.DataFrame) or item_norm.empty:
        if "Ej Staplingsbar" not in result.columns:
            result["Ej Staplingsbar"] = ""
        cols = [c for c in result.columns if c != "Ej Staplingsbar"] + ["Ej Staplingsbar"]
        return result[cols]

    art_col_res = find_col(result, ORDER_SCHEMA["artikel"], required=True)
    merged = result.merge(item_norm, how="left", left_on=art_col_res, right_on="Artikel", suffixes=("", "_item"))
    if "Artikel_item" in merged.columns:
        merged.drop(columns=["Artikel_item"], inplace=True, errors=False)
    if "Artikel_y" in merged.columns:
        merged.drop(columns=["Artikel_y"], inplace=True, errors=False)
    if "Ej Staplingsbar_y" in merged.columns:
        merged["Ej Staplingsbar"] = merged["Ej Staplingsbar_y"].fillna("")
    elif "Ej Staplingsbar_x" in merged.columns:
        merged["Ej Staplingsbar"] = merged["Ej Staplingsbar_x"].fillna("")
    elif "Ej Staplingsbar" not in merged.columns:
        merged["Ej Staplingsbar"] = ""
    for col in ["Ej Staplingsbar_x", "Ej Staplingsbar_y"]:
        if col in merged.columns:
            merged.drop(columns=[col], inplace=True)
    cols = [c for c in merged.columns if c != "Ej Staplingsbar"] + ["Ej Staplingsbar"]
    return merged[cols]


def _resolve_max_csv_path(explicit_path: Optional[str]) -> Path:
    if explicit_path:
        target = Path(explicit_path)
        if not target.exists():
            raise FileNotFoundError(f"Filen finns inte: {target}")
        return target

    found = _find_lyx_max_csv()
    if found is None:
        raise FileNotFoundError("Kunde inte hitta lowfreqdata/buffertpall/artikel_max.csv.")
    return found


def _read_cli_text_lines(path: str) -> list[str]:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"Filen finns inte: {target}")
    try:
        text = target.read_text(encoding="utf-8-sig")
    except Exception:
        text = target.read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines() if line.strip()]


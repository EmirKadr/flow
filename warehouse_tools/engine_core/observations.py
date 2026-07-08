"""Bufferpall-observationer, artikel-max och GitHub-synk."""
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

from .constants import (
    BUFFER_SCHEMA,
    DEFAULT_OBSERVATIONS_BUSINESS_CODE,
)
from .io_utils import (
    find_col,
)
from .runtime_paths import (
    _app_config_path,
    _business_path_segment,
    _normalise_observations_business_code,
    _seed_bufferpall_runtime_file,
)

OBSERVATIONS_FILENAME = "observations.csv.gz"

OBSERVATIONS_COLS = ["artikelnummer", "pallid", "antal"]

GITHUB_REPO = "EmirKadr/flow"

GITHUB_OBS_BRANCH = "data/community-observations"

GITHUB_OBS_DIR = "warehouse_tools/vendor/lowfreqdata/buffertpall"

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

    if df.empty:
        pd.DataFrame(columns=["artikelnummer", "max", "pallid"]).to_csv(
            ut_path, index=False, encoding="utf-8-sig"
        )
        return 0

    # Vektoriserad motsvarighet till _max_utan_outlier per artikel: ta max efter
    # att övre Tukey-outliers (antal > q3 + 1.5*IQR) tagits bort. Ersätter en
    # for-loop som materialiserade en subframe + körde np.percentile/idxmax per
    # grupp. quantile default interpolation = "linear" = np.percentile default.
    # För grupper med <=2 rader ger fönstret ovre >= max, så masken släpper
    # igenom allt -> samma som originalets fallback (rå idxmax). idxmax (INTE
    # sort_values+drop_duplicates) bevarar tie-break: första förekomsten av max
    # i indexordning, exakt som originalets sub["antal"].idxmax().
    g = df.groupby("artikelnummer")["antal"]
    q1 = df["artikelnummer"].map(g.quantile(0.25))
    q3 = df["artikelnummer"].map(g.quantile(0.75))
    ovre = (q3 + 1.5 * (q3 - q1)).to_numpy()
    mask = df["antal"].to_numpy() <= ovre
    filt = pd.Series(np.where(mask, df["antal"].to_numpy(), -np.inf), index=df.index)
    idx = filt.groupby(df["artikelnummer"], sort=True).idxmax()
    res = df.loc[idx.to_numpy()]

    pd.DataFrame(
        {
            "artikelnummer": res["artikelnummer"].to_numpy(),
            "max": res["antal"].astype(float).to_numpy(),
            "pallid": res["pallid"].astype(str).to_numpy(),
        },
        columns=["artikelnummer", "max", "pallid"],
    ).to_csv(ut_path, index=False, encoding="utf-8-sig")
    return len(res)

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

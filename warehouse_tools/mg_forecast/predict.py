"""
Iteration: Keep the physical pallet/master feature winner, and add a
large-order tail correction on top because it improved the walk-forward MAE
without hurting hit-rate.
"""
import os

import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb

os.environ.setdefault("MESTERGRUPPEN_USE_TRAINING_CACHE", "1")

_MIN_SAMPLES_FOR_CARRIER = 20
_DEFAULT_SHRINKAGE_K = 12
_TAIL_SKRYM_ESTIMATE_MIN = 4.0
_TAIL_SKRYM_SHRINKAGE_K = 20
_TAIL_SKRYM_CORR_CAP = 1.5
_TAIL_SKRYM_STAGE2_SHRINKAGE_K = 10
_TAIL_SKRYM_STAGE2_CORR_CAP = 1.0
_LARGE_ORDER_SHRINKAGE_K = 24
_LARGE_ORDER_CORR_CAP = 0.75


def _round_half(value: float) -> float:
    """Round to nearest 0.5, minimum 0."""
    return max(0.0, round(value * 2) / 2)


def _build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Engineer features - focus on proven high-correlation features + temporal patterns."""
    df = df.copy()
    for col_name in (
        "sum_palltype_flakmeter_est",
        "n_langpall_rader",
        "n_extra_langa_pallrader",
        "sum_langpall_estimate",
        "sum_extra_langa_pall_estimate",
        "max_palltype_langd",
    ):
        if col_name not in df.columns:
            df[col_name] = 0.0

    # Log transforms for heavy-tailed features.
    df["sum_vikt_log"] = np.log1p(df["sum_vikt_brutto"].clip(lower=0))
    df["sum_bestallt_log"] = np.log1p(df["sum_bestallt"].clip(lower=1))
    df["n_rader_log"] = np.log1p(df["n_rader"].clip(lower=1))
    df["n_artiklar_log"] = np.log1p(df["n_artiklar"].clip(lower=1))
    df["order_vikt_log"] = np.log1p(df["order_vikt_huvud"].clip(lower=0))
    df["order_antal_log"] = np.log1p(df["order_antal_huvud"].clip(lower=0))

    # Multi-order features.
    df["n_multi_huvud_log"] = np.log1p(df["n_multi_huvud"].clip(lower=0))
    df["multi_ratio"] = df["n_multi_huvud"] / df["n_ordrar"].clip(lower=1)

    # Weight-to-estimate ratio.
    df["vikt_per_estimate"] = df["sum_vikt_brutto"] / df["pall_estimate"].clip(lower=0.1)
    df["artiklar_per_estimate"] = df["n_artiklar"] / df["pall_estimate"].clip(lower=0.1)

    # Customer height interactions.
    df["height_inverse"] = 280 / df["kund_max_hojd"].clip(lower=1)
    df["height_deficit"] = 280 - df["kund_max_hojd"]
    df["height_x_vikt"] = df["height_inverse"] * df["sum_vikt_brutto"]

    # Skrymmande items.
    df["skrymmande_ratio"] = df["n_skrymmande_rader"] / df["n_rader"].clip(lower=1)
    df["longpall_ratio"] = df["n_langpall_rader"] / df["n_rader"].clip(lower=1)
    df["longpall_est_share"] = df["sum_langpall_estimate"] / df["pall_estimate"].clip(lower=0.1)
    df["extra_lang_est_share"] = df["sum_extra_langa_pall_estimate"] / df["pall_estimate"].clip(lower=0.1)
    df["flakmeter_per_estimate"] = df["sum_palltype_flakmeter_est"] / df["pall_estimate"].clip(lower=0.1)
    df["max_physical_langd"] = df[["max_art_langd", "max_palltype_langd"]].fillna(0).max(axis=1)

    # Zone-based complexity.
    df["art_per_zone"] = df["n_artiklar"] / df["n_zoner"].clip(lower=1)
    df["vikt_per_zone"] = df["sum_vikt_brutto"] / df["n_zoner"].clip(lower=1)

    # Order consolidation signal.
    df["consolidation"] = df["n_artiklar"] / df["n_ordrar"].clip(lower=1)
    df["pall_est_per_order"] = df["pall_estimate"] / df["n_ordrar"].clip(lower=1)
    df["pall_est_x_zoner"] = df["pall_estimate"] * df["n_zoner"]
    df["robot_share_bestallt"] = df["sum_bestallt_robot"] / df["sum_bestallt"].clip(lower=1)
    df["robot_share_rader"] = df["n_robot_rader"] / df["n_rader"].clip(lower=1)
    df["robot_x_estimate"] = df["robot_share_bestallt"] * df["pall_estimate"]

    if "orderdatum" in df.columns:
        dow = df["orderdatum"].dt.dayofweek
        df["dow_sin"] = np.sin(2 * np.pi * dow / 7)
        df["dow_cos"] = np.cos(2 * np.pi * dow / 7)

        month = df["orderdatum"].dt.month
        df["month_sin"] = np.sin(2 * np.pi * month / 12)
        df["month_cos"] = np.cos(2 * np.pi * month / 12)

        df["week_of_year"] = df["orderdatum"].dt.isocalendar().week.astype(float)
        df["estimate_x_dow"] = df["pall_estimate"] * df["dow_cos"]
        df["estimate_x_month"] = df["pall_estimate"] * df["month_cos"]
        df["vikt_x_dow"] = df["sum_vikt_brutto"] * df["dow_cos"]
        df["estimate_x_week"] = df["pall_estimate"] * df["week_of_year"]

        df["is_friday"] = (dow == 4).astype(float)
        df["is_monday"] = (dow == 0).astype(float)
        df["is_weekend"] = (dow >= 5).astype(float)
        df["friday_estimate"] = df["is_friday"] * df["pall_estimate"]
        df["monday_estimate"] = df["is_monday"] * df["pall_estimate"]

    return df


def _calibrate(train: pd.DataFrame) -> dict:
    """Train stacked XGB + LGB ensemble with fixed blend=0.5 and shrinkage K=12."""
    train = _build_features(train)
    train["residual"] = train["pallplatser"] - train["pall_estimate"]

    feature_cols = [
        "sum_vikt_brutto",
        "sum_vikt_log",
        "n_rader",
        "n_rader_log",
        "n_artiklar",
        "n_artiklar_log",
        "n_ordrar",
        "n_zoner",
        "n_unika_palltyper",
        "sum_volym",
        "sum_bestallt_robot",
        "n_robot_rader",
        "order_vikt_huvud",
        "order_volym_huvud",
        "order_vikt_log",
        "order_antal_log",
        "n_multi_huvud_log",
        "multi_ratio",
        "max_art_hojd",
        "max_art_langd",
        "n_skrymmande_rader",
        "skrymmande_ratio",
        "n_artiklar_med_buffert",
        "n_status_30",
        "n_status_35",
        "n_ar_plockad",
        "kund_max_hojd",
        "height_inverse",
        "height_deficit",
        "height_x_vikt",
        "vikt_per_estimate",
        "artiklar_per_estimate",
        "art_per_zone",
        "vikt_per_zone",
        "consolidation",
        "pall_est_per_order",
        "pall_est_x_zoner",
        "robot_share_bestallt",
        "robot_share_rader",
        "robot_x_estimate",
        "dow_sin",
        "dow_cos",
        "month_sin",
        "month_cos",
        "week_of_year",
        "estimate_x_dow",
        "estimate_x_month",
        "vikt_x_dow",
        "estimate_x_week",
        "is_friday",
        "is_monday",
        "is_weekend",
        "friday_estimate",
        "monday_estimate",
        "sum_palltype_flakmeter_est",
        "n_langpall_rader",
        "n_extra_langa_pallrader",
        "sum_langpall_estimate",
        "sum_extra_langa_pall_estimate",
        "max_palltype_langd",
        "longpall_ratio",
        "longpall_est_share",
        "extra_lang_est_share",
        "flakmeter_per_estimate",
        "max_physical_langd",
    ]

    features_to_exclude = {
        "n_staplingsbara_rader",
        "n_ej_staplingsbara",
        "sum_helpalls_avvik",
        "n_packklasser",
    }

    available_cols = [c for c in feature_cols if c in train.columns and c not in features_to_exclude]

    best_blend = 0.5
    best_k = _DEFAULT_SHRINKAGE_K

    X_full = train[available_cols].fillna(0).clip(lower=0)
    y_full = train["residual"]

    lgb_model = lgb.LGBMRegressor(
        n_estimators=120,
        max_depth=4,
        learning_rate=0.08,
        num_leaves=12,
        min_child_samples=20,
        subsample=0.7,
        colsample_bytree=0.7,
        reg_alpha=0.5,
        reg_lambda=0.5,
        random_state=42,
        verbose=-1,
        objective="quantile",
        alpha=0.5,
    )
    lgb_model.fit(X_full, y_full)

    xgb_model = xgb.XGBRegressor(
        n_estimators=120,
        max_depth=4,
        learning_rate=0.08,
        min_child_weight=20,
        subsample=0.7,
        colsample_bytree=0.7,
        reg_alpha=0.5,
        reg_lambda=0.5,
        random_state=42,
        verbosity=0,
        objective="reg:squarederror",
    )
    xgb_model.fit(X_full, y_full)

    train["pred_lgb"] = lgb_model.predict(X_full)
    train["pred_xgb"] = xgb_model.predict(X_full)
    train["pred_residual"] = best_blend * train["pred_lgb"] + (1 - best_blend) * train["pred_xgb"]
    train["pred_total"] = train["pall_estimate"] + train["pred_residual"]
    train["final_error"] = train["pallplatser"] - train["pred_total"]

    global_bias = train["final_error"].median()
    carrier_bias = {"__GLOBAL__": global_bias}

    for transportor, group in train.groupby("transportor"):
        n = len(group)
        if n >= _MIN_SAMPLES_FOR_CARRIER:
            carrier_error = group["final_error"].median()
            shrink = n / (n + best_k)
            carrier_bias[transportor] = shrink * carrier_error + (1 - shrink) * global_bias
        else:
            carrier_bias[transportor] = global_bias

    tail_mask = (
        (train["pall_estimate"] >= _TAIL_SKRYM_ESTIMATE_MIN)
        & (train["n_skrymmande_rader"] > 0)
    )
    tail_correction = 0.0
    tail_n = int(tail_mask.sum())
    if tail_n > 0:
        tail_error = float(train.loc[tail_mask, "final_error"].mean())
        tail_error = min(max(tail_error, 0.0), _TAIL_SKRYM_CORR_CAP)
        tail_correction = tail_error * (tail_n / (tail_n + _TAIL_SKRYM_SHRINKAGE_K))

    carrier_lookup = train["transportor"].map(carrier_bias).fillna(carrier_bias["__GLOBAL__"])
    train["pred_after_tail"] = train["pred_total"] + carrier_lookup + tail_mask.astype(float) * tail_correction
    train["tail_residual_after_tail"] = train["pallplatser"] - train["pred_after_tail"]
    tail_stage2_correction = 0.0
    if tail_n > 0:
        tail_stage2_error = float(train.loc[tail_mask, "tail_residual_after_tail"].mean())
        tail_stage2_error = min(max(tail_stage2_error, 0.0), _TAIL_SKRYM_STAGE2_CORR_CAP)
        tail_stage2_correction = tail_stage2_error * (tail_n / (tail_n + _TAIL_SKRYM_STAGE2_SHRINKAGE_K))

    large_order_correction = 0.0
    large_mask = train["pall_estimate"] >= _TAIL_SKRYM_ESTIMATE_MIN
    train["pred_after_stage2"] = train["pred_after_tail"] + tail_mask.astype(float) * tail_stage2_correction
    large_n = int(large_mask.sum())
    if large_n > 0:
        large_error = float((train.loc[large_mask, "pallplatser"] - train.loc[large_mask, "pred_after_stage2"]).mean())
        large_error = min(max(large_error, 0.0), _LARGE_ORDER_CORR_CAP)
        large_order_correction = large_error * (large_n / (large_n + _LARGE_ORDER_SHRINKAGE_K))

    return {
        "lgb": lgb_model,
        "xgb": xgb_model,
        "feature_cols": available_cols,
        "carrier_bias": carrier_bias,
        "tail_correction": tail_correction,
        "tail_stage2_correction": tail_stage2_correction,
        "large_order_correction": large_order_correction,
        "blend_weight": best_blend,
        "shrinkage_K": best_k,
    }


def _load_train() -> pd.DataFrame:
    from .pipeline import build_training_data, split

    df = build_training_data()
    train, _ = split(df)
    return train


_CALIBRATION = _calibrate(_load_train())


def predict(features: pd.DataFrame) -> pd.Series:
    """Predict pallet spaces using fixed 0.5 blend XGB+LGB ensemble with carrier bias."""
    features = _build_features(features)

    available_cols = _CALIBRATION["feature_cols"]
    X = features[available_cols].fillna(0).clip(lower=0)

    residual_lgb = _CALIBRATION["lgb"].predict(X)
    residual_xgb = _CALIBRATION["xgb"].predict(X)
    blend = _CALIBRATION["blend_weight"]
    residual_pred = blend * residual_lgb + (1 - blend) * residual_xgb

    predictions = features["pall_estimate"] + residual_pred
    carrier_bias = _CALIBRATION["carrier_bias"]

    bias_lookup = features["transportor"].map(carrier_bias)
    bias_lookup = bias_lookup.fillna(carrier_bias["__GLOBAL__"])
    predictions = predictions + bias_lookup

    tail_mask = (
        (features["pall_estimate"] >= _TAIL_SKRYM_ESTIMATE_MIN)
        & (features["n_skrymmande_rader"] > 0)
    )
    predictions = predictions + tail_mask.astype(float) * _CALIBRATION.get("tail_correction", 0.0)
    predictions = predictions + tail_mask.astype(float) * _CALIBRATION.get("tail_stage2_correction", 0.0)

    large_mask = features["pall_estimate"] >= _TAIL_SKRYM_ESTIMATE_MIN
    predictions = predictions + large_mask.astype(float) * _CALIBRATION.get("large_order_correction", 0.0)

    predictions = np.clip(predictions, 0.0, None)
    predictions = pd.Series(predictions).apply(_round_half)
    predictions.index = features.index
    return predictions

#!/usr/bin/env python3
"""
price_forecast.py — XGBoost day-ahead price forecaster for NL electricity.

Auto-detects available data:
  data/nl_panel.parquet  → rich mode: 28 features (temporal, price lags,
                            load, wind, solar, generation mix)
  data/nl_day_ahead_prices.csv → basic mode: 7 features (temporal + price lags)
                                  same as original pipeline

Run entsoe_fetch_rich.py first to unlock rich-feature mode.

Outputs (same format regardless of mode — downstream scripts unchanged):
  data/price_model.joblib
  data/price_predictions.csv  [datetime_utc, actual, forecast, naive]
"""
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_DIR    = Path(__file__).parent / "data"
PANEL_FILE  = DATA_DIR / "nl_panel.parquet"
PRICES_CSV  = DATA_DIR / "nl_day_ahead_prices.csv"
MODEL_PATH  = DATA_DIR / "price_model.joblib"
PREDS_CSV   = DATA_DIR / "price_predictions.csv"

TARGET_COL = "price_da"
TEST_DAYS  = 60


def load_featured() -> pd.DataFrame:
    """Load data (panel or CSV) and return fully featured DataFrame.
    Called by spo_train.py so both scripts use the same feature set."""
    raw_df, _ = _load_raw()
    return build_features(raw_df)

# ── Basic feature set (price-only mode, backward-compatible) ──────────────────
BASIC_FEATURES = [
    "hour", "day_of_week", "month",
    "lag_24h", "lag_168h",
    "rolling_mean_24h", "rolling_std_24h",
]

# ── Rich feature set (used when nl_panel.parquet is available) ────────────────
RICH_FEATURES = [
    # temporal
    "sin_hour", "cos_hour", "sin_dow", "cos_dow", "sin_month", "cos_month",
    "is_weekend",
    # price lags
    "lag_1h", "lag_2h", "lag_24h", "lag_48h", "lag_168h",
    "rolling_mean_24h", "rolling_std_24h",
    "rolling_mean_168h", "rolling_std_168h",
    # supply-demand
    "load_forecast",
    "net_load_forecast",
    "renewable_share_forecast",
    "total_wind_forecast",
    "solar_forecast",
    # generation mix (lagged — known from previous day)
    "nuclear_lag24",
    "gas_lag24",
    "wind_total_lag24",
]

# Set at runtime by build_features()
FEATURE_COLS: list[str] = BASIC_FEATURES


def _load_raw() -> tuple[pd.DataFrame, bool]:
    """
    Return (dataframe, is_rich).
    Tries nl_panel.parquet first; falls back to nl_day_ahead_prices.csv.
    """
    if PANEL_FILE.exists():
        log.info("Loading rich panel → %s", PANEL_FILE)
        df = pd.read_parquet(PANEL_FILE)
        df.index = pd.to_datetime(df.index, utc=True)
        # Normalise index to datetime_utc column for downstream compat
        df = df.reset_index().rename(columns={"index": "datetime_utc"})
        # Legacy alias: some code uses price_eur_mwh
        if "price_da" in df.columns and "price_eur_mwh" not in df.columns:
            df["price_eur_mwh"] = df["price_da"]
        return df, True

    if not PRICES_CSV.exists():
        log.info("No data found — running entsoe_fetch …")
        import entsoe_fetch
        entsoe_fetch.main()

    log.info("Loading price-only CSV → %s", PRICES_CSV)
    df = pd.read_csv(PRICES_CSV)
    # Normalise column name
    if "price_eur_mwh" in df.columns and "price_da" not in df.columns:
        df["price_da"] = df["price_eur_mwh"]
    return df, False


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build temporal + lag + domain features.
    Auto-selects rich vs basic feature set based on available columns.
    Updates the module-level FEATURE_COLS so spo_train.py stays consistent.
    """
    global FEATURE_COLS

    df = df.copy()
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True)
    df = df.sort_values("datetime_utc").reset_index(drop=True)

    p = df[TARGET_COL]
    t = df["datetime_utc"]

    # ── Temporal (always present) ─────────────────────────────────────────────
    df["hour"]       = t.dt.hour
    df["day_of_week"]= t.dt.dayofweek
    df["month"]      = t.dt.month
    df["is_weekend"] = (t.dt.dayofweek >= 5).astype(int)

    df["sin_hour"]  = np.sin(2 * np.pi * df["hour"]  / 24)
    df["cos_hour"]  = np.cos(2 * np.pi * df["hour"]  / 24)
    df["sin_dow"]   = np.sin(2 * np.pi * df["day_of_week"] / 7)
    df["cos_dow"]   = np.cos(2 * np.pi * df["day_of_week"] / 7)
    df["sin_month"] = np.sin(2 * np.pi * df["month"] / 12)
    df["cos_month"] = np.cos(2 * np.pi * df["month"] / 12)

    # ── Price lags ────────────────────────────────────────────────────────────
    df["lag_1h"]   = p.shift(1)
    df["lag_2h"]   = p.shift(2)
    df["lag_24h"]  = p.shift(24)
    df["lag_48h"]  = p.shift(48)
    df["lag_168h"] = p.shift(168)

    df["rolling_mean_24h"]  = p.shift(1).rolling(24,  min_periods=12).mean()
    df["rolling_std_24h"]   = p.shift(1).rolling(24,  min_periods=12).std()
    df["rolling_mean_168h"] = p.shift(1).rolling(168, min_periods=48).mean()
    df["rolling_std_168h"]  = p.shift(1).rolling(168, min_periods=48).std()

    # ── Rich supply-demand features (only if panel has them) ──────────────────
    has_rich = {"load_forecast", "wind_onshore_forecast",
                "solar_forecast"}.issubset(df.columns)

    if has_rich:
        wind_fcst = (df.get("wind_onshore_forecast", 0)
                     + df.get("wind_offshore_forecast", 0))
        solar_fcst = df.get("solar_forecast", pd.Series(0, index=df.index))

        df["total_wind_forecast"]     = wind_fcst
        df["solar_forecast"]          = solar_fcst
        df["net_load_forecast"]       = df["load_forecast"] - wind_fcst - solar_fcst
        df["renewable_share_forecast"]= (wind_fcst + solar_fcst) / df["load_forecast"].replace(0, np.nan)

        # Lag actual generation (observable from previous day)
        if "nuclear_actual" in df.columns:
            df["nuclear_lag24"]    = df["nuclear_actual"].shift(24)
        if "gas_actual" in df.columns:
            df["gas_lag24"]        = df["gas_actual"].shift(24)
        wind_act = (df.get("wind_onshore_actual", 0)
                    + df.get("wind_offshore_actual", 0))
        df["wind_total_lag24"] = wind_act.shift(24)

        feat_candidates = RICH_FEATURES
        log.info("Rich feature mode: %d candidate features", len(feat_candidates))
    else:
        feat_candidates = BASIC_FEATURES
        log.info("Basic feature mode (run entsoe_fetch_rich.py for more features)")

    # Keep only features that were actually created and have data
    FEATURE_COLS = [f for f in feat_candidates if f in df.columns]

    return df.dropna(subset=FEATURE_COLS).reset_index(drop=True)


def _metrics(label: str, y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    mae  = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    r2   = r2_score(y_true, y_pred)
    log.info("%s  MAE=%.2f  RMSE=%.2f  R²=%.3f", label, mae, rmse, r2)
    return {"label": label, "mae": mae, "rmse": rmse, "r2": r2}


def main():
    raw_df, is_rich = _load_raw()
    df = build_features(raw_df)
    log.info("Feature dataset: %d rows, %d features (%s mode)",
             len(df), len(FEATURE_COLS), "rich" if is_rich else "basic")

    # ── Temporal train / test split ───────────────────────────────────────────
    cutoff = df["datetime_utc"].max() - pd.Timedelta(days=TEST_DAYS)
    train  = df[df["datetime_utc"] <= cutoff]
    test   = df[df["datetime_utc"] >  cutoff]
    log.info("Train: %d rows (up to %s) | Test: %d rows (%d days)",
             len(train), cutoff.date(), len(test), TEST_DAYS)

    X_tr, y_tr = train[FEATURE_COLS].values, train[TARGET_COL].values
    X_te, y_te = test[FEATURE_COLS].values,  test[TARGET_COL].values

    # Validation set for early stopping (last 10% of train)
    split_pt = int(len(X_tr) * 0.9)

    # ── XGBoost ───────────────────────────────────────────────────────────────
    model = XGBRegressor(
        n_estimators         = 1000,
        learning_rate        = 0.04,
        max_depth            = 6,
        min_child_weight     = 3,
        subsample            = 0.8,
        colsample_bytree     = 0.8,
        reg_alpha            = 0.1,
        reg_lambda           = 1.0,
        early_stopping_rounds= 50,
        random_state         = 42,
        n_jobs               = -1,
        verbosity            = 0,
    )
    model.fit(
        X_tr[:split_pt], y_tr[:split_pt],
        eval_set=[(X_tr[split_pt:], y_tr[split_pt:])],
        verbose=False,
    )

    y_pred  = model.predict(X_te)
    y_naive = test["lag_24h"].values   # persistence baseline

    xgb_stats   = _metrics("XGBoost     ", y_te, y_pred)
    naive_stats = _metrics("Naive lag-24", y_te, y_naive)

    skill = 1.0 - xgb_stats["mae"] / naive_stats["mae"]

    # ── Save ──────────────────────────────────────────────────────────────────
    joblib.dump(model, MODEL_PATH)
    log.info("Model saved → %s", MODEL_PATH)

    preds_df = test[["datetime_utc"]].copy()
    preds_df["actual"]   = y_te
    preds_df["forecast"] = y_pred
    preds_df["naive"]    = y_naive
    preds_df.to_csv(PREDS_CSV, index=False)
    log.info("Predictions → %s (%d rows)", PREDS_CSV, len(preds_df))

    # ── Summary ───────────────────────────────────────────────────────────────
    mode_tag = f"[RICH – {len(FEATURE_COLS)} features]" if is_rich else "[BASIC – 7 features]"
    print(f"\n=== Forecast Performance — 60-day test set  {mode_tag} ===")
    print(f"{'Model':<22}  {'MAE':>8}  {'RMSE':>8}  {'R²':>7}")
    print("-" * 54)
    for s in [xgb_stats, naive_stats]:
        print(f"{s['label']:<22}  {s['mae']:>8.2f}  {s['rmse']:>8.2f}  {s['r2']:>7.3f}")
    print(f"\nXGBoost skill vs naive:  {skill*100:.1f}% MAE reduction")

    importances = pd.Series(model.feature_importances_, index=FEATURE_COLS)
    print("\nTop-10 feature importances:")
    print(importances.nlargest(10).round(4).to_string())

    # SHAP (optional)
    try:
        import shap
        explainer  = shap.TreeExplainer(model)
        shap_vals  = explainer.shap_values(X_te)
        shap_df    = pd.DataFrame(shap_vals, columns=FEATURE_COLS)
        shap_df["datetime_utc"] = test["datetime_utc"].values
        shap_df.to_csv(DATA_DIR / "shap_values.csv", index=False)
        log.info("SHAP values → %s", DATA_DIR / "shap_values.csv")
    except Exception as exc:
        log.debug("SHAP skipped: %s", exc)


if __name__ == "__main__":
    main()

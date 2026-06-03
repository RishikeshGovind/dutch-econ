#!/usr/bin/env python3
"""
price_forecast.py — Train XGBoost model to forecast NL day-ahead electricity prices.

Features: hour-of-day, day-of-week, month, lag-24h, lag-168h, rolling 24h mean/std.
Compares against naive persistence baseline (same hour yesterday).

Output:
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

DATA_DIR = Path(__file__).parent / "data"
PRICES_CSV = DATA_DIR / "nl_day_ahead_prices.csv"
MODEL_PATH = DATA_DIR / "price_model.joblib"
PREDS_CSV = DATA_DIR / "price_predictions.csv"

TEST_DAYS = 60  # hold-out period

FEATURE_COLS = [
    "hour",
    "day_of_week",
    "month",
    "lag_24h",
    "lag_168h",
    "rolling_mean_24h",
    "rolling_std_24h",
]
TARGET_COL = "price_eur_mwh"


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True)
    df = df.sort_values("datetime_utc").reset_index(drop=True)

    p = df[TARGET_COL]
    df["hour"] = df["datetime_utc"].dt.hour
    df["day_of_week"] = df["datetime_utc"].dt.dayofweek
    df["month"] = df["datetime_utc"].dt.month

    # Lag features — shift prevents look-ahead
    df["lag_24h"] = p.shift(24)
    df["lag_168h"] = p.shift(168)

    # Rolling stats computed on already-observed prices
    df["rolling_mean_24h"] = p.shift(1).rolling(24, min_periods=12).mean()
    df["rolling_std_24h"] = p.shift(1).rolling(24, min_periods=12).std()

    return df.dropna(subset=FEATURE_COLS).reset_index(drop=True)


def _metrics(label: str, y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    r2 = r2_score(y_true, y_pred)
    log.info("%s  MAE=%.2f  RMSE=%.2f  R²=%.3f", label, mae, rmse, r2)
    return {"label": label, "mae": mae, "rmse": rmse, "r2": r2}


def main():
    # Auto-fetch data if not present
    if not PRICES_CSV.exists():
        log.info("Price data not found — running entsoe_fetch.py...")
        import entsoe_fetch
        entsoe_fetch.main()

    raw = pd.read_csv(PRICES_CSV)
    df = build_features(raw)
    log.info("Feature dataset: %d rows", len(df))

    # Train / test split by time
    cutoff = df["datetime_utc"].max() - pd.Timedelta(days=TEST_DAYS)
    train = df[df["datetime_utc"] <= cutoff]
    test = df[df["datetime_utc"] > cutoff]
    log.info(
        "Train: %d rows (up to %s) | Test: %d rows (%d days)",
        len(train), cutoff.date(), len(test), TEST_DAYS,
    )

    X_tr, y_tr = train[FEATURE_COLS].values, train[TARGET_COL].values
    X_te, y_te = test[FEATURE_COLS].values, test[TARGET_COL].values

    # XGBoost regressor
    model = XGBRegressor(
        n_estimators=500,
        learning_rate=0.04,
        max_depth=6,
        min_child_weight=3,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        n_jobs=-1,
        verbosity=0,
    )
    model.fit(
        X_tr, y_tr,
        eval_set=[(X_te, y_te)],
        verbose=False,
    )

    y_pred = model.predict(X_te)
    xgb_stats = _metrics("XGBoost     ", y_te, y_pred)

    # Naive baseline: predict = price at same hour yesterday
    y_naive = test["lag_24h"].values
    naive_stats = _metrics("Naive lag-24", y_te, y_naive)

    skill_score = 1.0 - xgb_stats["mae"] / naive_stats["mae"]

    # Save
    joblib.dump(model, MODEL_PATH)
    log.info("Model saved → %s", MODEL_PATH)

    preds_df = test[["datetime_utc"]].copy()
    preds_df["actual"] = y_te
    preds_df["forecast"] = y_pred
    preds_df["naive"] = y_naive
    preds_df.to_csv(PREDS_CSV, index=False)
    log.info("Predictions saved → %s (%d rows)", PREDS_CSV, len(preds_df))

    # Summary table
    print("\n=== Forecast Performance (60-day test set) ===")
    print(f"{'Model':<22}  {'MAE':>8}  {'RMSE':>8}  {'R²':>7}")
    print("-" * 54)
    for s in [xgb_stats, naive_stats]:
        print(
            f"{s['label']:<22}  {s['mae']:>8.2f}  {s['rmse']:>8.2f}  {s['r2']:>7.3f}"
        )
    print(f"\nXGBoost skill score vs. naive: {skill_score * 100:.1f}% MAE reduction")

    # Feature importance summary
    importances = pd.Series(model.feature_importances_, index=FEATURE_COLS)
    print("\nTop feature importances:")
    print(importances.sort_values(ascending=False).round(3).to_string())

    # SHAP values for test set — used by demo_chart.py for decision explainability
    try:
        import shap
        explainer = shap.TreeExplainer(model)
        shap_vals = explainer.shap_values(X_te)
        shap_df = pd.DataFrame(shap_vals, columns=FEATURE_COLS)
        shap_df["datetime_utc"] = test["datetime_utc"].values
        shap_df.to_csv(DATA_DIR / "shap_values.csv", index=False)
        log.info("SHAP values saved → %s", DATA_DIR / "shap_values.csv")
    except Exception as exc:
        log.warning("SHAP computation skipped: %s", exc)


if __name__ == "__main__":
    main()

"""
fiscal_ml_api.py  —  Denmark edition

FastAPI + XGBoost + SHAP for Danish municipality unemployment risk prediction.

Panel CSV columns (from ML Export tab):
    zone_code, zone_name, region, year,
    avg_income_dkk, population, foreign_citizens_pct,
    unemployment_rate_pct, crime_per_1000

Target:
    Will this municipality have ABOVE-median unemployment next year?
    (binary, same structure as the Austrian fiscal-distress model)

Endpoints:
    GET  /health
    GET  /model_performance
    GET  /feature_importance
    POST /predict_distress     ← high-unemployment risk score + risk tier
    POST /shap_explain         ← top SHAP drivers per zone
    POST /fiscal_forecast      ← multi-year unemployment risk projection
"""

import logging
import os
from typing import List, Optional

import joblib
import numpy as np
import pandas as pd
import shap
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    classification_report,
    roc_auc_score,
)
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
PANEL_PATH = os.path.join(BASE_DIR, "data", "panel_dataset.csv")
MODEL_PATH = os.path.join(BASE_DIR, "data", "dk_unemp_model.joblib")

# ── feature sets ───────────────────────────────────────────────────────────────
RAW_FEATURES = [
    "avg_income_dkk",
    "population",
    "foreign_citizens_pct",
    "crime_per_1000",
    "unemployment_rate_pct",
]

ENGINEERED_FEATURES = [
    "income_growth_pct",   # YoY % change in avg income
    "pop_growth_pct",      # YoY % change in population
    "foreign_pct_change",  # YoY pp change in foreign citizens %
    "crime_change",        # YoY change in crime rate per 1,000
    "unemp_lag1",          # unemployment rate in previous year (t-1)
    "unemp_trend",         # 3-year linear trend slope of unemployment
]

CATEGORICAL_FEATURES = ["region"]

ALL_FEATURES: List[str] = []
MODEL_META: dict = {}

# ── app ─────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Denmark Area ML API",
    description=(
        "XGBoost + SHAP predicts whether a Danish municipality will have "
        "above-median unemployment next year, using panel data 2012–2024."
    ),
    version="2.0.0",
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# Global state (loaded/trained once at startup)
panel: pd.DataFrame = None
panel_featured: pd.DataFrame = None
model: XGBClassifier = None
platt_scaler: LogisticRegression = None
explainer: shap.TreeExplainer = None
label_encoders: dict = {}
test_results: dict = {}
national_median_by_year: dict = {}
classification_threshold: float = 0.5  # overwritten during training with class prevalence


def _calibrated_proba(X: pd.DataFrame) -> np.ndarray:
    """Raw XGBoost probability → Platt-scaled calibrated probability."""
    raw = model.predict_proba(X)[:, 1].reshape(-1, 1)
    return platt_scaler.predict_proba(raw)[:, 1]


# ══════════════════════════════════════════════════════════════════════════════
# Feature engineering
# ══════════════════════════════════════════════════════════════════════════════

def _rolling_slope(arr: np.ndarray) -> float:
    arr = arr[~np.isnan(arr)]
    if len(arr) < 2:
        return np.nan
    return float(np.polyfit(np.arange(len(arr), dtype=float), arr, 1)[0])


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy().sort_values(["zone_code", "year"]).reset_index(drop=True)

    grp = df.groupby("zone_code")

    prev_income = grp["avg_income_dkk"].shift(1)
    prev_pop    = grp["population"].shift(1)

    df["income_growth_pct"]  = (df["avg_income_dkk"] - prev_income) / prev_income.replace(0, np.nan) * 100
    df["pop_growth_pct"]     = (df["population"]     - prev_pop)    / prev_pop.replace(0, np.nan)    * 100
    df["foreign_pct_change"] = df["foreign_citizens_pct"] - grp["foreign_citizens_pct"].shift(1)
    df["crime_change"]       = df["crime_per_1000"]       - grp["crime_per_1000"].shift(1)
    df["unemp_lag1"]         = grp["unemployment_rate_pct"].shift(1)
    df["unemp_trend"]        = (
        grp["unemployment_rate_pct"]
        .transform(lambda s: s.rolling(3, min_periods=2).apply(_rolling_slope, raw=True))
    )
    return df


def _expected_calibration_error(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    """Weighted mean absolute difference between predicted probability and observed frequency."""
    bins    = np.linspace(0.0, 1.0 + 1e-8, n_bins + 1)
    bin_idx = np.clip(np.digitize(y_prob, bins) - 1, 0, n_bins - 1)
    n       = len(y_true)
    ece     = 0.0
    for b in range(n_bins):
        mask = bin_idx == b
        if not mask.any():
            continue
        ece += (mask.sum() / n) * abs(y_true[mask].mean() - y_prob[mask].mean())
    return float(ece)


# ══════════════════════════════════════════════════════════════════════════════
# Data preparation
# ══════════════════════════════════════════════════════════════════════════════

def prepare_data(df: pd.DataFrame):
    global label_encoders, ALL_FEATURES, national_median_by_year, panel_featured

    df = engineer_features(df)
    panel_featured = df

    # Cross-sectional median per year — kept for display in prediction endpoints only.
    med = df.groupby("year")["unemployment_rate_pct"].median()
    national_median_by_year = med.to_dict()

    # Expanding-window threshold: for year Y, estimate next year's median using only data ≤ Y.
    # Prevents validation/test-year statistics from leaking into training targets.
    years_sorted = sorted(df["year"].unique())
    expanding_threshold = {
        y + 1: df[df["year"] <= y]["unemployment_rate_pct"].median()
        for y in years_sorted
    }

    # Target: is next-year unemployment above the expanding-window estimate for that year?
    df["unemp_next"] = df.groupby("zone_code")["unemployment_rate_pct"].shift(-1)
    df["med_next"]   = (df["year"] + 1).map(expanding_threshold)
    df["target"]     = (df["unemp_next"] > df["med_next"]).astype(float)
    df = df.dropna(subset=["target"])
    df["target"] = df["target"].astype(int)

    # Encode categoricals
    for col in CATEGORICAL_FEATURES:
        if col in df.columns:
            le = LabelEncoder()
            df[col + "_enc"] = le.fit_transform(df[col].fillna("Unknown"))
            label_encoders[col] = le

    cat_enc    = [c + "_enc"  for c in CATEGORICAL_FEATURES if c in df.columns]
    avail_raw  = [f for f in RAW_FEATURES         if f in df.columns]
    avail_eng  = [f for f in ENGINEERED_FEATURES  if f in df.columns]
    ALL_FEATURES = avail_raw + avail_eng + cat_enc

    X    = df[ALL_FEATURES].copy()
    y    = df["target"]
    meta = df[["zone_code", "zone_name", "region", "year", "unemployment_rate_pct"]]
    return X, y, meta, df


# ══════════════════════════════════════════════════════════════════════════════
# Model training  (temporal split: train≤2018, val=2019, test≥2020)
# ══════════════════════════════════════════════════════════════════════════════

def train_model(X: pd.DataFrame, y: pd.Series, meta: pd.DataFrame):
    global model, platt_scaler, explainer, test_results, MODEL_META, classification_threshold

    train_m = meta["year"] <= 2018
    val_m   = meta["year"] == 2019
    test_m  = meta["year"] >= 2020

    X_tr, y_tr = X[train_m], y[train_m]
    X_va, y_va = X[val_m],   y[val_m]
    X_te, y_te = X[test_m],  y[test_m]

    logger.info(f"Train {len(X_tr)} | Val {len(X_va)} | Test {len(X_te)}")
    logger.info(f"Train high-unemp rate: {y_tr.mean():.2%}")

    neg, pos  = (y_tr == 0).sum(), (y_tr == 1).sum()
    scale_pos = (neg / pos) if pos > 0 else 1.0

    model = XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale_pos,
        eval_metric="auc",
        early_stopping_rounds=25,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)

    # Platt scaling: fit on train+val combined.
    # Val-only (99 samples, 12 positives) gives raw probs in a too-narrow range [0.43, 0.55]
    # for the LR to find a meaningful slope. Train+val gives more spread and reliable fit.
    X_trval   = pd.concat([X_tr, X_va])
    y_trval   = pd.concat([y_tr, y_va])
    raw_trval = model.predict_proba(X_trval)[:, 1].reshape(-1, 1)
    platt_scaler = LogisticRegression()
    platt_scaler.fit(raw_trval, y_trval)

    # Evaluate on test set using calibrated probabilities
    raw_te  = model.predict_proba(X_te)[:, 1]
    ece_raw = _expected_calibration_error(y_te.to_numpy(), raw_te)
    y_prob  = platt_scaler.predict_proba(raw_te.reshape(-1, 1))[:, 1]

    # Use training prevalence as threshold — correct after Platt scaling pulls probs to true prevalence
    classification_threshold = float(y_tr.mean())
    y_pred = (y_prob >= classification_threshold).astype(int)
    auc    = roc_auc_score(y_te, y_prob)
    ap     = average_precision_score(y_te, y_prob)
    report = classification_report(y_te, y_pred, output_dict=True)
    brier  = brier_score_loss(y_te, y_prob)
    ece    = _expected_calibration_error(y_te.to_numpy(), y_prob)

    test_results = {
        "auc_roc":          round(auc,     4),
        "avg_precision":    round(ap,      4),
        "brier_score":      round(brier,   4),
        "ece":              round(ece,     4),
        "ece_pre_calibration": round(ece_raw, 4),
        "accuracy":         round(report["accuracy"], 4),
        "precision_high":   round(report.get("1", {}).get("precision", 0), 4),
        "recall_high":      round(report.get("1", {}).get("recall",    0), 4),
        "f1_high":          round(report.get("1", {}).get("f1-score",  0), 4),
        "n_test":                    int(len(y_te)),
        "train_years":               "2012–2018",
        "test_years":                "2020–2023",
        "calibration":               "Platt scaling (logistic regression on validation probabilities)",
        "classification_threshold":  round(classification_threshold, 4),
    }
    logger.info(
        f"Test AUC: {auc:.4f} | AP: {ap:.4f} | Brier: {brier:.4f} "
        f"| ECE raw: {ece_raw:.4f} → calibrated: {ece:.4f}"
    )

    explainer = shap.TreeExplainer(model)
    MODEL_META = {
        "features":       ALL_FEATURES,
        "target":         "above_median_unemployment_next_year",
        "n_features":     len(ALL_FEATURES),
        "best_iteration": model.best_iteration,
        "scale_pos_weight": round(scale_pos, 2),
    }
    joblib.dump(
        {"model": model, "platt_scaler": platt_scaler,
         "label_encoders": label_encoders, "features": ALL_FEATURES,
         "national_median": national_median_by_year,
         "classification_threshold": classification_threshold},
        MODEL_PATH,
    )
    logger.info(f"Model saved → {MODEL_PATH}")


def _encode(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col, le in label_encoders.items():
        if col in df.columns:
            df[col + "_enc"] = df[col].apply(
                lambda v: le.transform([v])[0] if v in le.classes_ else -1
            )
    return df


# ══════════════════════════════════════════════════════════════════════════════
# Startup
# ══════════════════════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    global panel

    logger.info("Loading panel_dataset.csv …")
    if not os.path.exists(PANEL_PATH):
        logger.warning("panel_dataset.csv not found — ML endpoints will return 503.")
        return

    try:
        panel = pd.read_csv(PANEL_PATH)
        required = {"zone_code", "year", "unemployment_rate_pct"}
        if not required.issubset(panel.columns):
            raise ValueError(
                f"Missing columns {required - set(panel.columns)}. "
                f"Got: {list(panel.columns)}"
            )
        panel["zone_code"] = panel["zone_code"].astype(str).str.zfill(4)
        # Fill empty string values with NaN
        panel.replace("", np.nan, inplace=True)
        for col in RAW_FEATURES:
            if col in panel.columns:
                panel[col] = pd.to_numeric(panel[col], errors="coerce")
        logger.info(
            f"Panel: {len(panel):,} rows | {panel['zone_code'].nunique()} zones "
            f"| years {int(panel['year'].min())}–{int(panel['year'].max())}"
        )
    except Exception as e:
        logger.error(f"Failed to load panel_dataset.csv: {e}")
        panel = None
        return

    if os.path.exists(MODEL_PATH):
        logger.info("Loading cached model …")
        try:
            cached = joblib.load(MODEL_PATH)
            global model, platt_scaler, explainer, label_encoders, ALL_FEATURES
            global national_median_by_year, panel_featured, classification_threshold
            model                    = cached["model"]
            platt_scaler             = cached["platt_scaler"]
            label_encoders           = cached["label_encoders"]
            ALL_FEATURES             = cached["features"]
            national_median_by_year  = cached.get("national_median", {})
            classification_threshold = cached.get("classification_threshold", 0.5)
            explainer               = shap.TreeExplainer(model)
            panel_featured          = engineer_features(panel)
            logger.info("Cached model loaded.")
            return
        except Exception as e:
            logger.error(f"Cached model load failed: {e}. Retraining …")

    logger.info("Training XGBoost model …")
    X, y, meta, _ = prepare_data(panel)
    train_model(X, y, meta)
    logger.info("Training complete.")


# ══════════════════════════════════════════════════════════════════════════════
# Request schemas
# ══════════════════════════════════════════════════════════════════════════════

class ZoneRequest(BaseModel):
    ids:  List[str]
    year: Optional[int] = None

class ShapRequest(BaseModel):
    ids:   List[str]
    year:  Optional[int] = None
    top_n: Optional[int] = 8

class ForecastRequest(BaseModel):
    ids:     List[str]
    horizon: Optional[int] = 3


# ══════════════════════════════════════════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/health")
def health():
    return {
        "status":       "ok",
        "model_loaded": model is not None,
        "panel_rows":   len(panel) if panel is not None else 0,
        "latest_year":  int(panel["year"].max()) if panel is not None else None,
        "n_features":   len(ALL_FEATURES),
        "target":       "above_median_unemployment_next_year",
    }


@app.get("/model_performance")
def model_performance():
    if model is None:
        raise HTTPException(503, "Model not loaded.")
    return {
        "model":        "XGBoostClassifier",
        "meta":         MODEL_META,
        "test_metrics": test_results,
        "interpretation": {
            "target":         "1 = municipality will have above-median unemployment next year",
            "auc_roc":        "1.0 = perfect, 0.5 = random guess",
            "avg_precision":  "Better metric when classes are imbalanced",
            "recall_high":    "% of true high-unemployment cases the model catches",
            "brier_score":    "Mean squared error of predicted probabilities; 0.0 = perfect, 0.25 = uninformative baseline for balanced classes",
            "ece":            "Expected Calibration Error (10 bins); measures how well predicted probabilities match observed frequencies — 0.0 = perfectly calibrated",
        },
    }


@app.get("/feature_importance")
def feature_importance():
    if model is None or panel_featured is None:
        raise HTTPException(503, "Model not loaded.")

    sample = panel_featured.copy()
    sample = _encode(sample)
    avail  = [f for f in ALL_FEATURES if f in sample.columns]

    # Stratified sample: up to 200 rows per year so all temporal periods are represented
    strat = (
        sample
        .groupby("year", group_keys=False)
        .apply(lambda g: g.sample(n=min(len(g), 200), random_state=42))
        .reset_index(drop=True)
    )

    # Impute NaNs: ffill then bfill within each zone's time-ordered rows, then column median
    feat_df = strat[["zone_code", "year"] + avail].sort_values(["zone_code", "year"])
    feat_df[avail] = (
        feat_df.groupby("zone_code")[avail]
        .transform(lambda s: s.ffill().bfill())
    )
    col_medians = feat_df[avail].median()
    X_s = feat_df[avail].fillna(col_medians)

    sv       = explainer.shap_values(X_s)
    mean_abs = np.abs(sv).mean(axis=0)
    importance = sorted(
        [{"feature": f, "mean_shap": round(float(v), 5)}
         for f, v in zip(avail, mean_abs)],
        key=lambda x: x["mean_shap"], reverse=True,
    )
    return {
        "method":    "mean |SHAP| over stratified sample (all years, ≤200 rows/year)",
        "n_samples": len(X_s),
        "importance": importance,
    }


@app.post("/predict_distress")
def predict_distress(req: ZoneRequest):
    """Predict probability of above-median unemployment next year per zone."""
    if model is None or panel_featured is None:
        raise HTTPException(503, "Model not loaded.")

    # Default to second-latest year so we can still compare against known truth
    latest = int(panel["year"].max())
    yr     = req.year or (latest - 1)
    data   = panel_featured[
        panel_featured["zone_code"].isin(req.ids) &
        (panel_featured["year"] == yr)
    ].copy()

    if data.empty:
        raise HTTPException(404, f"No panel data for selected zones in year {yr}.")

    data  = _encode(data)
    avail = [f for f in ALL_FEATURES if f in data.columns]
    probs = _calibrated_proba(data[avail])
    nat_med = national_median_by_year.get(yr + 1, np.nan)

    results = []
    for i, (_, row) in enumerate(data.iterrows()):
        prob = float(probs[i])
        results.append({
            "zone_code":              row["zone_code"],
            "zone_name":              row.get("zone_name", ""),
            "region":                 row.get("region",    ""),
            "year_used":              yr,
            "predicts_year":          yr + 1,
            "high_unemp_probability": round(prob, 4),
            "predicted_high_unemp":   int(prob >= classification_threshold),
            "risk_category": (
                "High"   if prob >= 0.65 else
                "Medium" if prob >= 0.35 else
                "Low"
            ),
            "current_unemp_rate":    round(float(row.get("unemployment_rate_pct") or 0), 2),
            "national_median_unemp": round(float(nat_med), 2) if not np.isnan(nat_med) else None,
        })

    results.sort(key=lambda x: x["high_unemp_probability"], reverse=True)
    return {
        "model":  "XGBoostClassifier (Denmark)",
        "year":   yr,
        "target": f"Above-median unemployment in {yr + 1}",
        "zones":  results,
    }


@app.post("/shap_explain")
def shap_explain(req: ShapRequest):
    """Top SHAP drivers of unemployment risk for each zone."""
    if model is None or panel_featured is None:
        raise HTTPException(503, "Model not loaded.")

    latest = int(panel["year"].max())
    yr     = req.year or (latest - 1)
    top_n  = min(req.top_n or 8, len(ALL_FEATURES))
    data   = panel_featured[
        panel_featured["zone_code"].isin(req.ids) &
        (panel_featured["year"] == yr)
    ].copy()

    if data.empty:
        raise HTTPException(404, f"No data for selected zones in year {yr}.")

    data  = _encode(data)
    avail = [f for f in ALL_FEATURES if f in data.columns]
    X     = data[avail]
    sv    = explainer.shap_values(X)          # SHAP uses raw model internally
    base  = float(explainer.expected_value)
    probs = _calibrated_proba(X)

    explanations = []
    for i, (_, row) in enumerate(data.iterrows()):
        s     = sv[i]
        order = np.argsort(np.abs(s))[::-1][:top_n]
        explanations.append({
            "zone_code":              row["zone_code"],
            "zone_name":              row.get("zone_name", ""),
            "year":                   yr,
            "high_unemp_probability": round(float(probs[i]), 4),
            "base_probability":       round(float(1 / (1 + np.exp(-base))), 4),
            "top_drivers": [
                {
                    "feature":    avail[j],
                    "value":      round(float(X.iloc[i, j]), 4) if not pd.isna(X.iloc[i, j]) else None,
                    "shap_value": round(float(s[j]), 5),
                    "direction":  "increases_risk" if s[j] > 0 else "decreases_risk",
                }
                for j in order
            ],
            "interpretation": (
                "Each shap_value shows how much that feature pushes the "
                "prediction above (positive) or below (negative) the base rate."
            ),
        })

    return {
        "year":         yr,
        "base_rate":    round(float(1 / (1 + np.exp(-base))), 4),
        "explanations": explanations,
    }


@app.post("/fiscal_forecast")
def fiscal_forecast(req: ForecastRequest):
    """Multi-year unemployment risk forecast (iterative, indicative only)."""
    if model is None or panel_featured is None:
        raise HTTPException(503, "Model not loaded.")

    horizon = min(req.horizon or 3, 5)
    latest  = int(panel["year"].max())
    base_df = panel_featured[
        panel_featured["zone_code"].isin(req.ids) &
        (panel_featured["year"] == latest)
    ].copy()

    if base_df.empty:
        raise HTTPException(404, f"No base data for selected zones in {latest}.")

    forecasts = {z: [] for z in base_df["zone_code"].unique()}
    current   = base_df.copy()

    for step in range(horizon):
        pred_yr = latest + step + 1
        current = _encode(current)
        avail   = [f for f in ALL_FEATURES if f in current.columns]
        X       = current[avail]
        probs   = _calibrated_proba(X)
        preds   = (probs >= classification_threshold).astype(int)

        for i, (_, row) in enumerate(current.iterrows()):
            forecasts[row["zone_code"]].append({
                "year":                   pred_yr,
                "high_unemp_probability": round(float(probs[i]), 4),
                "predicted_high_unemp":   int(preds[i]),
            })

        # Roll forward: nudge unemployment up/down based on prediction
        current = current.copy()
        current["unemp_lag1"]            = current["unemployment_rate_pct"]
        current["unemployment_rate_pct"] = np.where(
            preds == 1,
            current["unemployment_rate_pct"] * 1.04,
            current["unemployment_rate_pct"] * 0.97,
        )
        current["year"] = pred_yr

    output = [
        {
            "zone_code": zc,
            "zone_name": base_df.loc[base_df["zone_code"] == zc, "zone_name"].iloc[0],
            "region":    base_df.loc[base_df["zone_code"] == zc, "region"].iloc[0],
            "base_year": latest,
            "forecast":  steps,
        }
        for zc, steps in forecasts.items()
    ]
    return {
        "base_year": latest,
        "horizon":   horizon,
        "note": (
            "Multi-year forecasts are scenario simulations, not statistical predictions. "
            "Uncertainty compounds at each step — treat as indicative planning only."
        ),
        "methodology": {
            "roll_forward": (
                "At each step the model classifies each zone as high/low risk (threshold 0.5). "
                "Unemployment is then nudged by a fixed heuristic: +4% if high-risk, -3% if low-risk. "
                "These multipliers (1.04 / 0.97) are not learned from data — they are rule-based scenario "
                "assumptions. Confidence intervals are not provided; true uncertainty grows non-linearly "
                "with horizon."
            ),
            "high_risk_unemployment_multiplier": 1.04,
            "low_risk_unemployment_multiplier":  0.97,
            "classification_threshold":          0.5,
            "max_horizon_years":                 5,
        },
        "zones": output,
    }

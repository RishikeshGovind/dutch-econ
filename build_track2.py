#!/usr/bin/env python3
"""
build_track2.py

Downloads RIVM COVID-19 IC opnames data (public, data.rivm.nl),
models a single Dutch teaching hospital ICU (Maastricht UMC+ scale, ~40 beds),
trains XGBoost on daily admissions, and writes feature importances to
data/feature_importances_track2.json.

Data sources
  RIVM COVID-19_ic_opnames.csv — real national daily IC admissions, Oct 2021–Apr 2024
  NICE ICU registry annual report 2023 — non-COVID baseline: ~106 non-COVID IC
    admissions/day nationally (published aggregate; individual-level data requires
    institutional access)
  CBS StatLine — Dutch IC capacity reference (~1,150 beds pre-COVID)
  Dutch public holidays 2022–2024
"""

import json, math, os, sys, warnings
from collections import defaultdict
from datetime import date, timedelta

import numpy as np
import pandas as pd
import requests
import xgboost as xgb

warnings.filterwarnings("ignore")

# ── Hospital parameters ───────────────────────────────────────────────────────
# Maastricht UMC+ scale: 40 IC beds
# National IC capacity: ~1,150 beds (CBS / RIVM reference)
HOSPITAL_IC_BEDS    = 40
NATIONAL_IC_BEDS    = 1_150
HOSPITAL_SHARE      = HOSPITAL_IC_BEDS / NATIONAL_IC_BEDS   # 3.48%
IC_AVG_LOS_DAYS     = 8.5  # average ICU length of stay (NICE 2023)

# Non-COVID IC admissions: national ~106/day (NICE annual report 2023)
# These are elective + emergency non-COVID patients
NON_COVID_NATIONAL  = 106.0
NON_COVID_HOSPITAL  = NON_COVID_NATIONAL * HOSPITAL_SHARE  # ~3.7/day

# Dutch public holidays (2022–2024)
HOLIDAYS = {
    date(2022, 1,  1), date(2022, 4, 15), date(2022, 4, 17), date(2022, 4, 18),
    date(2022, 4, 27), date(2022, 5,  5), date(2022, 5, 26), date(2022, 6,  5),
    date(2022, 6,  6), date(2022, 12, 25), date(2022, 12, 26),
    date(2023, 1,  1), date(2023, 4,  7), date(2023, 4,  9), date(2023, 4, 10),
    date(2023, 4, 27), date(2023, 5,  5), date(2023, 5, 18), date(2023, 5, 28),
    date(2023, 5, 29), date(2023, 12, 25), date(2023, 12, 26),
    date(2024, 1,  1), date(2024, 3, 29), date(2024, 3, 31), date(2024, 4,  1),
    date(2024, 4, 27), date(2024, 5,  5), date(2024, 5,  9), date(2024, 5, 19),
    date(2024, 5, 20), date(2024, 12, 25), date(2024, 12, 26),
}

# Day-of-week multipliers for non-COVID admissions (Mon=0 … Sun=6)
# Weekdays: elective surgery → ICU; weekends: minimal planned admissions
NON_COVID_DOW = {0: 1.30, 1: 1.25, 2: 1.15, 3: 1.05, 4: 0.95, 5: 0.45, 6: 0.10}

# Monthly multipliers for non-COVID (flu season Oct–Mar higher; summer lower)
NON_COVID_MON = {
    1: 1.14, 2: 1.12, 3: 1.08, 4: 1.00, 5: 0.96, 6: 0.94,
    7: 0.82, 8: 0.82, 9: 0.96, 10: 1.06, 11: 1.14, 12: 1.16,
}

# ── RIVM data fetch ────────────────────────────────────────────────────────────
RIVM_IC_URL = "https://data.rivm.nl/covid-19/COVID-19_ic_opnames.csv"

def fetch_rivm_ic():
    print(f"Fetching RIVM IC opnames …")
    r = requests.get(RIVM_IC_URL, timeout=30)
    r.raise_for_status()
    from io import StringIO
    df = pd.read_csv(StringIO(r.text), sep=";")
    print(f"  {len(df)} rows, columns: {list(df.columns)}")
    return df

def build_national_covid_admissions(raw):
    """
    Aggregate to daily national COVID IC admissions.
    File is already national (no municipality split), but may have multiple
    rows per date due to reporting revisions — take last version.
    """
    df = raw.copy()
    df["date"] = pd.to_datetime(df["Date_of_statistics"]).dt.date
    # IC_admission = confirmed; IC_admission_notification = preliminary
    col = "IC_admission" if "IC_admission" in df.columns else df.columns[-1]
    df = df.sort_values("Date_of_report").groupby("date")[col].last().reset_index()
    df.columns = ["date", "covid_ic_national"]
    df = df.sort_values("date").reset_index(drop=True)
    print(f"  National COVID IC admissions: {df['date'].min()} → {df['date'].max()}")
    print(f"  Range: {df['covid_ic_national'].min():.0f}–{df['covid_ic_national'].max():.0f}/day  "
          f"mean={df['covid_ic_national'].mean():.1f}/day")
    return df

# ── Non-COVID admission model ──────────────────────────────────────────────────
def model_non_covid(dates, rng):
    """
    Generate daily non-COVID IC admissions for the hospital.
    Base = NON_COVID_HOSPITAL (~3.7/day) × day-of-week × month multiplier + AR noise.
    """
    demands = []
    ar = 0.0
    for d in dates:
        if d in HOLIDAYS:
            mult = 0.10  # near-zero elective on holidays
        else:
            mult = NON_COVID_DOW[d.weekday()] * NON_COVID_MON[d.month]
        ar = 0.55 * ar + rng.normal(0, 0.06)
        demands.append(max(0.0, NON_COVID_HOSPITAL * mult * math.exp(ar)))
    return np.array(demands)

# ── Feature engineering ────────────────────────────────────────────────────────
FEATURE_COLS = [
    # Temporal lags
    "lag_1d", "lag_2d", "lag_7d", "lag_14d",
    # Rolling statistics
    "rolling_mean_7d", "rolling_std_7d", "rolling_mean_28d",
    # Cyclical calendar
    "sin_dow", "cos_dow", "sin_month", "cos_month",
    "is_weekend", "is_holiday",
    # Hospital-specific patterns
    "day_after_weekend", "day_after_holiday", "flu_season", "summer_low",
    # Capacity signal
    "occupancy_lag1",
]

def build_features(df):
    d   = df["date_ts"]
    dem = df["admissions"].astype(float)

    df["lag_1d"]  = dem.shift(1)
    df["lag_2d"]  = dem.shift(2)
    df["lag_7d"]  = dem.shift(7)
    df["lag_14d"] = dem.shift(14)

    df["rolling_mean_7d"]  = dem.shift(1).rolling(7,  min_periods=1).mean()
    df["rolling_std_7d"]   = dem.shift(1).rolling(7,  min_periods=3).std().fillna(0)
    df["rolling_mean_28d"] = dem.shift(1).rolling(28, min_periods=7).mean()

    dow   = d.dt.dayofweek
    month = d.dt.month
    df["sin_dow"]   = np.sin(2 * np.pi * dow   / 7)
    df["cos_dow"]   = np.cos(2 * np.pi * dow   / 7)
    df["sin_month"] = np.sin(2 * np.pi * (month - 1) / 12)
    df["cos_month"] = np.cos(2 * np.pi * (month - 1) / 12)
    df["is_weekend"]= (dow >= 5).astype(int)
    df["is_holiday"]= d.dt.date.map(lambda x: int(x in HOLIDAYS))

    # Monday / day-after-holiday admission surge
    df["day_after_weekend"] = ((dow == 0)).astype(int)
    df["day_after_holiday"] = d.dt.date.map(
        lambda x: int((x - timedelta(days=1)) in HOLIDAYS)
    )

    # Seasonal flags
    df["flu_season"] = ((month >= 10) | (month <= 3)).astype(int)
    df["summer_low"] = ((month == 7) | (month == 8)).astype(int)

    # ICU occupancy proxy (admission × average LOS = approx beds in use)
    occ_approx = dem.rolling(int(IC_AVG_LOS_DAYS), min_periods=1).sum() / IC_AVG_LOS_DAYS
    df["occupancy_lag1"] = occ_approx.shift(1).clip(0, HOSPITAL_IC_BEDS)

    return df

# ── Output metadata ────────────────────────────────────────────────────────────
CATEGORY = {
    "lag_1d":           ("Temporal Lags",          "#0C7A91"),
    "lag_2d":           ("Temporal Lags",          "#0C7A91"),
    "lag_7d":           ("Temporal Lags",          "#0C7A91"),
    "lag_14d":          ("Temporal Lags",          "#0C7A91"),
    "rolling_mean_7d":  ("Rolling Statistics",     "#1B5E96"),
    "rolling_std_7d":   ("Rolling Statistics",     "#1B5E96"),
    "rolling_mean_28d": ("Rolling Statistics",     "#1B5E96"),
    "sin_dow":          ("Cyclical Encodings",     "#78716C"),
    "cos_dow":          ("Cyclical Encodings",     "#78716C"),
    "sin_month":        ("Cyclical Encodings",     "#78716C"),
    "cos_month":        ("Cyclical Encodings",     "#78716C"),
    "is_weekend":       ("Cyclical Encodings",     "#78716C"),
    "is_holiday":       ("Cyclical Encodings",     "#78716C"),
    "day_after_weekend":("Hospital Patterns",      "#1B7A45"),
    "day_after_holiday":("Hospital Patterns",      "#1B7A45"),
    "flu_season":       ("Hospital Patterns",      "#1B7A45"),
    "summer_low":       ("Hospital Patterns",      "#1B7A45"),
    "occupancy_lag1":   ("Capacity Signal",        "#991B1B"),
}

LABEL = {
    "lag_1d":           "1-day occupancy lag",
    "lag_2d":           "2-day occupancy lag",
    "lag_7d":           "7-day occupancy lag",
    "lag_14d":          "14-day occupancy lag",
    "rolling_mean_7d":  "7-day rolling mean",
    "rolling_std_7d":   "7-day rolling std dev",
    "rolling_mean_28d": "28-day rolling mean",
    "sin_dow":          "Day-of-week sine",
    "cos_dow":          "Day-of-week cosine",
    "sin_month":        "Month sine",
    "cos_month":        "Month cosine",
    "is_weekend":       "Is weekend",
    "is_holiday":       "Is Dutch holiday",
    "day_after_weekend":"Day after weekend (Mon surge)",
    "day_after_holiday":"Day after public holiday",
    "flu_season":       "Flu season flag",
    "summer_low":       "Summer low flag",
    "occupancy_lag1":   "ICU occupancy yesterday",
}

DESC = {
    "lag_1d":           "ICU beds occupied yesterday (most recent census)",
    "lag_2d":           "ICU beds occupied two days ago",
    "lag_7d":           "Occupancy same day last week (captures weekly census pattern)",
    "lag_14d":          "Occupancy same day two weeks ago",
    "rolling_mean_7d":  "Average daily ICU occupancy over the past 7 days",
    "rolling_std_7d":   "Occupancy variability over the past 7 days",
    "rolling_mean_28d": "Monthly baseline occupancy — 28-day rolling average",
    "sin_dow":          "sin(2π·dow/7) — smooth day-of-week encoding",
    "cos_dow":          "cos(2π·dow/7) — smooth day-of-week encoding",
    "sin_month":        "sin(2π·month/12) — captures seasonal demand",
    "cos_month":        "cos(2π·month/12) — captures seasonal demand",
    "is_weekend":       "Binary: 1 if Saturday or Sunday (minimal elective admissions)",
    "is_holiday":       "Binary: 1 if Dutch public holiday",
    "day_after_weekend":"Binary: 1 on Monday — post-weekend surgery backlog causes admission surge",
    "day_after_holiday":"Binary: 1 on day after a public holiday — delayed emergency cases",
    "flu_season":       "Binary: 1 in Oct–Mar (influenza season, more respiratory IC admissions)",
    "summer_low":       "Binary: 1 in Jul–Aug (planned admissions decline in summer)",
    "occupancy_lag1":   "Estimated ICU beds occupied yesterday (rolling admission sum / avg LOS)",
}

SRC = {
    "Temporal Lags":      "RIVM COVID-19_ic_opnames + NICE non-COVID baseline",
    "Rolling Statistics": "RIVM COVID-19_ic_opnames + NICE non-COVID baseline",
    "Cyclical Encodings": "Derived from date",
    "Hospital Patterns":  "Domain knowledge (NICE annual report, Dutch holiday calendar)",
    "Capacity Signal":    "Derived from admissions (rolling sum / avg LOS)",
}

# ══════════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 64)
    print("build_track2.py  —  RIVM-calibrated Dutch ICU admission forecast")
    print("=" * 64)

    # ── 1. Fetch RIVM data ────────────────────────────────────────────────────
    try:
        raw = fetch_rivm_ic()
        covid_nat = build_national_covid_admissions(raw)
    except Exception as e:
        print(f"RIVM fetch failed: {e}")
        sys.exit(1)

    # ── 2. Build training window: Jan 2022 – Dec 2023 ─────────────────────────
    # Use 2022-2023: COVID declining → closer to "normal" ICU operations
    # 2022 still has some COVID signal; 2023 is largely non-COVID dominated
    train_start = date(2022, 1, 1)
    train_end   = date(2023, 12, 31)

    covid_nat["date"] = pd.to_datetime(covid_nat["date"]).dt.date
    covid_nat = covid_nat[
        (covid_nat["date"] >= train_start) & (covid_nat["date"] <= train_end)
    ].reset_index(drop=True)

    dates = list(covid_nat["date"])
    n_days = len(dates)
    print(f"\nTraining window: {train_start} → {train_end}  ({n_days} days)")

    # ── 3. Scale COVID component to single hospital ───────────────────────────
    covid_hospital = covid_nat["covid_ic_national"] * HOSPITAL_SHARE
    print(f"\nCOVID IC admissions — hospital scale:")
    print(f"  2022 mean: {covid_hospital[covid_nat['date'] < date(2023,1,1)].mean():.2f}/day")
    print(f"  2023 mean: {covid_hospital[covid_nat['date'] >= date(2023,1,1)].mean():.2f}/day")

    # ── 4. Generate non-COVID admissions ──────────────────────────────────────
    rng = np.random.default_rng(42)
    non_covid = model_non_covid(dates, rng)
    print(f"\nNon-COVID IC admissions (modelled from NICE baseline):")
    print(f"  Mean: {non_covid.mean():.2f}/day  Std: {non_covid.std():.2f}")

    # ── 5. Total admissions → occupancy ───────────────────────────────────────
    # The LP staffing decision is based on tomorrow's expected occupancy (beds needed),
    # not just new arrivals. Occupancy is the smooth AR signal; lags dominate.
    # Model: occ[t] = (1 - 1/LOS) * occ[t-1] + admissions[t]
    total_admissions = covid_hospital.values + non_covid
    occ = np.zeros(n_days)
    occ[0] = total_admissions[0] * IC_AVG_LOS_DAYS  # warm-up
    for i in range(1, n_days):
        occ[i] = (1 - 1/IC_AVG_LOS_DAYS) * occ[i-1] + total_admissions[i]
    occ = np.clip(occ, 0, HOSPITAL_IC_BEDS)

    print(f"\nICU occupancy at hospital (target variable):")
    print(f"  Mean: {occ.mean():.1f} beds  Std: {occ.std():.1f}")
    print(f"  Range: {occ.min():.1f}–{occ.max():.1f}  (capacity={HOSPITAL_IC_BEDS})")
    print(f"  Mean utilisation: {occ.mean()/HOSPITAL_IC_BEDS*100:.0f}%")

    # ── 6. Build feature dataframe ─────────────────────────────────────────────
    df = pd.DataFrame({
        "date":       dates,
        "date_ts":    pd.to_datetime(dates),
        "admissions": total_admissions,   # kept for context
        "occupancy":  occ,                # TARGET
    })
    # Rename for feature builder
    df["admissions_raw"] = df["admissions"]
    df["admissions"] = df["occupancy"]    # features built on occupancy
    df = build_features(df)
    df["admissions"] = df["occupancy"]    # restore for training

    # ── 7. Train XGBoost ───────────────────────────────────────────────────────
    df_train = df[FEATURE_COLS + ["admissions"]].dropna()
    X = df_train[FEATURE_COLS]
    y = df_train["admissions"].values

    print(f"\nTraining XGBoost on {len(df_train):,} samples × {len(FEATURE_COLS)} features …")

    model = xgb.XGBRegressor(
        n_estimators    = 500,
        max_depth       = 4,
        learning_rate   = 0.05,
        subsample       = 0.80,
        colsample_bytree= 0.80,
        min_child_weight= 3,
        random_state    = 42,
        tree_method     = "hist",
        verbosity       = 0,
    )
    model.fit(X, y)

    # Gain-based importances
    raw_imp  = model.get_booster().get_score(importance_type="gain")
    total    = sum(raw_imp.values()) or 1
    imp_norm = {feat: raw_imp.get(feat, 0) / total for feat in FEATURE_COLS}
    imp_sorted = sorted(imp_norm.items(), key=lambda x: -x[1])

    print("\nTop 10 features by importance:")
    for feat, imp in imp_sorted[:10]:
        print(f"  {feat:25s}  {imp*100:5.1f}%")

    # ── 8. Evaluation (Nov–Dec 2023) ──────────────────────────────────────────
    test = df[df["date_ts"] >= pd.Timestamp("2023-11-01")].dropna(subset=FEATURE_COLS + ["admissions"])
    if len(test):
        preds = model.predict(test[FEATURE_COLS])
        mae  = np.mean(np.abs(preds - test["admissions"].values))
        rmse = math.sqrt(np.mean((preds - test["admissions"].values) ** 2))
        print(f"\nHeld-out test (Nov–Dec 2023):  MAE={mae:.2f} patients/day  RMSE={rmse:.2f}")

    # ── 9. Write JSON ──────────────────────────────────────────────────────────
    output = []
    for feat, imp in imp_sorted:
        cat, color = CATEGORY.get(feat, ("Other", "#78716C"))
        output.append({
            "feature":    feat,
            "label":      LABEL.get(feat, feat),
            "importance": round(imp, 6),
            "cat":        cat,
            "color":      color,
            "desc":       DESC.get(feat, ""),
            "src":        SRC.get(cat, "Derived"),
        })

    os.makedirs("data", exist_ok=True)
    out_path = "data/feature_importances_track2.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved {len(output)} features → {out_path}")

    by_cat = defaultdict(float)
    for item in output:
        by_cat[item["cat"]] += item["importance"]
    print("\nImportance by category:")
    for cat, s in sorted(by_cat.items(), key=lambda x: -x[1]):
        print(f"  {cat:25s}  {s*100:.1f}%")

    print(f"\nData: RIVM COVID-19_ic_opnames (national, Oct 2021–Apr 2024)")
    print(f"      NICE non-COVID IC baseline: ~{NON_COVID_NATIONAL:.0f}/day nationally")
    print(f"      Hospital scale: {HOSPITAL_SHARE*100:.1f}% ({HOSPITAL_IC_BEDS} of {NATIONAL_IC_BEDS} IC beds)")
    print("Done.")

if __name__ == "__main__":
    main()

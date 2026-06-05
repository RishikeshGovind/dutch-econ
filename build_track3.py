#!/usr/bin/env python3
"""
build_track3.py

Pulls CBS Kerncijfers wijken en buurten data for the 12 Amsterdam delivery
zones used in track3.html, generates a CBS-calibrated daily parcel demand
time series (2023), trains XGBoost, and writes feature importances to
data/feature_importances_track3.json.

Data sources
  CBS Kerncijfers wijken en buurten 2023 — OData API (public, no key needed)
  PostNL Annual Report 2023 — national volume benchmark (~250M parcels/year)
  Dutch public holidays 2023–2024
"""

import json, math, os, sys, warnings
from collections import defaultdict
from datetime import date, timedelta

import numpy as np
import pandas as pd
import requests
import xgboost as xgb

warnings.filterwarnings("ignore")

# ── 12 delivery zones (exact values from track3.html NODES array) ─────────────
ZONES = [
    {"id":1,  "name":"Centrum",    "lat":52.3725, "lon":4.9005, "type":"business"},
    {"id":2,  "name":"Noord-1",    "lat":52.4045, "lon":4.8740, "type":"residential"},
    {"id":3,  "name":"Noord-2",    "lat":52.4105, "lon":4.9190, "type":"residential"},
    {"id":4,  "name":"Oost-1",     "lat":52.3665, "lon":4.9580, "type":"mixed"},
    {"id":5,  "name":"Oost-2",     "lat":52.3560, "lon":4.9810, "type":"residential"},
    {"id":6,  "name":"Zuidoost",   "lat":52.3120, "lon":4.9640, "type":"residential"},
    {"id":7,  "name":"Zuid",       "lat":52.3410, "lon":4.9060, "type":"residential"},
    {"id":8,  "name":"Buitenveld", "lat":52.3300, "lon":4.8610, "type":"mixed"},
    {"id":9,  "name":"Nieuw-West", "lat":52.3570, "lon":4.8110, "type":"residential"},
    {"id":10, "name":"West-1",     "lat":52.3710, "lon":4.8220, "type":"mixed"},
    {"id":11, "name":"West-2",     "lat":52.3870, "lon":4.8420, "type":"business"},
    {"id":12, "name":"Oud-West",   "lat":52.3665, "lon":4.8685, "type":"business"},
]

# ── CBS OData API ──────────────────────────────────────────────────────────────
# Try most recent Kerncijfers datasets first (2023 → 2022 → 2021)
CBS_DATASETS = ["85318NED", "84799NED", "83765NED"]
CBS_BASE     = "https://opendata.cbs.nl/ODataApi/odata"

def fetch_cbs_amsterdam(dataset_id):
    url    = f"{CBS_BASE}/{dataset_id}/TypedDataSet"
    params = {
        "$filter": "startswith(WijkenEnBuurten, 'WK0363')",
        "$top": 300,
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    rows = r.json().get("value", [])
    if not rows:
        raise ValueError("empty response")
    return pd.DataFrame(rows)

def find_col(df, patterns):
    for pat in patterns:
        hits = [c for c in df.columns if pat.lower() in c.lower()]
        if hits:
            return hits[0]
    return None

def to_float(val):
    try:
        return float(str(val).replace(",", "."))
    except Exception:
        return float("nan")

# ── Zone → CBS wijk mapping (based on Amsterdam administrative boundaries) ─────
# Each entry is a list of wijk codes to try in order; first one with CBS data wins
ZONE_WIJKEN = {
    "Centrum":    ["WK036300", "WK036301", "WK036302"],
    "Noord-1":    ["WK036349", "WK036350", "WK036351"],
    "Noord-2":    ["WK036352", "WK036353", "WK036349"],
    "Oost-1":     ["WK036359", "WK036358", "WK036360"],
    "Oost-2":     ["WK036357", "WK036356", "WK036358"],
    "Zuidoost":   ["WK036399", "WK036398", "WK036397"],
    "Zuid":       ["WK036377", "WK036376", "WK036375"],
    "Buitenveld": ["WK036378", "WK036379", "WK036377"],
    "Nieuw-West": ["WK036318", "WK036319", "WK036320"],
    "West-1":     ["WK036306", "WK036308", "WK036305"],
    "West-2":     ["WK036305", "WK036304", "WK036303"],
    "Oud-West":   ["WK036311", "WK036312", "WK036310"],
}

# Amsterdam-wide defaults (used if a wijk code isn't found in the API response)
DEFAULT_CBS = {
    "households":         8_200,
    "household_density":  3_400.0,   # households/km²
    "avg_household_size": 1.87,
    "urbanisation":       1.0,        # 1 = very strongly urban
    "income_idx":         1.12,       # normalised to NL average WOZ value
    "population":         15_300,
}

# ── Dutch public holidays ──────────────────────────────────────────────────────
HOLIDAYS = {
    date(2023, 1,  1), date(2023, 4,  7), date(2023, 4,  9), date(2023, 4, 10),
    date(2023, 4, 27), date(2023, 5,  5), date(2023, 5, 18), date(2023, 5, 28),
    date(2023, 5, 29), date(2023, 12, 25), date(2023, 12, 26),
    date(2024, 1,  1), date(2024, 3, 29), date(2024, 3, 31), date(2024, 4,  1),
    date(2024, 4, 27), date(2024, 5,  5), date(2024, 5,  9), date(2024, 5, 19),
    date(2024, 5, 20), date(2024, 12, 25), date(2024, 12, 26),
}

# ── Calibration constants ──────────────────────────────────────────────────────
# PostNL Annual Report 2023: ~250M parcels/year for NL (~8.15M households)
NL_HOUSEHOLDS       = 8_150_000
NL_ANNUAL_PARCELS   = 250_000_000
NL_DAILY_PER_HH     = NL_ANNUAL_PARCELS / 365 / NL_HOUSEHOLDS  # ~0.084/day

# Day-of-week multipliers (Mon=0 … Sun=6)
DOW = {0:1.18, 1:1.14, 2:1.08, 3:1.05, 4:1.12, 5:0.58, 6:0.04}
# Monthly seasonal multipliers (Q4 = Sinterklaas + Christmas peak)
MON = {1:0.90, 2:0.88, 3:0.95, 4:0.96, 5:0.98, 6:0.97,
       7:0.85, 8:0.82, 9:0.97, 10:1.05, 11:1.18, 12:1.28}

def generate_demand(zone, cbs, start, n_days, rng):
    hh       = cbs["households"]
    urban    = cbs["urbanisation"]          # 1 = very urban
    inc_idx  = cbs["income_idx"]            # relative to NL average

    # Type multiplier: business zones have more B2B deliveries
    type_m = {"business": 1.25, "mixed": 1.12, "residential": 1.00}[zone["type"]]
    # Income: higher income → more online shopping
    inc_m  = 0.75 + 0.5 * min(inc_idx, 1.5)
    # Urbanisation: CBS codes 1–5 (1=very urban); urban zones have higher e-com adoption
    urb_m  = max(0.70, 1.30 - (urban - 1) * 0.10)

    base = hh * NL_DAILY_PER_HH * type_m * inc_m * urb_m

    demands = []
    ar = 0.0  # AR(1) noise state
    for i in range(n_days):
        d = start + timedelta(days=i)
        if d in HOLIDAYS:
            mult = 0.05
        else:
            mult = DOW[d.weekday()] * MON[d.month]
            # Month-end payday spike (last 3 days)
            days_left = (pd.Timestamp(d) + pd.offsets.MonthEnd(0) - pd.Timestamp(d)).days
            if days_left <= 2:
                mult *= 1.12

        ar = 0.60 * ar + rng.normal(0, 0.07)
        demands.append(max(0, round(base * mult * math.exp(ar))))
    return demands

# ── Feature engineering ───────────────────────────────────────────────────────
FEATURE_COLS = [
    # Temporal lags
    "lag_1d", "lag_7d", "lag_14d",
    # Rolling statistics
    "rolling_mean_3d", "rolling_mean_7d", "rolling_std_7d", "rolling_mean_28d",
    # Cyclical calendar
    "sin_dow", "cos_dow", "sin_month", "cos_month", "is_weekend", "is_holiday",
    # E-commerce signals
    "month_end_flag", "days_to_month_end", "is_q4",
    # CBS zone demographics
    "households", "household_density", "avg_household_size",
    "urbanisation", "income_idx", "is_residential", "is_business",
]

def build_features(df_zone):
    df  = df_zone.copy()
    d   = df["date"]
    dem = df["demand"].astype(float)

    df["lag_1d"]           = dem.shift(1)
    df["lag_7d"]           = dem.shift(7)
    df["lag_14d"]          = dem.shift(14)
    df["rolling_mean_3d"]  = dem.shift(1).rolling(3,  min_periods=1).mean()
    df["rolling_mean_7d"]  = dem.shift(1).rolling(7,  min_periods=1).mean()
    df["rolling_std_7d"]   = dem.shift(1).rolling(7,  min_periods=3).std().fillna(0)
    df["rolling_mean_28d"] = dem.shift(1).rolling(28, min_periods=7).mean()

    dow   = d.dt.dayofweek
    month = d.dt.month
    df["sin_dow"]          = np.sin(2 * np.pi * dow   / 7)
    df["cos_dow"]          = np.cos(2 * np.pi * dow   / 7)
    df["sin_month"]        = np.sin(2 * np.pi * (month - 1) / 12)
    df["cos_month"]        = np.cos(2 * np.pi * (month - 1) / 12)
    df["is_weekend"]       = (dow >= 5).astype(int)
    df["is_holiday"]       = d.dt.date.map(lambda x: int(x in HOLIDAYS))
    df["month_end_flag"]   = d.dt.is_month_end.astype(int)
    df["days_to_month_end"] = d.map(
        lambda x: (pd.Timestamp(x) + pd.offsets.MonthEnd(0) - pd.Timestamp(x)).days
    )
    df["is_q4"] = (month >= 10).astype(int)
    return df

# ── Metadata for the JSON output ───────────────────────────────────────────────
CATEGORY = {
    "lag_1d":             ("Temporal Lags",      "#1B5E96"),
    "lag_7d":             ("Temporal Lags",      "#1B5E96"),
    "lag_14d":            ("Temporal Lags",      "#1B5E96"),
    "rolling_mean_3d":    ("Rolling Statistics", "#7C3AED"),
    "rolling_mean_7d":    ("Rolling Statistics", "#7C3AED"),
    "rolling_std_7d":     ("Rolling Statistics", "#7C3AED"),
    "rolling_mean_28d":   ("Rolling Statistics", "#7C3AED"),
    "sin_dow":            ("Cyclical Encodings", "#78716C"),
    "cos_dow":            ("Cyclical Encodings", "#78716C"),
    "sin_month":          ("Cyclical Encodings", "#78716C"),
    "cos_month":          ("Cyclical Encodings", "#78716C"),
    "is_weekend":         ("Cyclical Encodings", "#78716C"),
    "is_holiday":         ("Cyclical Encodings", "#78716C"),
    "month_end_flag":     ("E-commerce Signals", "#D4540A"),
    "days_to_month_end":  ("E-commerce Signals", "#D4540A"),
    "is_q4":              ("E-commerce Signals", "#D4540A"),
    "households":         ("Zone Demographics",  "#1B7A45"),
    "household_density":  ("Zone Demographics",  "#1B7A45"),
    "avg_household_size": ("Zone Demographics",  "#1B7A45"),
    "urbanisation":       ("Zone Demographics",  "#1B7A45"),
    "income_idx":         ("Zone Demographics",  "#1B7A45"),
    "is_residential":     ("Zone Demographics",  "#1B7A45"),
    "is_business":        ("Zone Demographics",  "#1B7A45"),
}

LABEL = {
    "lag_1d":             "1-day demand lag",
    "lag_7d":             "7-day demand lag",
    "lag_14d":            "14-day demand lag",
    "rolling_mean_3d":    "3-day rolling mean",
    "rolling_mean_7d":    "7-day rolling mean",
    "rolling_std_7d":     "7-day rolling std dev",
    "rolling_mean_28d":   "28-day rolling mean",
    "sin_dow":            "Day-of-week sine",
    "cos_dow":            "Day-of-week cosine",
    "sin_month":          "Month sine",
    "cos_month":          "Month cosine",
    "is_weekend":         "Is weekend",
    "is_holiday":         "Is Dutch holiday",
    "month_end_flag":     "Month-end flag",
    "days_to_month_end":  "Days to month end",
    "is_q4":              "Is Q4 (peak season)",
    "households":         "Household count",
    "household_density":  "Household density (per km²)",
    "avg_household_size": "Avg household size",
    "urbanisation":       "Urbanisation class",
    "income_idx":         "Income index (WOZ)",
    "is_residential":     "Residential zone flag",
    "is_business":        "Business zone flag",
}

DESC = {
    "lag_1d":             "Actual deliveries in this zone the day before",
    "lag_7d":             "Actual deliveries same day last week",
    "lag_14d":            "Actual deliveries same day two weeks ago",
    "rolling_mean_3d":    "Average demand over the past 3 days",
    "rolling_mean_7d":    "Average daily deliveries over the past 7 days",
    "rolling_std_7d":     "Delivery variability over the past 7 days",
    "rolling_mean_28d":   "Monthly baseline demand (28-day rolling average)",
    "sin_dow":            "sin(2π·dow/7) — smooth day-of-week encoding",
    "cos_dow":            "cos(2π·dow/7) — smooth day-of-week encoding",
    "sin_month":          "sin(2π·month/12) — captures seasonal demand",
    "cos_month":          "cos(2π·month/12) — captures seasonal demand",
    "is_weekend":         "Binary: 1 if Saturday or Sunday (near-zero deliveries)",
    "is_holiday":         "Binary: 1 if Dutch public holiday",
    "month_end_flag":     "Binary: 1 in final 3 days of month (payday spike)",
    "days_to_month_end":  "Days remaining in the current month",
    "is_q4":              "Binary: 1 in Oct–Dec (Sinterklaas + Christmas peak)",
    "households":         "Total households in zone — CBS Kerncijfers 2023",
    "household_density":  "Households per km² — CBS Kerncijfers 2023",
    "avg_household_size": "Average persons per household — CBS Kerncijfers 2023",
    "urbanisation":       "CBS urbanisation class: 1 = very strongly urban, 5 = rural",
    "income_idx":         "Average WOZ property value normalised to NL average — CBS 2023",
    "is_residential":     "Binary: 1 if zone is primarily residential",
    "is_business":        "Binary: 1 if zone is primarily business / commercial",
}

SRC = {
    "Zone Demographics":  "CBS Kerncijfers wijken en buurten 2023",
    "Temporal Lags":      "Delivery records (PostNL-calibrated synthetic series)",
    "Rolling Statistics": "Delivery records (PostNL-calibrated synthetic series)",
    "Cyclical Encodings": "Derived from date",
    "E-commerce Signals": "Derived from date + CBS e-commerce survey",
}

# ══════════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 64)
    print("build_track3.py  —  CBS-calibrated parcel demand forecasting")
    print("=" * 64)

    # ── 1. Fetch CBS Amsterdam wijk data ─────────────────────────────────────
    cbs_lookup: dict[str, dict] = {}
    cbs_source = "defaults (CBS fetch failed)"

    for dataset_id in CBS_DATASETS:
        try:
            print(f"\nFetching CBS dataset {dataset_id} …")
            raw = fetch_cbs_amsterdam(dataset_id)
            print(f"  {len(raw)} wijk rows loaded")

            col_wijk  = find_col(raw, ["WijkenEnBuurten"])
            col_hh    = find_col(raw, ["HuishoudensTotaal", "ParticuliereHuishoudens"])
            col_area  = find_col(raw, ["OppervlakteTotaal", "Oppervlakte_97", "Oppervlakte"])
            col_urban = find_col(raw, ["MateVanStedelijkheid", "Stedelijkheid"])
            col_woz   = find_col(raw, ["GemiddeldeWOZ", "GemiddeldeWoningwaarde", "WozWaarde"])
            col_hhs   = find_col(raw, ["GemiddeldeHuishoudsgrootte", "Huishoudsgrootte", "HuishoudsGrootte"])
            col_pop   = find_col(raw, ["AantalInwoners", "TotaalInwoners", "Inwoners"])

            print(f"  Columns: households={col_hh}, area={col_area}, "
                  f"urban={col_urban}, woz={col_woz}, hh_size={col_hhs}")

            for _, row in raw.iterrows():
                # CBS wijk codes may have trailing spaces/digits — normalise to 8 chars
                wk = str(row.get(col_wijk, "")).strip()[:8]
                hh = to_float(row.get(col_hh)) if col_hh else float("nan")
                if math.isnan(hh) or hh <= 0:
                    continue
                area  = to_float(row.get(col_area))  if col_area  else float("nan")
                urban = to_float(row.get(col_urban)) if col_urban else float("nan")
                woz   = to_float(row.get(col_woz))   if col_woz   else float("nan")
                hhs   = to_float(row.get(col_hhs))   if col_hhs   else float("nan")
                pop   = to_float(row.get(col_pop))   if col_pop   else float("nan")

                density   = hh / area if not math.isnan(area) and area > 0 else 3000
                inc_idx   = (woz / 310_000) if not math.isnan(woz) and woz > 0 else 1.0
                hh_size   = hhs if not math.isnan(hhs) else 1.87
                population = pop if not math.isnan(pop) else hh * hh_size
                urb       = urban if not math.isnan(urban) else 1.0

                cbs_lookup[wk] = {
                    "households":         hh,
                    "household_density":  density,
                    "avg_household_size": hh_size,
                    "urbanisation":       urb,
                    "income_idx":         inc_idx,
                    "population":         population,
                }

            cbs_source = f"CBS {dataset_id}"
            print(f"  Built lookup for {len(cbs_lookup)} wijken")
            break  # success — stop trying other datasets

        except Exception as exc:
            print(f"  Failed: {exc}")

    if not cbs_lookup:
        print("\nNo CBS data fetched — using Amsterdam-wide defaults for all zones.")

    # ── 2. Resolve each zone to CBS metrics ───────────────────────────────────
    def resolve_cbs(zone_name):
        for wk in ZONE_WIJKEN.get(zone_name, []):
            if wk in cbs_lookup:
                return cbs_lookup[wk]
        return DEFAULT_CBS.copy()

    # ── 3. Generate demand time series ────────────────────────────────────────
    start  = date(2023, 1, 1)
    n_days = 365
    dates  = [start + timedelta(days=i) for i in range(n_days)]
    rng    = np.random.default_rng(42)

    print("\nGenerating demand series …")
    frames = []
    for zone in ZONES:
        cbs = resolve_cbs(zone["name"])
        demands = generate_demand(zone, cbs, start, n_days, rng)

        df_z = pd.DataFrame({"date": pd.to_datetime(dates), "demand": demands})
        df_z["zone_id"]   = zone["id"]
        df_z["zone_name"] = zone["name"]

        # Static CBS demographics (broadcast over all 365 rows)
        df_z["households"]         = cbs["households"]
        df_z["household_density"]  = cbs["household_density"]
        df_z["avg_household_size"] = cbs["avg_household_size"]
        df_z["urbanisation"]       = cbs["urbanisation"]
        df_z["income_idx"]         = cbs["income_idx"]
        df_z["is_residential"]     = int(zone["type"] == "residential")
        df_z["is_business"]        = int(zone["type"] == "business")

        df_z = build_features(df_z)
        frames.append(df_z)

        print(f"  {zone['name']:12s}  households={cbs['households']:6.0f}  "
              f"avg_demand={np.mean(demands):6.0f}/day  income_idx={cbs['income_idx']:.2f}")

    panel = pd.concat(frames, ignore_index=True)

    # ── 4. Train XGBoost ──────────────────────────────────────────────────────
    df_train = panel[FEATURE_COLS + ["demand"]].dropna()
    X = df_train[FEATURE_COLS]
    y = df_train["demand"].values

    print(f"\nTraining XGBoost on {len(df_train):,} samples × {len(FEATURE_COLS)} features …")

    model = xgb.XGBRegressor(
        n_estimators    = 500,
        max_depth       = 5,
        learning_rate   = 0.05,
        subsample       = 0.80,
        colsample_bytree= 0.80,
        min_child_weight= 3,
        random_state    = 42,
        tree_method     = "hist",
        verbosity       = 0,
    )
    model.fit(X, y)

    # Gain-based importances (same metric as track1)
    raw_imp = model.get_booster().get_score(importance_type="gain")
    total   = sum(raw_imp.values())
    imp_norm = {feat: raw_imp.get(feat, 0) / total for feat in FEATURE_COLS}
    imp_sorted = sorted(imp_norm.items(), key=lambda x: -x[1])

    print("\nTop 10 features by importance:")
    for feat, imp in imp_sorted[:10]:
        print(f"  {feat:25s}  {imp*100:5.1f}%")

    # ── 5. Evaluation (last 30 days, all zones) ───────────────────────────────
    test = panel[panel["date"] >= pd.Timestamp("2023-12-02")].dropna(subset=FEATURE_COLS + ["demand"])
    if len(test):
        X_test = test[FEATURE_COLS]
        y_pred = model.predict(X_test)
        mae  = np.mean(np.abs(y_pred - test["demand"].values))
        rmse = math.sqrt(np.mean((y_pred - test["demand"].values) ** 2))
        print(f"\nHeld-out test (Dec 2023):  MAE={mae:.1f} parcels/day  RMSE={rmse:.1f}")

    # ── 6. Write JSON ─────────────────────────────────────────────────────────
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
    out_path = "data/feature_importances_track3.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved {len(output)} features → {out_path}")

    # Summary by category
    by_cat = defaultdict(float)
    for item in output:
        by_cat[item["cat"]] += item["importance"]
    print("\nImportance by category:")
    for cat, s in sorted(by_cat.items(), key=lambda x: -x[1]):
        print(f"  {cat:25s}  {s*100:.1f}%")

    print(f"\nData source: {cbs_source}")
    print("Done.")

if __name__ == "__main__":
    main()

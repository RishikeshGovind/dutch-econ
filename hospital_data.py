#!/usr/bin/env python3
"""
hospital_data.py — Synthetic Dutch hospital admissions (2022-2023).

Based on CBS hospital statistics: ~7,500 admissions per 100k per year.
6 wards at a hypothetical Maastricht UMC+ satellite.
Output: data/hospital_admissions.csv
"""
import numpy as np
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

# Ward: base daily admissions, std dev, nurse:patient ratio
WARDS = {
    "ICU":         {"base": 11, "std": 2.5, "ratio": 2.0},
    "Emergency":   {"base": 45, "std": 8.0, "ratio": 5.0},
    "Cardiology":  {"base": 16, "std": 3.0, "ratio": 4.0},
    "Oncology":    {"base": 12, "std": 2.5, "ratio": 4.0},
    "Neurology":   {"base":  9, "std": 2.0, "ratio": 4.0},
    "Orthopedics": {"base": 14, "std": 3.0, "ratio": 5.0},
}

DOW_MULT   = np.array([1.08, 1.05, 1.02, 1.00, 0.95, 0.72, 0.68])  # Mon..Sun
MONTH_MULT = np.array([1.15, 1.12, 1.05, 0.98, 0.92, 0.85,
                        0.82, 0.85, 0.95, 1.02, 1.08, 1.18])


def generate():
    DATA_DIR.mkdir(exist_ok=True)
    rng   = np.random.default_rng(42)
    dates = pd.date_range("2022-01-01", "2023-12-31", freq="D")
    rows  = []

    for d in dates:
        seasonal = DOW_MULT[d.dayofweek] * MONTH_MULT[d.month - 1]
        for ward, s in WARDS.items():
            base = s["base"] * seasonal
            # Emergency: occasional surge events (flu, accidents)
            surge = rng.choice([0, 12, 25], p=[0.93, 0.05, 0.02]) if ward == "Emergency" else 0
            rows.append({
                "date":       d.date(),
                "ward":       ward,
                "admissions": max(1, int(rng.normal(base + surge, s["std"]))),
            })

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])

    # Lag / rolling features per ward
    parts = []
    for _, g in df.groupby("ward"):
        g = g.sort_values("date").copy()
        a = g["admissions"]
        g["lag_7d"]      = a.shift(7)
        g["lag_14d"]     = a.shift(14)
        g["rolling_7d"]  = a.shift(1).rolling(7).mean()
        g["dow"]         = g["date"].dt.dayofweek
        g["month"]       = g["date"].dt.month
        parts.append(g)

    out = pd.concat(parts).dropna().reset_index(drop=True)
    out.to_csv(DATA_DIR / "hospital_admissions.csv", index=False)
    print(f"Saved {len(out)} rows → data/hospital_admissions.csv")
    print(out.groupby("ward")["admissions"].agg(["mean","std"]).round(1))


if __name__ == "__main__":
    generate()

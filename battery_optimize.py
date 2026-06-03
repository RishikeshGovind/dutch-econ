#!/usr/bin/env python3
"""
battery_optimize.py — LP battery dispatch optimizer for the Predict-Then-Optimize demo.

Battery spec:  1 MW max charge/discharge, 2 MWh capacity, 90% round-trip efficiency.
Initial SOC:   50% (1 MWh).

Two modes compared:
  Oracle  — LP solved with TRUE prices   (upper bound, perfect foresight)
  Naive   — LP solved with XGBoost FORECASTS, revenue evaluated at true prices

For each 24-hour window in the 60-day test period the LP is:

  Minimise  Σ_t [ price_t · charge_t  −  price_t · discharge_t ]
  s.t.      soc[t+1] = soc[t] + η · charge[t] − discharge[t]   (SOC dynamics)
            soc[0]   = soc_init                                   (initial state)
            0 ≤ charge[t]    ≤ 1  MW
            0 ≤ discharge[t] ≤ 1  MW
            0 ≤ soc[t]       ≤ 2  MWh

Variables: [charge_0..23, discharge_0..23, soc_0..23]  (72 total per day)

Output:  data/battery_results.csv
"""
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linprog

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
PREDS_CSV = DATA_DIR / "price_predictions.csv"
RESULTS_CSV = DATA_DIR / "battery_results.csv"
SENSITIVITY_CSV = DATA_DIR / "decision_sensitivity.csv"

SENSITIVITY_DELTA = 10.0   # EUR/MWh perturbation for sensitivity sweep

# Battery parameters
MAX_MW = 1.0        # charge / discharge limit
CAP_MWH = 2.0       # usable capacity
ETA = 0.90          # round-trip efficiency applied to charging
SOC_INIT = CAP_MWH * 0.50  # 1.0 MWh


def solve_day(prices: np.ndarray, soc_init: float) -> dict:
    """
    Solve one 24-hour LP dispatch.

    Variable layout (n=72):
      indices  0..23  → charge_t
      indices 24..47  → discharge_t
      indices 48..71  → soc_t  (SOC at START of hour t)

    Returns dict with arrays charge, discharge, soc and final_soc scalar.
    """
    T = len(prices)
    assert T == 24, "Expected 24-hour price array"

    # Objective: minimise Σ price_t*(charge_t - discharge_t)
    c = np.concatenate([prices, -prices, np.zeros(T)])

    # Equality constraints (24 total)
    #  t = 0..22:  -soc[t] + soc[t+1] - η*charge[t] + discharge[t] = 0
    #  t = 23:     soc[0] = soc_init
    n_eq = T  # 23 dynamics + 1 initial
    A_eq = np.zeros((n_eq, 3 * T))
    b_eq = np.zeros(n_eq)

    for t in range(T - 1):
        row = t
        A_eq[row, 2 * T + t] = -1.0           # -soc[t]
        A_eq[row, 2 * T + t + 1] = 1.0        # +soc[t+1]
        A_eq[row, t] = -ETA                    # -η·charge[t]
        A_eq[row, T + t] = 1.0                 # +discharge[t]

    # Initial SOC
    A_eq[T - 1, 2 * T] = 1.0
    b_eq[T - 1] = soc_init

    bounds = (
        [(0.0, MAX_MW)] * T        # charge
        + [(0.0, MAX_MW)] * T      # discharge
        + [(0.0, CAP_MWH)] * T    # soc
    )

    res = linprog(c, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")

    if not res.success:
        log.debug("LP failed (status %d): %s", res.status, res.message)
        return {
            "charge": np.zeros(T),
            "discharge": np.zeros(T),
            "soc": np.full(T, soc_init),
            "final_soc": soc_init,
        }

    x = res.x
    charge = np.clip(x[:T], 0.0, MAX_MW)
    discharge = np.clip(x[T : 2 * T], 0.0, MAX_MW)
    soc = np.clip(x[2 * T :], 0.0, CAP_MWH)

    # Final SOC after the last hour's action
    final_soc = float(np.clip(soc[-1] + ETA * charge[-1] - discharge[-1], 0.0, CAP_MWH))

    return {"charge": charge, "discharge": discharge, "soc": soc, "final_soc": final_soc}


def run_pipeline(df: pd.DataFrame) -> pd.DataFrame:
    """Iterate over test-period days, solve oracle and naive LPs."""
    df = df.copy()
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True)
    df["date"] = df["datetime_utc"].dt.date
    df["hour"] = df["datetime_utc"].dt.hour
    df = df.sort_values(["date", "hour"]).reset_index(drop=True)

    days = sorted(df["date"].unique())
    rows = []

    soc_oracle = SOC_INIT
    soc_naive = SOC_INIT

    for day in days:
        day_df = df[df["date"] == day].sort_values("hour")
        if len(day_df) < 24:
            log.debug("Skipping %s: only %d hours", day, len(day_df))
            continue

        actual = day_df["actual"].values[:24]
        forecast = day_df["forecast"].values[:24]

        oracle = solve_day(actual, soc_oracle)
        naive = solve_day(forecast, soc_naive)

        for h in range(24):
            rows.append(
                {
                    "date": day,
                    "hour": h,
                    "datetime_utc": day_df["datetime_utc"].iloc[h],
                    "price_actual": actual[h],
                    "price_forecast": forecast[h],
                    "charge_oracle_mw": oracle["charge"][h],
                    "discharge_oracle_mw": oracle["discharge"][h],
                    "soc_oracle_mwh": oracle["soc"][h],
                    "charge_naive_mw": naive["charge"][h],
                    "discharge_naive_mw": naive["discharge"][h],
                    "soc_naive_mwh": naive["soc"][h],
                }
            )

        soc_oracle = oracle["final_soc"]
        soc_naive = naive["final_soc"]

    results = pd.DataFrame(rows)

    # Compute daily aggregates and join back (needed by demo_chart.py)
    oracle_rev = {}
    naive_rev = {}
    day_mae = {}
    for day, g in results.groupby("date"):
        oracle_rev[day] = float(
            np.sum(g["price_actual"] * (g["discharge_oracle_mw"] - g["charge_oracle_mw"]))
        )
        naive_rev[day] = float(
            np.sum(g["price_actual"] * (g["discharge_naive_mw"] - g["charge_naive_mw"]))
        )
        day_mae[day] = float(np.mean(np.abs(g["price_forecast"] - g["price_actual"])))

    results["oracle_revenue"] = results["date"].map(oracle_rev)
    results["naive_revenue"] = results["date"].map(naive_rev)
    results["mae"] = results["date"].map(day_mae)

    return results


def compute_sensitivity(results: pd.DataFrame) -> pd.DataFrame:
    """
    Decision-level explainability: for each test hour, perturb the XGBoost
    forecast by ±SENSITIVITY_DELTA EUR/MWh and measure whether the naive
    dispatch decision changes (flip) and by how much revenue shifts.

    This is the LP counterpart of SHAP: not "which feature moved the prediction"
    but "which prediction error moved the dispatch decision."

    Columns returned:
      date, hour, actual_price, forecast_price,
      flipped_up, flipped_dn, sensitivity_score (0/1),
      revenue_impact_up, revenue_impact_dn, max_revenue_impact
    """
    results = results.copy()
    results["datetime_utc"] = pd.to_datetime(results["datetime_utc"])
    results["hour"] = results["hour"].astype(int)

    rows = []
    n_sensitive = 0

    for date, day in results.groupby("date"):
        day = day.sort_values("hour")
        if len(day) < 24:
            continue

        actual = day["price_actual"].values[:24]
        forecast = day["price_forecast"].values[:24]
        base_charge = day["charge_naive_mw"].values[:24]
        base_discharge = day["discharge_naive_mw"].values[:24]
        base_rev = float(np.sum(actual * (base_discharge - base_charge)))

        # Starting SOC for this day (SOC at the start of hour 0 under naive dispatch)
        soc_init = float(day["soc_naive_mwh"].iloc[0])

        for h in range(24):
            fup = forecast.copy()
            fup[h] += SENSITIVITY_DELTA
            res_up = solve_day(fup, soc_init)

            fdn = forecast.copy()
            fdn[h] -= SENSITIVITY_DELTA
            res_dn = solve_day(fdn, soc_init)

            # Flip = decision at hour h changes by more than numerical noise
            flip_up = bool(
                abs(res_up["charge"][h] - base_charge[h]) > 0.1
                or abs(res_up["discharge"][h] - base_discharge[h]) > 0.1
            )
            flip_dn = bool(
                abs(res_dn["charge"][h] - base_charge[h]) > 0.1
                or abs(res_dn["discharge"][h] - base_discharge[h]) > 0.1
            )
            sensitive = int(flip_up or flip_dn)
            n_sensitive += sensitive

            rev_up = float(np.sum(actual * (res_up["discharge"] - res_up["charge"])))
            rev_dn = float(np.sum(actual * (res_dn["discharge"] - res_dn["charge"])))

            rows.append(
                {
                    "date": date,
                    "hour": h,
                    "actual_price": actual[h],
                    "forecast_price": forecast[h],
                    "flipped_up": flip_up,
                    "flipped_dn": flip_dn,
                    "sensitivity_score": sensitive,
                    "revenue_impact_up": rev_up - base_rev,
                    "revenue_impact_dn": rev_dn - base_rev,
                    "max_revenue_impact": max(abs(rev_up - base_rev), abs(rev_dn - base_rev)),
                }
            )

    total = len(rows)
    log.info(
        "Sensitivity: %d/%d hours (%.1f%%) flip decision under ±%.0f €/MWh perturbation",
        n_sensitive, total, 100 * n_sensitive / total, SENSITIVITY_DELTA,
    )
    return pd.DataFrame(rows)


def main():
    if not PREDS_CSV.exists():
        log.info("Predictions not found — running price_forecast.py...")
        import price_forecast
        price_forecast.main()

    df = pd.read_csv(PREDS_CSV)
    log.info("Loaded %d rows from %s", len(df), PREDS_CSV)

    results = run_pipeline(df)
    results.to_csv(RESULTS_CSV, index=False)
    log.info("Battery results saved → %s", RESULTS_CSV)

    # Decision sensitivity analysis
    log.info("Running decision sensitivity analysis (%d test hours × 2 perturbations)...",
             len(results))
    sensitivity = compute_sensitivity(results)
    sensitivity.to_csv(SENSITIVITY_CSV, index=False)
    log.info("Sensitivity saved → %s", SENSITIVITY_CSV)

    sens_rate = sensitivity["sensitivity_score"].mean() * 100
    high_impact = sensitivity.nlargest(5, "max_revenue_impact")[
        ["date", "hour", "forecast_price", "actual_price", "max_revenue_impact"]
    ]
    print(f"\n=== Decision Sensitivity (±{SENSITIVITY_DELTA:.0f} €/MWh perturbation) ===")
    print(f"  {sens_rate:.1f}% of test hours flip charge/discharge under a {SENSITIVITY_DELTA:.0f} €/MWh forecast shift")
    print("\n  Top 5 highest-impact hours:")
    print(high_impact.to_string(index=False))

    # Summary statistics
    daily = (
        results.groupby("date")[["oracle_revenue", "naive_revenue"]]
        .first()
        .reset_index()
    )
    oracle_total = daily["oracle_revenue"].sum()
    naive_total = daily["naive_revenue"].sum()
    gap = oracle_total - naive_total
    gap_pct = gap / oracle_total * 100 if oracle_total != 0 else float("nan")

    print("\n=== Battery Dispatch Results — 60-day Test Period ===")
    print(f"  Oracle (perfect foresight):       €{oracle_total:>9,.0f}")
    print(f"  Naive predict-then-optimize:      €{naive_total:>9,.0f}")
    print(f"  Decision quality gap:             €{gap:>9,.0f}  ({gap_pct:.1f}%)")
    print()
    print(
        f"  A {gap_pct:.0f}% revenue gap from forecast error motivates decision-focused"
        " learning (SPO+):\n"
        "  training the forecaster to minimise decision regret, not prediction MSE."
    )


if __name__ == "__main__":
    main()

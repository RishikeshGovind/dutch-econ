#!/usr/bin/env python3
"""
demo_chart.py — Publication-quality figures for the Predict-Then-Optimize demo.

Requires: data/price_predictions.csv, data/battery_results.csv
Output:   data/figures/price_forecast.png
          data/figures/battery_dispatch.png
          data/figures/value_of_better_forecast.png
"""
import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive backend

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
FIGURES_DIR = DATA_DIR / "figures"
PREDS_CSV = DATA_DIR / "price_predictions.csv"
RESULTS_CSV = DATA_DIR / "battery_results.csv"
SENSITIVITY_CSV = DATA_DIR / "decision_sensitivity.csv"
SPO_COMP_CSV = DATA_DIR / "spo_comparison.csv"
SHAP_CSV = DATA_DIR / "shap_values.csv"

# Color palette (colorblind-friendly)
BLUE = "#1D4ED8"
ORANGE = "#D97706"
GREEN = "#15803D"
RED = "#B91C1C"
GRAY = "#6B7280"
LIGHT_BLUE = "#BFDBFE"
LIGHT_ORANGE = "#FDE68A"

_RC = {
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.35,
    "grid.linestyle": "--",
    "font.family": "sans-serif",
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "axes.labelsize": 10,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "figure.dpi": 150,
    "savefig.dpi": 150,
}


# ---------------------------------------------------------------------------
# Figure 1: 2-week price forecast sample
# ---------------------------------------------------------------------------

def fig1_price_forecast(preds: pd.DataFrame, out_path: Path) -> None:
    sample = preds.sort_values("datetime_utc").head(24 * 14)
    mae = float(np.mean(np.abs(sample["actual"] - sample["forecast"])))
    rmse = float(np.sqrt(np.mean((sample["actual"] - sample["forecast"]) ** 2)))

    fig, ax = plt.subplots(figsize=(13, 4.5))

    ax.plot(sample["datetime_utc"], sample["actual"],
            color=BLUE, lw=1.6, label="Actual price", zorder=4)
    ax.plot(sample["datetime_utc"], sample["forecast"],
            color=ORANGE, lw=1.4, ls="--", label="XGBoost forecast", zorder=3)
    ax.fill_between(
        sample["datetime_utc"], sample["actual"], sample["forecast"],
        color=ORANGE, alpha=0.18, label=f"Error  (MAE = {mae:.1f} €/MWh)", zorder=2,
    )
    ax.axhline(0, color=GRAY, lw=0.6, ls=":")

    ax.set_ylabel("Day-Ahead Price (€/MWh)")
    ax.set_title("Netherlands Day-Ahead Electricity Price Forecast — 2-Week Sample")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")

    ax.text(
        0.99, 0.97,
        f"MAE  = {mae:.1f} €/MWh\nRMSE = {rmse:.1f} €/MWh",
        transform=ax.transAxes, ha="right", va="top", fontsize=8.5,
        bbox=dict(boxstyle="round,pad=0.4", fc="white", ec=GRAY, alpha=0.85),
    )
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    log.info("Saved %s", out_path)


# ---------------------------------------------------------------------------
# Figure 2: 72-hour battery dispatch (oracle)
# ---------------------------------------------------------------------------

def fig2_battery_dispatch(results: pd.DataFrame, out_path: Path) -> None:
    sample = results.sort_values("datetime_utc").head(72).copy()
    dt = sample["datetime_utc"]

    fig, ax1 = plt.subplots(figsize=(14, 5.5))
    ax2 = ax1.twinx()

    # Left axis — prices
    ax1.plot(dt, sample["price_actual"], color=GRAY, lw=1.6, label="Actual price", zorder=5)
    ax1.plot(dt, sample["price_forecast"], color=GRAY, lw=1.0, ls=":", alpha=0.65,
             label="Forecast price", zorder=4)
    ax1.axhline(0, color=GRAY, lw=0.5, ls=":")
    ax1.set_ylabel("Price (€/MWh)", color=GRAY)
    ax1.tick_params(axis="y", labelcolor=GRAY)
    ax1.set_zorder(3)
    ax1.patch.set_visible(False)

    # Right axis — SOC and power flows
    ax2.fill_between(dt, sample["soc_oracle_mwh"], alpha=0.35,
                     color=BLUE, label="SOC (MWh)")
    ax2.fill_between(dt, sample["charge_oracle_mw"], alpha=0.55,
                     color=GREEN, label="Charge (MW)")
    ax2.fill_between(dt, -sample["discharge_oracle_mw"], alpha=0.55,
                     color=RED, label="Discharge (MW, negative)")
    ax2.set_ylabel("Power (MW) / State of Charge (MWh)", color=BLUE)
    ax2.tick_params(axis="y", labelcolor=BLUE)
    ax2.set_ylim(-1.6, 2.8)
    ax2.axhline(0, color=BLUE, lw=0.4, ls=":")

    ax1.set_title("Oracle Battery Dispatch — 72-Hour Sample (Charge Low, Discharge High)")
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%d %b %Hh"))
    ax1.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 6, 12, 18]))
    plt.setp(ax1.get_xticklabels(), rotation=30, ha="right")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right", ncol=3)

    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    log.info("Saved %s", out_path)


# ---------------------------------------------------------------------------
# Figure 3: Forecast MAE vs. dispatch revenue (the core thesis figure)
# ---------------------------------------------------------------------------

def fig3_value_of_forecast(results: pd.DataFrame, out_path: Path) -> None:
    # One row per test day
    daily = results.groupby("date").first().reset_index()
    x = daily["mae"].values
    y = daily["naive_revenue"].values

    # OLS trend line
    slope, intercept, r_val, p_val, _ = stats.linregress(x, y)
    x_line = np.linspace(x.min(), x.max(), 200)
    y_line = slope * x_line + intercept

    oracle_mean = daily["oracle_revenue"].mean()
    naive_mean = daily["naive_revenue"].mean()

    fig, ax = plt.subplots(figsize=(8, 6))

    # Scatter: color-code by whether day beats oracle mean
    above = y >= oracle_mean * 0.9
    ax.scatter(x[above], y[above], color=GREEN, alpha=0.75, s=55, zorder=4,
               label="High-revenue days (≥90% oracle)")
    ax.scatter(x[~above], y[~above], color=RED, alpha=0.65, s=55, zorder=4,
               label="Low-revenue days")

    ax.plot(x_line, y_line, color=ORANGE, lw=2.2, zorder=5,
            label=f"OLS: slope={slope:.1f}  r={r_val:.2f}  p={p_val:.3f}")

    # Oracle and naive mean reference lines
    ax.axhline(oracle_mean, color=BLUE, lw=1.8, ls="--",
               label=f"Oracle avg (€{oracle_mean:.0f}/day)")
    ax.axhline(naive_mean, color=GRAY, lw=1.2, ls=":",
               label=f"Naive avg (€{naive_mean:.0f}/day)")

    ax.set_xlabel("Forecast MAE that day (€/MWh)", labelpad=6)
    ax.set_ylabel("Realized battery revenue that day (€)", labelpad=6)
    ax.set_title(
        "Value of Better Forecasts\n"
        "Lower MAE → Higher Dispatch Revenue (Empirical Motivation for SPO+)"
    )
    ax.legend(loc="upper right", framealpha=0.9)

    # Stat annotation box
    sign = "−" if slope < 0 else "+"
    ax.text(
        0.03, 0.04,
        (
            f"Pearson r  = {r_val:.3f}\n"
            f"p-value    = {p_val:.3f}\n"
            f"Slope      = {sign}€{abs(slope):.1f} per €/MWh MAE\n"
            f"Gap oracle = €{oracle_mean - naive_mean:.0f}/day"
        ),
        transform=ax.transAxes, ha="left", va="bottom", fontsize=8.5,
        bbox=dict(boxstyle="round,pad=0.45", fc="white", ec=GRAY, alpha=0.88),
    )

    # Shade "high-error" region
    x_thresh = np.percentile(x, 75)
    ax.axvspan(x_thresh, x.max(), color=RED, alpha=0.05, label="_nolegend_")
    ax.text(x_thresh + 0.2, ax.get_ylim()[0] * 0.98, "High MAE region",
            color=RED, fontsize=7.5, va="bottom")

    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    log.info("Saved %s", out_path)


# ---------------------------------------------------------------------------
# Figure 4: SPO+ vs standard forecast — decision quality comparison
# ---------------------------------------------------------------------------

def fig4_spo_comparison(comp: pd.DataFrame, out_path: Path) -> None:
    """
    Grouped bar chart: forecast MAE (lower is better) vs dispatch revenue
    (higher is better) for Oracle, Standard XGBoost, Regret-weighted, SPO+.

    The key message: SPO+ may NOT have the best MAE, but it earns the most
    revenue — demonstrating that MSE is the wrong training objective.
    """
    models = comp["model"].tolist()
    maes = comp["mae"].tolist()
    revenues = comp["revenue"].tolist()
    oracle_rev = comp.loc[comp["model"] == "Oracle", "revenue"].values[0]

    # Colors: oracle = neutral, others = distinct
    colors = [GRAY, BLUE, ORANGE, GREEN]

    fig, (ax_mae, ax_rev) = plt.subplots(1, 2, figsize=(13, 5.5))

    # ── Left: MAE ────────────────────────────────────────────────────────────
    x = np.arange(len(models))
    bars_mae = ax_mae.bar(x, maes, color=colors, alpha=0.82, width=0.55, zorder=3)
    ax_mae.bar_label(bars_mae, fmt="%.1f", padding=3, fontsize=8.5)
    ax_mae.set_xticks(x)
    ax_mae.set_xticklabels(models, rotation=15, ha="right")
    ax_mae.set_ylabel("Forecast MAE (€/MWh)")
    ax_mae.set_title("Forecast Accuracy\n(lower is better)")
    ax_mae.set_ylim(0, max(m for m in maes if m > 0) * 1.30)
    # Annotate "Oracle has no forecast error"
    ax_mae.text(0, maes[0] + 0.3, "perfect\nforesight", ha="center",
                fontsize=7, color=GRAY, style="italic")

    # ── Right: Revenue ───────────────────────────────────────────────────────
    bars_rev = ax_rev.bar(x, revenues, color=colors, alpha=0.82, width=0.55, zorder=3)
    ax_rev.bar_label(bars_rev,
                     labels=[f"€{r:,.0f}" for r in revenues],
                     padding=3, fontsize=8.5)
    ax_rev.axhline(oracle_rev, color=GRAY, lw=1.2, ls="--", alpha=0.6, label="Oracle")
    ax_rev.set_xticks(x)
    ax_rev.set_xticklabels(models, rotation=15, ha="right")
    ax_rev.set_ylabel("60-day dispatch revenue (€)")
    ax_rev.set_title("Decision Quality — Dispatch Revenue\n(higher is better)")
    ax_rev.set_ylim(min(0, min(revenues)) * 1.1,
                    oracle_rev * 1.22)

    # Annotate % of oracle gap recovered by SPO+
    spo_rev = comp.loc[comp["model"] == "SPO+ gradient", "revenue"].values
    mse_rev = comp.loc[comp["model"] == "Standard XGBoost", "revenue"].values
    if len(spo_rev) and len(mse_rev):
        gap_recovered = (spo_rev[0] - mse_rev[0]) / max(oracle_rev - mse_rev[0], 1) * 100
        ax_rev.annotate(
            f"SPO+ recovers\n{gap_recovered:.0f}% of oracle gap",
            xy=(x[-1], spo_rev[0]),
            xytext=(x[-1] - 0.4, spo_rev[0] + (oracle_rev - spo_rev[0]) * 0.5),
            fontsize=8, color=GREEN,
            arrowprops=dict(arrowstyle="->", color=GREEN, lw=1.2),
        )

    fig.suptitle(
        "SPO+ vs Standard Forecast: MAE vs Dispatch Revenue\n"
        "Decision-focused learning trades forecast accuracy for decision quality",
        fontweight="bold", fontsize=11,
    )
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    log.info("Saved %s", out_path)


# ---------------------------------------------------------------------------
# Figure 5: Decision sensitivity heatmap + SHAP at critical hours
# ---------------------------------------------------------------------------

def fig5_decision_sensitivity(
    sensitivity: pd.DataFrame,
    shap_df: pd.DataFrame | None,
    out_path: Path,
) -> None:
    """
    Left panel:  Heatmap of decision sensitivity rate by hour-of-day × day-of-week.
                 Shows WHEN forecast errors matter most for dispatch decisions.

    Right panel: If SHAP values are available, compare mean |SHAP| for high-sensitivity
                 vs low-sensitivity hours — showing WHICH features drive decisions at
                 critical moments (prediction explainability meets decision explainability).
    """
    sensitivity = sensitivity.copy()
    sensitivity["day_of_week"] = pd.to_datetime(sensitivity["date"]).dt.dayofweek

    # ── Pivot to 7×24 heatmap ────────────────────────────────────────────────
    pivot = (
        sensitivity.pivot_table(
            values="sensitivity_score",
            index="day_of_week",
            columns="hour",
            aggfunc="mean",
        )
    )
    dow_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    n_panels = 2 if (shap_df is not None and not shap_df.empty) else 1
    fig, axes = plt.subplots(1, n_panels, figsize=(13 if n_panels == 2 else 8, 5.5))
    if n_panels == 1:
        axes = [axes]

    ax_heat = axes[0]
    im = ax_heat.imshow(
        pivot.values,
        cmap="YlOrRd",
        aspect="auto",
        vmin=0,
        vmax=pivot.values.max(),
    )
    plt.colorbar(im, ax=ax_heat, label="Decision flip rate", fraction=0.03, pad=0.02)
    ax_heat.set_yticks(range(len(dow_labels)))
    ax_heat.set_yticklabels(dow_labels)
    ax_heat.set_xlabel("Hour of day")
    ax_heat.set_title(
        f"Decision Sensitivity Heatmap\n"
        f"P(dispatch flips | forecast shift ±10 €/MWh)"
    )

    # Overlay bar chart of hourly sensitivity rate along x-axis
    ax_bar = ax_heat.twinx()
    hourly_sens = sensitivity.groupby("hour")["sensitivity_score"].mean()
    ax_bar.fill_between(
        hourly_sens.index, hourly_sens.values, alpha=0.2, color=BLUE, step="mid",
    )
    ax_bar.set_ylabel("Mean sensitivity rate", color=BLUE)
    ax_bar.tick_params(axis="y", labelcolor=BLUE)
    ax_bar.set_ylim(0, 1.0)

    # ── Right panel: SHAP at high vs low sensitivity hours ───────────────────
    if n_panels == 2:
        ax_shap = axes[1]
        shap_df = shap_df.copy()
        shap_df["datetime_utc"] = pd.to_datetime(shap_df["datetime_utc"], utc=True)

        # Align sensitivity scores with SHAP rows by datetime
        sens_dt = sensitivity.copy()
        sens_dt["datetime_utc"] = pd.to_datetime(
            sens_dt["date"].astype(str) + " " + sens_dt["hour"].astype(str) + ":00:00",
            utc=True,
        )
        merged = shap_df.merge(
            sens_dt[["datetime_utc", "sensitivity_score"]],
            on="datetime_utc",
            how="inner",
        )

        feat_cols = [c for c in shap_df.columns if c != "datetime_utc"]
        if len(merged) > 0:
            high = merged[merged["sensitivity_score"] == 1][feat_cols]
            low = merged[merged["sensitivity_score"] == 0][feat_cols]

            shap_high = high.abs().mean() if len(high) else pd.Series(0, index=feat_cols)
            shap_low = low.abs().mean() if len(low) else pd.Series(0, index=feat_cols)

            y_pos = np.arange(len(feat_cols))
            ax_shap.barh(y_pos + 0.2, shap_high.values, height=0.38,
                         color=RED, alpha=0.75, label="High-sensitivity hours")
            ax_shap.barh(y_pos - 0.2, shap_low.values, height=0.38,
                         color=BLUE, alpha=0.65, label="Low-sensitivity hours")
            ax_shap.set_yticks(y_pos)
            ax_shap.set_yticklabels(feat_cols)
            ax_shap.set_xlabel("Mean |SHAP value| (€/MWh)")
            ax_shap.set_title(
                "Feature Importance at Decision-Critical Hours\n"
                "SHAP attribution: high-sensitivity vs stable hours"
            )
            ax_shap.legend()
            ax_shap.text(
                0.97, 0.03,
                "High-sensitivity: hours where a\n10 €/MWh error flips dispatch",
                transform=ax_shap.transAxes, ha="right", va="bottom",
                fontsize=7.5,
                bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=GRAY, alpha=0.85),
            )

    fig.suptitle(
        "Decision-Level Explainability: When and Why Forecast Errors Matter",
        fontweight="bold", fontsize=11,
    )
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    log.info("Saved %s", out_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    missing = [p for p in [PREDS_CSV, RESULTS_CSV] if not p.exists()]
    if missing:
        log.error("Missing input files: %s", missing)
        log.error("Run:  python price_forecast.py && python battery_optimize.py")
        raise SystemExit(1)

    preds = pd.read_csv(PREDS_CSV, parse_dates=["datetime_utc"])
    results = pd.read_csv(RESULTS_CSV)
    results["datetime_utc"] = pd.to_datetime(results["datetime_utc"])

    # Optional datasets (populated by spo_train.py and battery_optimize.py)
    comp_df = pd.read_csv(SPO_COMP_CSV) if SPO_COMP_CSV.exists() else None
    sensitivity_df = pd.read_csv(SENSITIVITY_CSV) if SENSITIVITY_CSV.exists() else None
    shap_df = pd.read_csv(SHAP_CSV) if SHAP_CSV.exists() else None

    with plt.rc_context(_RC):
        fig1_price_forecast(preds, FIGURES_DIR / "price_forecast.png")
        fig2_battery_dispatch(results, FIGURES_DIR / "battery_dispatch.png")
        fig3_value_of_forecast(results, FIGURES_DIR / "value_of_better_forecast.png")

        if comp_df is not None:
            fig4_spo_comparison(comp_df, FIGURES_DIR / "spo_comparison.png")
        else:
            log.info("Skipping fig4 — run spo_train.py first to generate spo_comparison.csv")

        if sensitivity_df is not None:
            fig5_decision_sensitivity(
                sensitivity_df, shap_df, FIGURES_DIR / "decision_sensitivity.png"
            )
        else:
            log.info("Skipping fig5 — run battery_optimize.py first to generate decision_sensitivity.csv")

    n_figs = 3 + (comp_df is not None) + (sensitivity_df is not None)
    log.info("%d figures saved to %s/", n_figs, FIGURES_DIR)


if __name__ == "__main__":
    main()

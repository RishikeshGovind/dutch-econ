#!/usr/bin/env python3
"""
build_track1.py — Generates track1.html, a self-contained visual essay on
the Track 1 Predict-Then-Optimize battery dispatch pipeline.

Inspired by FlowingData / The Pudding. Includes a live D3 force-simulation
of energy particles flowing between grid → battery → market.

Run:  python build_track1.py
Open: open track1.html  (no server needed — data is embedded)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

DATA_DIR = Path(__file__).parent / "data"
OUT_HTML = Path(__file__).parent / "track1.html"

# ── Data processing ───────────────────────────────────────────────────────────

def check_files():
    needed = ["price_predictions.csv", "battery_results.csv",
              "decision_sensitivity.csv", "spo_comparison.csv"]
    missing = [f for f in needed if not (DATA_DIR / f).exists()]
    if missing:
        print(f"Missing: {missing}\nRun: python price_forecast.py && "
              "python battery_optimize.py && python spo_train.py")
        sys.exit(1)


def heatmap_data(preds):
    preds = preds.copy()
    preds["datetime_utc"] = pd.to_datetime(preds["datetime_utc"], utc=True)
    preds["date"] = preds["datetime_utc"].dt.strftime("%Y-%m-%d")
    preds["hour"] = preds["datetime_utc"].dt.hour
    return [{"date": r["date"], "hour": int(r["hour"]), "price": round(float(r["actual"]), 1)}
            for _, r in preds.head(14 * 24).iterrows()]


def dispatch_data(results):
    results = results.copy()
    results["datetime_utc"] = pd.to_datetime(results["datetime_utc"])
    return [{"dt": r["datetime_utc"].strftime("%Y-%m-%dT%H:00"),
             "price": round(float(r["price_actual"]), 1),
             "charge": round(float(r["charge_oracle_mw"]), 3),
             "discharge": round(float(r["discharge_oracle_mw"]), 3),
             "soc": round(float(r["soc_oracle_mwh"]), 3)}
            for _, r in results.head(72).iterrows()]


def revenue_data(results):
    out, cum_o, cum_n = [], 0.0, 0.0
    for i, (day, g) in enumerate(results.groupby("date")):
        o = float(np.sum(g["price_actual"] * (g["discharge_oracle_mw"] - g["charge_oracle_mw"])))
        n = float(np.sum(g["price_actual"] * (g["discharge_naive_mw"] - g["charge_naive_mw"])))
        cum_o += o; cum_n += n
        out.append({"day": i+1, "date": str(day),
                    "oracle": round(cum_o, 0), "naive": round(cum_n, 0)})
    return out


def clock_data(sensitivity):
    h = sensitivity.groupby("hour").agg(
        sensitivity=("sensitivity_score", "mean"),
        impact=("max_revenue_impact", "mean")).reset_index()
    return [{"hour": int(r["hour"]), "sensitivity": round(float(r["sensitivity"]), 3),
             "impact": round(float(r["impact"]), 1)} for _, r in h.iterrows()]


def scatter_data(results):
    out = []
    for day, g in results.groupby("date"):
        rev = float(np.sum(g["price_actual"] * (g["discharge_naive_mw"] - g["charge_naive_mw"])))
        mae = float(np.mean(np.abs(g["price_forecast"] - g["price_actual"])))
        out.append({"date": str(day), "mae": round(mae, 1), "revenue": round(rev, 0)})
    return out


def data_source_meta() -> dict:
    """Return metadata about where the data came from."""
    panel = DATA_DIR / "nl_panel.parquet"
    if panel.exists():
        df = pd.read_parquet(panel, columns=["price_da"])
        idx = pd.to_datetime(df.index, utc=True)
        return {
            "source": "ENTSO-E Transparency Platform",
            "live": True,
            "start": idx.min().strftime("%d %b %Y"),
            "end":   idx.max().strftime("%d %b %Y"),
            "rows":  len(df),
        }
    return {"source": "Synthetic (ENTSO-E calibrated)", "live": False,
            "start": "Jan 2022", "end": "Dec 2023", "rows": 0}


FEATURE_META = {
    # Temporal
    "sin_hour":   ("Temporal",        "Hour of day (sin)",       "ENTSO-E A44", "Cyclical sine encoding of hour — captures intraday price shape"),
    "cos_hour":   ("Temporal",        "Hour of day (cos)",       "ENTSO-E A44", "Cosine pair for hour — together with sin gives smooth 24h cycle"),
    "sin_dow":    ("Temporal",        "Day of week (sin)",       "ENTSO-E A44", "Cyclical encoding of weekday — captures Mon–Fri vs weekend pricing"),
    "cos_dow":    ("Temporal",        "Day of week (cos)",       "ENTSO-E A44", "Cosine pair for day-of-week"),
    "sin_month":  ("Temporal",        "Month (sin)",             "ENTSO-E A44", "Cyclical month encoding — captures winter heating vs summer surplus"),
    "cos_month":  ("Temporal",        "Month (cos)",             "ENTSO-E A44", "Cosine pair for month"),
    "is_weekend": ("Temporal",        "Weekend flag",            "ENTSO-E A44", "Binary 1/0 — lower industrial demand on Sat–Sun depresses prices"),
    # Price history
    "lag_1h":          ("Price History", "Price lag 1 h",        "ENTSO-E A44", "Day-ahead price one hour ago (€/MWh) — strongest autocorrelation signal"),
    "lag_2h":          ("Price History", "Price lag 2 h",        "ENTSO-E A44", "Day-ahead price two hours ago (€/MWh)"),
    "lag_24h":         ("Price History", "Price lag 24 h",       "ENTSO-E A44", "Same hour yesterday — used as the naive persistence baseline"),
    "lag_48h":         ("Price History", "Price lag 48 h",       "ENTSO-E A44", "Same hour two days ago (€/MWh)"),
    "lag_168h":        ("Price History", "Price lag 168 h",      "ENTSO-E A44", "Same hour last week — captures weekly seasonal patterns"),
    "rolling_mean_24h":("Price History", "Rolling mean 24 h",    "ENTSO-E A44", "24 h moving average of day-ahead price — dominant feature"),
    "rolling_std_24h": ("Price History", "Rolling vol. 24 h",    "ENTSO-E A44", "24 h rolling standard deviation — recent price volatility"),
    "rolling_mean_168h":("Price History","Rolling mean 168 h",   "ENTSO-E A44", "7-day moving average — medium-term price regime"),
    "rolling_std_168h":("Price History", "Rolling vol. 168 h",   "ENTSO-E A44", "7-day rolling standard deviation — weekly volatility regime"),
    # Supply-demand
    "load_forecast":            ("Supply-Demand", "Load forecast",          "ENTSO-E A65", "Day-ahead load forecast for Netherlands (MW)"),
    "net_load_forecast":        ("Supply-Demand", "Net load",               "ENTSO-E A65+A69", "Load minus wind and solar forecast — residual demand for dispatchable plant"),
    "renewable_share_forecast": ("Supply-Demand", "Renewable share",        "ENTSO-E A69", "Wind + solar as fraction of load — key price suppressor; high share → low/negative prices"),
    "total_wind_forecast":      ("Supply-Demand", "Total wind forecast",    "ENTSO-E A69", "Onshore + offshore wind generation forecast (MW)"),
    "solar_forecast":           ("Supply-Demand", "Solar forecast",         "ENTSO-E A69", "PV generation forecast (MW)"),
    # Generation mix
    "nuclear_lag24":    ("Generation Mix", "Nuclear output (lag 24 h)",  "ENTSO-E A75", "Nuclear generation 24 h ago (MW) — stable baseload, signals available capacity"),
    "gas_lag24":        ("Generation Mix", "Gas output (lag 24 h)",      "ENTSO-E A75", "Gas-fired generation 24 h ago (MW) — marginal cost proxy; high gas → high prices"),
    "wind_total_lag24": ("Generation Mix", "Wind output (lag 24 h)",     "ENTSO-E A75", "Actual total wind output 24 h ago (MW) — validates forecast reliability"),
}


def feature_data() -> list:
    """Load feature importances and attach human-readable metadata."""
    fi_path = DATA_DIR / "feature_importances.json"
    if not fi_path.exists():
        return []
    rows = pd.read_json(fi_path).to_dict("records")
    total = sum(r["importance"] for r in rows)
    out = []
    for r in rows:
        meta = FEATURE_META.get(r["feature"],
               ("Other", r["feature"], "Derived", "Engineered feature"))
        out.append({
            "name":        r["feature"],
            "label":       meta[1],
            "category":    meta[0],
            "source":      meta[2],
            "description": meta[3],
            "importance":  round(r["importance"], 5),
            "pct":         round(r["importance"] / total * 100, 1) if total else 0,
        })
    out.sort(key=lambda x: -x["importance"])
    return out


def build_payload():
    check_files()
    preds   = pd.read_csv(DATA_DIR / "price_predictions.csv")
    results = pd.read_csv(DATA_DIR / "battery_results.csv")
    sens    = pd.read_csv(DATA_DIR / "decision_sensitivity.csv")
    spo     = pd.read_csv(DATA_DIR / "spo_comparison.csv")

    sc = scatter_data(results)
    xs = np.array([d["mae"] for d in sc])
    ys = np.array([d["revenue"] for d in sc])
    slope, intercept, r_val, p_val, _ = sp_stats.linregress(xs, ys)

    rev = revenue_data(results)
    oracle_total = rev[-1]["oracle"] if rev else 0
    naive_total  = rev[-1]["naive"]  if rev else 0

    return {
        "meta":     data_source_meta(),
        "heatmap":  heatmap_data(preds),
        "dispatch": dispatch_data(results),
        "revenue":  rev,
        "clock":    clock_data(sens),
        "scatter":  sc,
        "spo": [{"model": r["model"],
                 "mae":  round(float(r["mae"]) if not pd.isna(r["mae"]) else 0, 1),
                 "revenue": round(float(r["revenue"]), 0),
                 "pct": round(float(r["pct_oracle"]), 1)}
                for _, r in spo.iterrows()],
        "ols": {"slope": round(slope, 2), "intercept": round(intercept, 0),
                "r": round(r_val, 3), "p": round(p_val, 3)},
        "stats": {
            "oracle": int(oracle_total), "naive": int(naive_total),
            "gap": int(oracle_total - naive_total),
            "gap_pct": round((oracle_total - naive_total) / oracle_total * 100, 1) if oracle_total else 0,
            "sens_pct": round(sens["sensitivity_score"].mean() * 100, 1),
            "mae": round(float(np.mean(np.abs(preds["actual"] - preds["forecast"]))), 1),
        },
        "features": feature_data(),
    }


# ── HTML ──────────────────────────────────────────────────────────────────────

def html(data_json: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Track 1 · Predict-Then-Optimize · NL Battery Dispatch</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root{{
  --bg:#F7F4EE;--surface:#FBF9F5;--border:#E5E0D8;
  --text:#1C1917;--muted:#78716C;--subtle:#A8A29E;
  --orange:#D4540A;--blue:#1B5E96;--green:#1B7A45;
  --purple:#6D28D9;--red:#9B1C1C;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth}}
body{{background:var(--bg);color:var(--text);font-family:'Inter',-apple-system,sans-serif;font-size:15px;line-height:1.6;overflow-x:hidden}}

/* Nav */
#sidenav{{position:fixed;right:22px;top:50%;transform:translateY(-50%);z-index:300;display:flex;flex-direction:column;gap:9px}}
.dot{{width:7px;height:7px;border-radius:50%;background:var(--border);cursor:pointer;transition:all .25s}}
.dot.on{{background:var(--orange);transform:scale(1.4)}}

/* Sections */
section{{min-height:100vh;display:flex;flex-direction:column;justify-content:center;padding:80px clamp(48px,6vw,120px);width:100%;position:relative}}
section+section{{border-top:1px solid var(--border)}}
.eyebrow{{font-size:10px;font-weight:600;letter-spacing:.18em;text-transform:uppercase;color:var(--orange);margin-bottom:10px}}
h1{{font-family:'Playfair Display',serif;font-size:clamp(32px,4vw,56px);line-height:1.15;margin-bottom:18px}}
h2{{font-family:'Playfair Display',serif;font-size:clamp(26px,3vw,40px);line-height:1.2;margin-bottom:14px}}
.lead{{font-size:16px;color:var(--muted);max-width:min(1000px,88%);margin-bottom:36px;font-weight:300}}

/* Hero */
#hero{{min-height:100vh;padding-top:120px}}
#hero h1 em{{font-style:italic;color:var(--orange)}}
.hero-line{{width:40px;height:3px;background:var(--orange);margin:20px 0 32px}}
.hero-stats{{display:flex;gap:48px;flex-wrap:wrap;margin-bottom:52px}}
.stat .num{{font-family:'Playfair Display',serif;font-size:clamp(38px,5vw,64px);font-weight:700;line-height:1;color:var(--orange)}}
.stat .num.blue{{color:var(--blue)}}.stat .num.green{{color:var(--green)}}
.stat .lbl{{font-size:11px;color:var(--muted);margin-top:5px;text-transform:uppercase;letter-spacing:.1em}}

/* Insight */
.insight{{display:inline-flex;gap:14px;align-items:flex-start;background:var(--surface);border-left:3px solid var(--orange);padding:14px 20px;border-radius:0 8px 8px 0;margin-top:24px;max-width:min(1000px,88%)}}
.insight-icon{{font-size:18px;flex-shrink:0;margin-top:1px}}
.insight-text{{font-size:13px;color:var(--muted);line-height:1.6}}
.insight-text strong{{display:block;color:var(--text);margin-bottom:3px;font-size:11px;text-transform:uppercase;letter-spacing:.08em}}

/* Simulation section */
#sim-banner{{display:flex;align-items:center;gap:18px;padding:14px 22px;background:var(--surface);border:1px solid var(--border);border-radius:10px;margin-bottom:14px;min-height:58px}}
#sim-action{{font-family:'Playfair Display',serif;font-size:20px;font-weight:700;min-width:170px;white-space:nowrap;transition:color .4s}}
#sim-narrative{{font-size:13px;color:var(--muted);font-style:italic;line-height:1.5}}
#sim-controls{{display:flex;align-items:center;gap:14px;margin-bottom:12px;flex-wrap:wrap}}
#sim-play-btn{{
  background:var(--orange);color:#fff;border:none;border-radius:6px;
  padding:8px 20px;font-size:13px;font-weight:500;cursor:pointer;
  font-family:'Inter',sans-serif;letter-spacing:.02em;transition:background .2s;min-width:90px
}}
#sim-play-btn:hover{{background:#B84508}}
#sim-slider{{flex:1;min-width:160px;accent-color:var(--orange);height:4px;cursor:pointer}}
.sim-time{{font-family:'Playfair Display',serif;font-size:22px;color:var(--text);min-width:60px}}
.sim-stat-row{{display:flex;gap:0;flex-wrap:wrap;margin-top:14px;border:1px solid var(--border);border-radius:10px;overflow:hidden;background:var(--surface)}}
.sim-stat{{flex:1;min-width:140px;padding:14px 20px;border-right:1px solid var(--border)}}
.sim-stat:last-child{{border-right:none}}
.sim-stat .sv{{font-family:'Playfair Display',serif;font-size:22px;font-weight:700;color:var(--text);line-height:1.2;transition:color .3s}}
.sim-stat .sl{{font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:var(--subtle);margin-top:4px}}
.soc-track{{height:5px;background:var(--border);border-radius:3px;overflow:hidden;margin-bottom:6px;width:100%}}
#sim-soc-bar{{height:100%;background:var(--blue);border-radius:3px;transition:width .6s ease}}

/* Chart common */
.chart-wrap{{width:100%;overflow-x:auto}}
.chart-row{{display:grid;grid-template-columns:1fr 1fr;gap:56px;align-items:start}}

/* Tooltip */
#tip{{position:fixed;background:#fff;border:1px solid var(--border);border-radius:8px;padding:10px 14px;font-size:12.5px;pointer-events:none;opacity:0;transition:opacity .15s;z-index:999;box-shadow:0 4px 16px rgba(0,0,0,.09);max-width:210px;line-height:1.5}}
#tip .tl{{font-weight:600;margin-bottom:4px;color:var(--text)}}
#tip .tv{{color:var(--muted)}}

/* Legend */
.legend{{display:flex;gap:18px;flex-wrap:wrap;margin-top:14px}}
.legend-item{{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--muted)}}
.legend-rect{{width:20px;height:10px;border-radius:2px;flex-shrink:0}}

/* SPO table */
.spo-table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}}
.spo-table th{{font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--subtle);font-weight:500;padding:0 10px 10px 0;border-bottom:1px solid var(--border);text-align:left}}
.spo-table td{{padding:10px 10px 10px 0;border-bottom:1px solid var(--border);vertical-align:middle}}
.spo-table tr.hl td{{font-weight:500}}
.spo-bar{{height:5px;border-radius:3px;background:var(--orange);opacity:.8}}

/* Fade-in */
.fade{{opacity:0;transform:translateY(28px);transition:opacity .65s ease,transform .65s ease}}
.fade.in{{opacity:1;transform:none}}
.fade.d1{{transition-delay:.12s}}.fade.d2{{transition-delay:.24s}}

svg text{{font-family:'Inter',-apple-system,sans-serif}}

/* ML Feature export */
#feat-toggle{{display:flex;align-items:center;gap:10px;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:14px 20px;cursor:pointer;font-family:'Inter',sans-serif;font-size:14px;font-weight:500;color:var(--text);width:100%;text-align:left;transition:border-color .2s}}
#feat-toggle:hover{{border-color:var(--orange)}}
#feat-toggle .arrow{{transition:transform .3s;font-size:11px;color:var(--orange)}}
#feat-toggle.open .arrow{{transform:rotate(180deg)}}
#feat-body{{margin-top:20px;display:none}}
.ftabs{{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:18px}}
.ftab{{background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:5px 14px;font-size:12px;font-weight:500;cursor:pointer;font-family:'Inter',sans-serif;color:var(--muted);transition:all .2s}}
.ftab.on{{background:var(--orange);border-color:var(--orange);color:#fff}}
.ftab:hover:not(.on){{border-color:var(--orange);color:var(--orange)}}
.feat-grid{{display:grid;grid-template-columns:1fr;gap:0;border:1px solid var(--border);border-radius:10px;overflow:hidden}}
.feat-hdr,.feat-row{{display:grid;grid-template-columns:180px 140px 160px 1fr 140px;gap:0;align-items:center}}
.feat-hdr{{background:var(--surface);border-bottom:1px solid var(--border);padding:10px 0}}
.feat-hdr span{{font-size:9px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--subtle);padding:0 16px}}
.feat-row{{padding:10px 0;border-bottom:1px solid var(--border);transition:background .15s}}
.feat-row:last-child{{border-bottom:none}}
.feat-row:hover{{background:var(--surface)}}
.feat-row > *{{padding:0 16px;font-size:12.5px}}
.feat-name{{font-family:'JetBrains Mono',monospace,sans-serif;font-size:11.5px;color:var(--text);font-weight:500}}
.feat-cat{{display:inline-flex}}.feat-cat span{{font-size:10px;font-weight:600;padding:2px 8px;border-radius:10px;white-space:nowrap}}
.cat-Temporal{{background:#EEF2FB;color:#3B5998}}
.cat-Price{{background:#FEF3E2;color:#B45309}}
.cat-Supply{{background:#EAFAF1;color:#1B7A45}}
.cat-Generation{{background:#F3E8FF;color:#6D28D9}}
.feat-src{{font-size:11px;color:var(--subtle)}}
.feat-desc{{font-size:12px;color:var(--muted);line-height:1.5}}
.feat-bar-wrap{{display:flex;align-items:center;gap:8px}}
.feat-bar-bg{{flex:1;height:5px;background:var(--border);border-radius:3px;overflow:hidden}}
.feat-bar{{height:100%;background:var(--orange);border-radius:3px;opacity:.85}}
.feat-pct{{font-size:11px;color:var(--muted);white-space:nowrap;min-width:34px;text-align:right}}

/* Live data badge */
#data-badge{{
  position:fixed;bottom:18px;left:22px;z-index:400;
  display:inline-flex;align-items:center;gap:7px;
  background:rgba(251,249,245,.92);border:1px solid var(--border);
  border-radius:20px;padding:6px 14px 6px 10px;
  font-size:11px;color:var(--muted);backdrop-filter:blur(6px);
  box-shadow:0 2px 8px rgba(0,0,0,.06);
}}
#data-badge .pulse{{
  width:7px;height:7px;border-radius:50%;background:#1B7A45;flex-shrink:0;
  animation:pulse 2s infinite;
}}
#data-badge .synth{{background:var(--subtle);animation:none;}}
@keyframes pulse{{0%,100%{{opacity:1;transform:scale(1)}}50%{{opacity:.5;transform:scale(1.3)}}}}
</style>
</head>
<body>

<div id="data-badge"></div>

<div id="sidenav">
  <div class="dot on"  data-i="0" title="Overview"></div>
  <div class="dot"     data-i="1" title="Simulation"></div>
  <div class="dot"     data-i="2" title="Price Calendar"></div>
  <div class="dot"     data-i="3" title="Dispatch Portrait"></div>
  <div class="dot"     data-i="4" title="Revenue Race"></div>
  <div class="dot"     data-i="5" title="Decision Sensitivity"></div>
  <div class="dot"     data-i="6" title="ML Features"></div>
</div>
<div id="tip"><div class="tl"></div><div class="tv"></div></div>

<!-- ══════════════════════════════════════════════════════════════ HERO -->
<section id="hero">
  <div class="eyebrow fade">Track 1 · Predict-Then-Optimize</div>
  <h1 class="fade d1">Between <em>Oracle</em> and Reality:<br>A 60-Day Energy Storage Experiment</h1>
  <div class="hero-line fade d1"></div>
  <p class="lead fade d2">A 1 MW / 2 MWh battery charges from the Dutch day-ahead electricity market when prices are low
  and sells when they peak. The only problem — prices must be forecast 24 hours ahead.
  How much does forecast error cost?</p>
  <div class="hero-stats">
    <div class="stat fade"><div class="num green" id="h-oracle">—</div><div class="lbl">Oracle revenue (€) — perfect foresight</div></div>
    <div class="stat fade d1"><div class="num blue" id="h-naive">—</div><div class="lbl">Naive P-T-O revenue (€) — XGBoost forecast</div></div>
    <div class="stat fade d2"><div class="num" id="h-gap">—</div><div class="lbl">Decision quality gap (€) — lost to forecast error</div></div>
  </div>
  <div class="insight fade d2">
    <span class="insight-icon">↓</span>
    <div class="insight-text"><strong>The Research Question</strong>
    Minimising forecast MSE is not the same as maximising dispatch profit.
    The sections below trace exactly where and why this gap opens — and motivate
    decision-focused learning (SPO+) as the remedy.</div>
  </div>
</section>

<!-- ══════════════════════════════════════════════════════════════ SIMULATION -->
<section id="sim">
  <div class="eyebrow fade">Hour-by-Hour Dispatch</div>
  <h2 class="fade">The Oracle's Perfect Day</h2>
  <p class="lead fade">24 hours of NL day-ahead prices — known in advance. The oracle charges during
  the cheapest windows (blue arrows) and sells at the peaks (orange arrows). The <span style="color:var(--blue);font-weight:500">blue curve</span>
  tracks the battery's charge level as the day unfolds. Every idle hour is a calculated decision, not a missed opportunity.</p>

  <div class="fade">
    <!-- Status banner — tells the story each hour -->
    <div id="sim-banner">
      <span id="sim-action" style="color:var(--muted)">○ Ready</span>
      <span id="sim-narrative">Press Play to simulate a day of oracle dispatch decisions</span>
    </div>
    <!-- Controls above the canvas -->
    <div id="sim-controls">
      <button id="sim-play-btn">▶ Play</button>
      <input type="range" id="sim-slider" min="0" max="23" value="0" step="1">
      <span class="sim-time" id="sim-hour-disp">00:00</span>
    </div>
    <div class="chart-wrap"><div id="sim-svg-wrap"></div></div>
    <div class="sim-stat-row">
      <div class="sim-stat">
        <div class="sv" id="sim-price">—</div>
        <div class="sl">Market price (€/MWh)</div>
      </div>
      <div class="sim-stat" style="min-width:180px">
        <div class="soc-track"><div id="sim-soc-bar" style="width:50%"></div></div>
        <div class="sv" id="sim-soc" style="font-size:16px;margin-top:4px">1.0 MWh</div>
        <div class="sl">Battery charge level</div>
      </div>
      <div class="sim-stat">
        <div class="sv" id="sim-revenue" style="color:var(--green)">€0</div>
        <div class="sl">Revenue earned today</div>
      </div>
    </div>
  </div>
</section>

<!-- ══════════════════════════════════════════════════════════════ HEATMAP -->
<section id="heatmap">
  <div class="eyebrow fade">Chart 1 of 5</div>
  <h2 class="fade">What the Market Looks Like</h2>
  <p class="lead fade">Netherlands day-ahead prices across 14 test days and 24 hours.
  <span style="color:var(--purple);font-weight:500">Purple = negative prices</span> (renewables flood the grid);
  <span style="color:var(--orange);font-weight:500">deep orange = scarcity peaks</span>.
  These are the signals the battery must read — one day ahead.</p>
  <div class="chart-wrap fade"><div id="heatmap-chart"></div></div>
  <div class="insight fade">
    <span class="insight-icon">⚡</span>
    <div class="insight-text"><strong>Why this matters for the LP</strong>
    Negative price hours are golden — the grid pays you to consume. The battery's entire profit
    depends on forecasting these relative rankings 24 hours early.</div>
  </div>
</section>

<!-- ══════════════════════════════════════════════════════════════ DISPATCH -->
<section id="dispatch">
  <div class="eyebrow fade">Chart 2 of 5</div>
  <h2 class="fade">Charge Low, Sell High</h2>
  <p class="lead fade">72 hours of oracle dispatch. The battery charges during cheap or negative-price periods
  (blue, below zero) and discharges at peaks (orange, above zero).
  The grey dashed line is the state of charge — what is physically possible at each moment.</p>
  <div class="chart-wrap fade"><div id="dispatch-chart"></div></div>
  <div class="legend fade">
    <div class="legend-item"><div class="legend-rect" style="background:var(--orange);opacity:.8"></div>Discharge — selling to grid</div>
    <div class="legend-item"><div class="legend-rect" style="background:var(--blue);opacity:.8"></div>Charge — buying from grid</div>
    <div class="legend-item"><div class="legend-rect" style="background:#999;opacity:.5;height:3px;margin-top:3px"></div>State of charge (MWh)</div>
  </div>
</section>

<!-- ══════════════════════════════════════════════════════════════ REVENUE -->
<section id="revenue">
  <div class="eyebrow fade">Chart 3 of 5</div>
  <h2 class="fade">The Growing Gap</h2>
  <p class="lead fade">Cumulative revenue over 60 test days. The oracle (dashed) is the upper bound of what
  is physically achievable with perfect foresight. Every missed negative-price hour and misjudged
  peak compounds the loss.</p>
  <div class="chart-wrap fade"><div id="revenue-chart"></div></div>
  <div class="insight fade">
    <span class="insight-icon">📉</span>
    <div class="insight-text"><strong>The compounding effect</strong>
    The gap spikes on high-volatility days where price events were missed or misforecast.
    These are exactly the days SPO+ is designed to target by training on decision regret,
    not prediction error.</div>
  </div>
</section>

<!-- ══════════════════════════════════════════════════════════════ EXPLAIN -->
<section id="explain">
  <div class="eyebrow fade">Charts 4 & 5 of 5</div>
  <h2 class="fade">When Forecast Errors Matter</h2>
  <p class="lead fade">Not all forecast errors are equal. A 10 €/MWh error at 3 am changes nothing;
  the same error at 6 pm can flip the charge/discharge decision entirely.</p>
  <div class="chart-row">
    <div>
      <p style="font-size:13px;color:var(--muted);margin-bottom:16px" class="fade">
        <strong style="color:var(--text)">Decision sensitivity clock</strong><br>
        Arc radius = probability that a ±10 €/MWh forecast shift flips dispatch. Colour = sensitivity level.</p>
      <div class="fade"><div id="clock-chart"></div></div>
    </div>
    <div>
      <p style="font-size:13px;color:var(--muted);margin-bottom:16px" class="fade">
        <strong style="color:var(--text)">Lower MAE → Higher revenue</strong><br>
        Each point is one test day. OLS confirms: forecast accuracy and decision quality move together.</p>
      <div class="fade"><div id="scatter-chart"></div></div>
      <div class="fade" style="margin-top:28px">
        <p style="font-size:11px;color:var(--subtle);margin-bottom:10px;text-transform:uppercase;letter-spacing:.1em;font-weight:500">Model comparison · 60-day dispatch revenue</p>
        <table class="spo-table" id="spo-table"></table>
      </div>
    </div>
  </div>
  <div class="insight fade" style="margin-top:40px">
    <span class="insight-icon">🎯</span>
    <div class="insight-text"><strong>The SPO+ research agenda</strong>
    Standard XGBoost minimises MSE uniformly across all hours.
    Smart Predict-Then-Optimize (Elmachtoub & Grigas, 2022) trains the model to minimise
    <em>decision regret</em> — concentrating accuracy at the sensitive hours shown in the clock above.</div>
  </div>
</section>

<!-- ══════════════════════════════════════════════════════════════ ML FEATURES -->
<section id="features" style="min-height:auto;padding-top:64px;padding-bottom:80px">
  <div class="eyebrow fade">Model Transparency · XGBoost Training Set</div>
  <h2 class="fade">Feature Export</h2>
  <p class="lead fade">Every variable used to train the day-ahead price forecaster.
  Sourced from five ENTSO-E transparency series — no proprietary data.
  Importance = XGBoost split gain, normalised to sum to 100%.</p>

  <div class="fade" style="margin-top:8px">
    <button id="feat-toggle">
      <span class="arrow">▼</span>
      <span id="feat-toggle-label">Show all features</span>
      <span style="margin-left:auto;font-size:11px;color:var(--subtle)" id="feat-count"></span>
    </button>
    <div id="feat-body">
      <div class="ftabs" id="feat-tabs"></div>
      <div class="feat-grid" id="feat-grid">
        <div class="feat-hdr">
          <span>Feature</span><span>Category</span><span>Source</span>
          <span>Description</span><span>Importance</span>
        </div>
        <div id="feat-rows"></div>
      </div>
    </div>
  </div>
</section>

<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
const DATA = {data_json};
const {{meta,heatmap,dispatch,revenue,clock,scatter,spo,ols,stats,features}} = DATA;

// ── Data source badge ────────────────────────────────────────────────────────
(function(){{
  const b = document.getElementById("data-badge");
  const dot = document.createElement("div");
  dot.className = "pulse" + (meta.live ? "" : " synth");
  b.appendChild(dot);
  const label = document.createElement("span");
  label.textContent = meta.live
    ? `Live ENTSO-E · ${{meta.start}} – ${{meta.end}}`
    : "Synthetic data · run entsoe_fetch_rich.py for live";
  b.appendChild(label);
}})();
const fmt = d3.format(",.0f");
const fmtE = v => "€"+fmt(v);
const $ = id => document.getElementById(id);

// ── Tooltip ──────────────────────────────────────────────────────────────────
const tip = $("tip");
function showTip(ev,label,val){{
  tip.querySelector(".tl").textContent=label;
  tip.querySelector(".tv").innerHTML=val;
  tip.style.opacity=1; moveTip(ev);
}}
function moveTip(ev){{
  const {{clientX:x,clientY:y}}=ev;
  const tw=tip.offsetWidth,th=tip.offsetHeight;
  tip.style.left=(x+14>window.innerWidth-tw-8?x-tw-14:x+14)+"px";
  tip.style.top=(y-th/2<4?4:y-th/2)+"px";
}}
function hideTip(){{tip.style.opacity=0;}}

const priceColor = d3.scaleLinear()
  .domain([-60,0,50,120,175])
  .range(["#6D28D9","#F7F4EE","#FCD34D","#D4540A","#7F1D1D"]).clamp(true);

// ════════════════════════════════════════════════════════════════════
// SIMULATION — price bar chart + SOC curve story
// ════════════════════════════════════════════════════════════════════
(function initSim(){{
  const simDay = dispatch.slice(0,24);
  const BATT_W = 110, GAP = 20;
  const W = Math.min($("sim-svg-wrap").clientWidth||960, 960);
  const H = 270;
  const m = {{t:38, r:8, b:50, l:46}};
  const chartW = W - BATT_W - GAP;
  const iW = chartW - m.l - m.r, iH = H - m.t - m.b;
  const bw = iW / 24, bp = 2;

  const svg = d3.select("#sim-svg-wrap").append("svg").attr("width",W).attr("height",H);
  const g   = svg.append("g").attr("transform",`translate(${{m.l}},${{m.t}})`);

  // ── Price scales — zero line proportional to actual range ──────────
  const prices = simDay.map(d => d.price);
  const maxP = d3.max(prices), minP = d3.min(prices);
  const hasNeg = minP < -1;
  // Allocate vertical space proportionally: positive range above zero, negative below
  const topRange = maxP * 1.10;
  const botRange = hasNeg ? Math.abs(minP) * 1.15 : topRange * 0.08;
  const zeroY = iH * topRange / (topRange + botRange);  // zero line from top
  const pY = v => v >= 0
    ? zeroY - (v / topRange) * zeroY
    : zeroY + (Math.abs(v) / botRange) * (iH - zeroY);
  const socYS = d3.scaleLinear().domain([0,2]).range([zeroY * 0.90, 5]);

  // ── Column tints for charge / sell hours ───────────────────────────
  simDay.forEach((d,i) => {{
    const isChg = d.charge>0.05, isDis = d.discharge>0.05;
    if (!isChg && !isDis) return;
    g.append("rect").attr("x",i*bw).attr("y",0).attr("width",bw).attr("height",iH)
      .attr("fill", d.price<0?"rgba(109,40,217,.08)":isChg?"rgba(27,94,150,.08)":"rgba(212,84,10,.08)");
  }});

  // ── Zero line ──────────────────────────────────────────────────────
  g.append("line").attr("x1",-4).attr("x2",iW).attr("y1",zeroY).attr("y2",zeroY)
    .attr("stroke","#DDD8CE").attr("stroke-width",1);
  g.append("text").attr("x",-8).attr("y",zeroY+4).attr("text-anchor","end")
    .style("font-size","9px").style("fill","#B0A89E").text("0€");

  // ── Price bars ─────────────────────────────────────────────────────
  const bars = g.selectAll("rect.pb").data(simDay).join("rect").attr("class","pb")
    .attr("x",(d,i)=>i*bw+bp).attr("width",bw-bp*2)
    .attr("y",d=>pY(Math.max(0,d.price)))
    .attr("height",d=>Math.max(2,Math.abs(pY(d.price)-zeroY)))
    .attr("fill",d=>priceColor(d.price)).attr("rx",2).attr("opacity",0.25);

  // ── Plan arrows above action bars (visible from start) ─────────────
  simDay.forEach((d,i) => {{
    const isChg = d.charge>0.05, isDis = d.discharge>0.05;
    if (!isChg && !isDis) return;
    g.append("text").attr("x",i*bw+bw/2).attr("y",-5).attr("text-anchor","middle")
      .style("font-size","9px").attr("opacity",.4)
      .style("fill",d.price<0?"#9B6FD4":isChg?"#1B5E96":"#D4540A")
      .text(isChg?"↓":"↑");
  }});

  // ── Hour axis ──────────────────────────────────────────────────────
  [0,3,6,9,12,15,18,21].forEach(h => {{
    g.append("line").attr("x1",h*bw+bw/2).attr("x2",h*bw+bw/2)
      .attr("y1",iH+1).attr("y2",iH+6).attr("stroke","#D6D0C8").attr("stroke-width",1);
    g.append("text").attr("x",h*bw+bw/2).attr("y",iH+18).attr("text-anchor","middle")
      .style("font-size","10px").style("fill","#A8A29E")
      .text(h===0?"midnight":h===12?"noon":h+":00");
  }});

  // ── SOC curve (drawn progressively) ───────────────────────────────
  const socLineF  = d3.line().x(d=>d.x).y(d=>socYS(d.soc)).curve(d3.curveCatmullRom.alpha(0.5));
  const socAreaFn = d3.area().x(d=>d.x).y0(d=>zeroY*0.92).y1(d=>socYS(d.soc)).curve(d3.curveCatmullRom.alpha(0.5));
  const socPath = g.append("path").attr("fill","none").attr("stroke","#1B5E96").attr("stroke-width",2).attr("opacity",.55);
  const socFill = g.append("path").attr("fill","rgba(27,94,150,.07)").attr("stroke","none");

  // ── Current-hour cursor ────────────────────────────────────────────
  const cursor = g.append("g").attr("opacity",0);
  cursor.append("line").attr("class","cl").attr("y1",-m.t+8).attr("y2",iH)
    .attr("stroke","#1C1917").attr("stroke-width",1.5).attr("opacity",.35);
  cursor.append("rect").attr("class","cb").attr("width",38).attr("height",17).attr("rx",4)
    .attr("fill","#1C1917").attr("opacity",.85);
  cursor.append("text").attr("class","ct").attr("text-anchor","middle").attr("y",-m.t+18)
    .style("font-size","10px").style("font-weight","700").style("fill","#fff");
  const actIcon  = g.append("text").attr("text-anchor","middle").style("font-size","16px").attr("opacity",0);
  const actPrice = g.append("text").attr("text-anchor","middle").style("font-size","11px").style("font-weight","600").attr("opacity",0);

  // ── Battery panel (right side) ─────────────────────────────────────
  const bpX = chartW + GAP;  // battery panel origin x
  const BW=54, BH=iH+4;
  const BX=(BATT_W-BW)/2, BY=m.t-2;
  const bp2 = svg.append("g").attr("transform",`translate(${{bpX}},0)`);

  // Terminal nub
  bp2.append("rect").attr("x",BX+BW/2-11).attr("y",BY-8)
    .attr("width",22).attr("height",9).attr("rx",3).attr("fill","#C7C0B8");
  // Outer body
  bp2.append("rect").attr("x",BX).attr("y",BY).attr("width",BW).attr("height",BH)
    .attr("rx",6).attr("fill","none").attr("stroke","#C7C0B8").attr("stroke-width",2);
  // Background fill track
  bp2.append("rect").attr("x",BX+3).attr("y",BY+3).attr("width",BW-6).attr("height",BH-6)
    .attr("rx",4).attr("fill","rgba(0,0,0,.03)");

  // Animated fill
  const battFill = bp2.append("rect")
    .attr("x",BX+3).attr("y",BY+BH-3).attr("width",BW-6).attr("height",0)
    .attr("rx",4).attr("fill","#8BAFC4");

  // Percentage text
  const battPct = bp2.append("text").attr("x",BX+BW/2).attr("y",BY+BH/2-3)
    .attr("text-anchor","middle").style("font-family","'Playfair Display',serif")
    .style("font-size","17px").style("font-weight","700").style("fill","#1C1917").text("50%");
  const battMwh = bp2.append("text").attr("x",BX+BW/2).attr("y",BY+BH/2+14)
    .attr("text-anchor","middle").style("font-size","9px").style("fill","#78716C").text("1.0 MWh");

  // Action label above battery
  const battAct = bp2.append("text").attr("x",BX+BW/2).attr("y",BY-14)
    .attr("text-anchor","middle").style("font-size","9px").style("font-weight","600")
    .attr("opacity",0);

  // Animated flow arrows (charge = downward ↓ into battery, discharge = ↑ out)
  const flowArrow = bp2.append("text").attr("x",BX+BW/2).attr("y",BY+BH/2+36)
    .attr("text-anchor","middle").style("font-size","20px").attr("opacity",0);

  bp2.append("text").attr("x",BX+BW/2).attr("y",BY+BH+18).attr("text-anchor","middle")
    .style("font-size","8px").style("font-weight","700").style("letter-spacing",".12em")
    .style("fill","#A8A29E").text("BATTERY");
  bp2.append("text").attr("x",BX+BW/2).attr("y",BY+BH+30).attr("text-anchor","middle")
    .style("font-size","8px").style("fill","#B0A89E").text("1MW · 2MWh · 90%");

  // Legend (bottom left of chart)
  svg.append("circle").attr("cx",m.l+6).attr("cy",H-8).attr("r",4)
    .attr("fill","#1B5E96").attr("opacity",.55);
  svg.append("text").attr("x",m.l+14).attr("y",H-4)
    .style("font-size","9px").style("fill","#1B5E96").attr("opacity",.6).text("battery SOC");

  // ── State ──────────────────────────────────────────────────────────
  let curH=0, cumRev=0;
  const socPts=[];

  function stepHour(h) {{
    curH=h;
    const D=simDay[h];
    const isChg=D.charge>0.05, isDis=D.discharge>0.05, isNeg=D.price<0;
    const soc=Math.max(0,Math.min(2,D.soc));
    if (isDis&&D.price>0) cumRev+=D.price*D.discharge;

    bars.attr("opacity",(d,i)=>i<h?0.78:i===h?1:0.2);

    // Cursor
    const cx=h*bw+bw/2;
    cursor.attr("opacity",1);
    cursor.select(".cl").attr("x1",cx).attr("x2",cx);
    cursor.select(".cb").attr("x",cx-19).attr("y",-m.t+7);
    cursor.select(".ct").attr("x",cx).text(String(h).padStart(2,"0")+":00");
    const barTopY=pY(Math.max(0,D.price));
    actIcon.attr("x",cx).attr("y",barTopY-4).attr("opacity",1)
      .style("fill",isNeg?"#6D28D9":isChg?"#1B5E96":isDis?"#D4540A":"#A8A29E")
      .text(isChg?"⬇":isDis?"⬆":"·");
    actPrice.attr("x",cx).attr("y",barTopY-20).attr("opacity",.9)
      .style("fill",priceColor(D.price))
      .text((D.price>=0?"+":"")+D.price.toFixed(0)+"€");

    // SOC curve
    if (!socPts.find(p=>p.h===h)) socPts.push({{h,x:cx,soc}});
    if (socPts.length>1) {{ socPath.attr("d",socLineF(socPts)); socFill.attr("d",socAreaFn(socPts)); }}

    // ── Battery animation ───────────────────────────────────────────
    const fillH=Math.max(0,(BH-6)*(soc/2));
    const fillColor=isNeg?"#6D28D9":isChg?"#1B5E96":isDis?"#D4540A":"#8BAFC4";
    battFill.transition().duration(420).ease(d3.easeQuadOut)
      .attr("y",BY+BH-3-fillH).attr("height",fillH).attr("fill",fillColor);
    const pct=Math.round(soc/2*100);
    battPct.text(pct+"%").style("fill",pct>58?"#fff":"#1C1917");
    battMwh.text(soc.toFixed(1)+" MWh").style("fill",pct>58?"rgba(255,255,255,.65)":"#78716C");

    // Action label + animated arrow
    if (isChg||isDis) {{
      battAct.attr("opacity",1).style("fill",isNeg?"#6D28D9":isChg?"#1B5E96":"#D4540A")
        .text(isNeg?"← grid pays":"CHARGING".slice(0,isChg?8:0)||(isDis?"SELLING":""));
      flowArrow.attr("opacity",isChg?0:isDis?0:0);  // handled by battAct
    }} else {{
      battAct.attr("opacity",0);
    }}

    // Stats
    $("sim-price").textContent=(D.price>=0?"+":"")+D.price.toFixed(0)+" €/MWh";
    $("sim-price").style.color=isNeg?"#6D28D9":D.price>80?"#D4540A":"var(--text)";
    $("sim-soc").textContent=soc.toFixed(1)+" MWh ("+pct+"%)";
    $("sim-soc-bar").style.width=pct+"%";
    $("sim-revenue").textContent=fmtE(Math.round(cumRev));
    $("sim-hour-disp").textContent=String(h).padStart(2,"0")+":00";
    $("sim-slider").value=h;

    // Narrative
    let action,narr,col;
    if (isChg&&isNeg) {{
      action="⬇ Charging — grid pays us";
      narr=`${{D.price.toFixed(0)}} €/MWh — renewables flooding the grid. We're paid ${{Math.abs(D.price).toFixed(0)}} €/MWh to absorb surplus. Battery charges and earns.`;
      col="#6D28D9";
    }} else if (isChg) {{
      action="⬇ Charging — buying low";
      narr=`${{D.price.toFixed(0)}} €/MWh — one of today's cheapest hours. Buying ${{D.charge.toFixed(1)}} MW now to sell at the day's peak.`;
      col="#1B5E96";
    }} else if (isDis) {{
      action="⬆ Discharging — selling high";
      narr=`${{D.price.toFixed(0)}} €/MWh — peak demand. Releasing ${{D.discharge.toFixed(1)}} MW earns €${{(D.price*D.discharge).toFixed(0)}} this hour alone.`;
      col="#D4540A";
    }} else {{
      action="○ Holding — optimal wait";
      narr=`${{D.price.toFixed(0)}} €/MWh — the LP says wait. Not cheap enough to charge, not high enough to sell. Every idle hour is intentional.`;
      col="#78716C";
    }}
    $("sim-action").textContent=action; $("sim-action").style.color=col;
    $("sim-narrative").textContent=narr;
  }}

  function jumpTo(h) {{
    cumRev=0; socPts.length=0;
    socPath.attr("d",null); socFill.attr("d",null);
    cursor.attr("opacity",0); actIcon.attr("opacity",0); actPrice.attr("opacity",0);
    bars.attr("opacity",0.2);
    battFill.attr("y",BY+BH-3).attr("height",0).attr("fill","#8BAFC4");
    battPct.text("0%").style("fill","#1C1917");
    battMwh.text("0.0 MWh").style("fill","#78716C");
    for (let i=0;i<=h;i++) {{ const D=simDay[i]; if(D.discharge>0.05&&D.price>0) cumRev+=D.price*D.discharge; }}
    stepHour(h);
  }}

  let playing=false, timer=null;
  function advance() {{
    if (!playing) return;
    if (curH>=23) {{ playing=false; $("sim-play-btn").textContent="↺ Replay"; $("sim-play-btn").dataset.mode="replay"; return; }}
    curH++; stepHour(curH); timer=setTimeout(advance,1050);
  }}
  $("sim-play-btn").addEventListener("click", function() {{
    if (this.dataset.mode==="replay") {{
      this.dataset.mode=""; playing=true; this.textContent="⏸ Pause"; jumpTo(0); setTimeout(advance,400);
    }} else {{
      playing=!playing; this.textContent=playing?"⏸ Pause":"▶ Play";
      if(playing) advance(); else if(timer){{clearTimeout(timer);timer=null;}}
    }}
  }});
  $("sim-slider").addEventListener("input", function() {{
    playing=false; if(timer){{clearTimeout(timer);timer=null;}}
    $("sim-play-btn").textContent="▶ Play"; $("sim-play-btn").dataset.mode="";
    jumpTo(parseInt(this.value));
  }});
  stepHour(0);
  setTimeout(()=>{{playing=true;$("sim-play-btn").textContent="⏸ Pause";advance();}},900);
}})();

// ════════════════════════════════════════════════════════════════════
// CHART 1 · PRICE HEATMAP
// ════════════════════════════════════════════════════════════════════
(function drawHeatmap(){{
  const dates=[...new Set(heatmap.map(d=>d.date))].sort();
  const W0=Math.min($("heatmap-chart").clientWidth||900,960);
  const cellW=Math.floor((W0-90)/24);
  const cellH=Math.max(22,Math.floor(Math.min(42,(460-50)/dates.length)));
  const m={{t:30,r:20,b:44,l:86}};
  const W=cellW*24+m.l+m.r, H=cellH*dates.length+m.t+m.b;
  const svg=d3.select("#heatmap-chart").append("svg").attr("width",W).attr("height",H);
  const g=svg.append("g").attr("transform",`translate(${{m.l}},${{m.t}})`);
  const xB=d3.scaleBand().domain(d3.range(24)).range([0,cellW*24]).padding(.06);
  const yB=d3.scaleBand().domain(dates).range([0,cellH*dates.length]).padding(.06);
  g.selectAll("rect.c").data(heatmap).join("rect").attr("class","c")
    .attr("x",d=>xB(d.hour)).attr("y",d=>yB(d.date))
    .attr("width",xB.bandwidth()).attr("height",yB.bandwidth())
    .attr("fill",d=>priceColor(d.price)).attr("rx",2)
    .on("mousemove",(ev,d)=>showTip(ev,`${{d.date}} · ${{d.hour}}:00h`,
      `<span style="color:${{priceColor(d.price)}};font-weight:600">${{d.price>0?"+":""}}${{d.price}} €/MWh</span>`))
    .on("mouseleave",hideTip);
  g.append("g").attr("transform",`translate(0,${{cellH*dates.length+4}})`)
    .call(d3.axisBottom(xB).tickValues(d3.range(0,24,3)).tickFormat(h=>h+"h").tickSize(4))
    .call(g=>g.select(".domain").remove())
    .call(g=>g.selectAll("text").style("font-size","11px").style("fill","#78716C"));
  g.append("g").attr("transform","translate(-8,0)")
    .call(d3.axisLeft(yB).tickFormat(d=>{{const dt=new Date(d+"T00:00:00");return d3.timeFormat("%d %b")(dt);}}).tickSize(0))
    .call(g=>g.select(".domain").remove())
    .call(g=>g.selectAll("text").style("font-size","11px").style("fill","#78716C"));
  // Legend
  const lgW=200, defs=svg.append("defs");
  const grad=defs.append("linearGradient").attr("id","hm-g").attr("x1","0%").attr("x2","100%");
  [[-60,"#6D28D9"],[0,"#F7F4EE"],[50,"#FCD34D"],[120,"#D4540A"],[175,"#7F1D1D"]].forEach(([v,c])=>
    grad.append("stop").attr("offset",`${{(v+60)/235*100}}%`).attr("stop-color",c));
  const lg=svg.append("g").attr("transform",`translate(${{m.l}},${{H-12}})`);
  lg.append("rect").attr("width",lgW).attr("height",10).attr("rx",3).attr("fill","url(#hm-g)");
  ["−60","0","","120","175+ €/MWh"].forEach((t,i)=>
    lg.append("text").attr("x",lgW/4*i).attr("y",23)
      .style("font-size","9px").style("fill","#A8A29E").text(t));
}})();

// ════════════════════════════════════════════════════════════════════
// CHART 2 · DISPATCH PORTRAIT
// ════════════════════════════════════════════════════════════════════
(function drawDispatch(){{
  const m={{t:16,r:24,b:44,l:48}};
  const W=Math.min($("dispatch-chart").clientWidth||920,960), H=340;
  const iW=W-m.l-m.r, iH=H-m.t-m.b;
  const svg=d3.select("#dispatch-chart").append("svg").attr("width",W).attr("height",H);
  const g=svg.append("g").attr("transform",`translate(${{m.l}},${{m.t}})`);
  const times=dispatch.map(d=>new Date(d.dt));
  const x=d3.scaleTime().domain(d3.extent(times)).range([0,iW]);
  const midY=iH*0.54, bw=iW/dispatch.length, bs=midY/1.05;
  g.selectAll("rect.pb").data(dispatch).join("rect")
    .attr("x",(_,i)=>i*bw).attr("y",0).attr("width",bw).attr("height",iH)
    .attr("fill",d=>priceColor(d.price)).attr("opacity",.12);
  g.append("line").attr("x1",0).attr("x2",iW).attr("y1",midY).attr("y2",midY)
    .attr("stroke","#C7C0B8").attr("stroke-width",1);
  g.selectAll("rect.dis").data(dispatch).join("rect").attr("class","dis")
    .attr("x",(_,i)=>i*bw+1).attr("width",bw-2)
    .attr("y",d=>midY-d.discharge*bs).attr("height",d=>d.discharge*bs)
    .attr("fill","#D4540A").attr("opacity",.78).attr("rx",1)
    .on("mousemove",(ev,d)=>showTip(ev,`${{d.dt.slice(0,13)}}h`,`Discharge: <b>${{d.discharge.toFixed(2)}} MW</b><br>Price: ${{d.price}} €/MWh`))
    .on("mouseleave",hideTip);
  g.selectAll("rect.chg").data(dispatch).join("rect").attr("class","chg")
    .attr("x",(_,i)=>i*bw+1).attr("width",bw-2)
    .attr("y",midY).attr("height",d=>d.charge*bs)
    .attr("fill","#1B5E96").attr("opacity",.78).attr("rx",1)
    .on("mousemove",(ev,d)=>showTip(ev,`${{d.dt.slice(0,13)}}h`,`Charge: <b>${{d.charge.toFixed(2)}} MW</b><br>Price: ${{d.price}} €/MWh`))
    .on("mouseleave",hideTip);
  const socLine=d3.line().x((_,i)=>i*bw+bw/2).y(d=>midY-d.soc/2*bs*1.6).curve(d3.curveMonotoneX);
  g.append("path").datum(dispatch).attr("d",socLine)
    .attr("fill","none").attr("stroke","#888").attr("stroke-width",1.5).attr("stroke-dasharray","4,3").attr("opacity",.65);
  const priceLine=d3.line().x((_,i)=>i*bw+bw/2).y(d=>{{
    const py=d3.scaleLinear().domain([d3.min(dispatch,d=>d.price),d3.max(dispatch,d=>d.price)]).range([iH-8,8]);
    return py(d.price);
  }}).curve(d3.curveMonotoneX);
  g.append("path").datum(dispatch).attr("d",priceLine)
    .attr("fill","none").attr("stroke","#1C1917").attr("stroke-width",1.3).attr("opacity",.28);
  dispatch.forEach((d,i)=>{{if(d.dt.endsWith("T00:00")){{
    g.append("line").attr("x1",i*bw).attr("x2",i*bw).attr("y1",0).attr("y2",iH)
      .attr("stroke","#C7C0B8").attr("stroke-width",.8).attr("stroke-dasharray","3,3");
    g.append("text").attr("x",i*bw+4).attr("y",12)
      .style("font-size","10px").style("fill","#A8A29E")
      .text(new Date(d.dt).toLocaleDateString("en-GB",{{day:"numeric",month:"short"}}));
  }}}});
  g.append("text").attr("x",iW).attr("y",midY-bs*0.45).attr("text-anchor","end")
    .style("font-size","10px").style("fill","#D4540A").text("discharge ↑");
  g.append("text").attr("x",iW).attr("y",midY+bs*0.45).attr("text-anchor","end")
    .style("font-size","10px").style("fill","#1B5E96").text("charge ↓");
}})();

// ════════════════════════════════════════════════════════════════════
// CHART 3 · REVENUE RACE
// ════════════════════════════════════════════════════════════════════
(function drawRevenue(){{
  const m={{t:20,r:80,b:44,l:68}};
  const W=Math.min($("revenue-chart").clientWidth||920,960),H=320;
  const iW=W-m.l-m.r,iH=H-m.t-m.b;
  const svg=d3.select("#revenue-chart").append("svg").attr("width",W).attr("height",H);
  const g=svg.append("g").attr("transform",`translate(${{m.l}},${{m.t}})`);
  const allV=revenue.flatMap(d=>[d.oracle,d.naive]);
  const x=d3.scaleLinear().domain([1,revenue.length]).range([0,iW]);
  const y=d3.scaleLinear().domain([Math.min(0,d3.min(allV))-500,d3.max(allV)*1.05]).range([iH,0]);
  const defs=svg.append("defs");
  const gg=defs.append("linearGradient").attr("id","gap-g").attr("x1","0%").attr("x2","100%");
  gg.append("stop").attr("offset","0%").attr("stop-color","#D4540A").attr("stop-opacity",.05);
  gg.append("stop").attr("offset","100%").attr("stop-color","#D4540A").attr("stop-opacity",.18);
  g.append("path").datum(revenue)
    .attr("d",d3.area().x(d=>x(d.day)).y0(d=>y(d.naive)).y1(d=>y(d.oracle)).curve(d3.curveMonotoneX))
    .attr("fill","url(#gap-g)");
  g.append("path").datum(revenue)
    .attr("d",d3.line().x(d=>x(d.day)).y(d=>y(d.oracle)).curve(d3.curveMonotoneX))
    .attr("fill","none").attr("stroke","#1B7A45").attr("stroke-width",1.5).attr("stroke-dasharray","5,4").attr("opacity",.7);
  g.append("path").datum(revenue)
    .attr("d",d3.line().x(d=>x(d.day)).y(d=>y(d.naive)).curve(d3.curveMonotoneX))
    .attr("fill","none").attr("stroke","#1B5E96").attr("stroke-width",2.2);
  const scrub=g.append("line").attr("y1",0).attr("y2",iH).attr("stroke","#C7C0B8").attr("stroke-width",1).attr("opacity",0);
  const bis=d3.bisector(d=>d.day).left;
  svg.on("mousemove",ev=>{{
    const [mx]=d3.pointer(ev,g.node());
    const day=Math.round(x.invert(mx));
    const d=revenue[Math.max(0,Math.min(bis(revenue,day),revenue.length-1))];
    scrub.attr("x1",x(d.day)).attr("x2",x(d.day)).attr("opacity",.6);
    showTip(ev,`Day ${{d.day}} · ${{d.date}}`,`Oracle: <b>${{fmtE(d.oracle)}}</b><br>Naive: <b>${{fmtE(d.naive)}}</b><br>Gap: ${{fmtE(d.oracle-d.naive)}}`);
  }}).on("mouseleave",()=>{{scrub.attr("opacity",0);hideTip();}});
  g.append("g").attr("transform",`translate(0,${{iH}})`)
    .call(d3.axisBottom(x).ticks(10).tickFormat(d=>`Day ${{d}}`))
    .call(g=>g.select(".domain").remove()).call(g=>g.selectAll("text").style("font-size","10px").style("fill","#A8A29E"));
  g.append("g").call(d3.axisLeft(y).ticks(5).tickFormat(fmtE))
    .call(g=>g.select(".domain").remove()).call(g=>g.selectAll("text").style("font-size","10px").style("fill","#A8A29E"));
  const last=revenue[revenue.length-1];
  g.append("text").attr("x",iW+6).attr("y",y(last.oracle)).attr("dominant-baseline","middle")
    .style("font-size","11px").style("fill","#1B7A45").text("Oracle");
  g.append("text").attr("x",iW+6).attr("y",y(last.naive)).attr("dominant-baseline","middle")
    .style("font-size","11px").style("fill","#1B5E96").text("Naive");
  const midD=revenue[Math.floor(revenue.length*.72)];
  g.append("text").attr("x",x(midD.day)).attr("y",(y(midD.oracle)+y(midD.naive))/2)
    .attr("text-anchor","middle").attr("dominant-baseline","middle")
    .style("font-size","11px").style("fill","#D4540A").style("font-style","italic")
    .text(`${{fmtE(midD.oracle-midD.naive)}} gap`);
}})();

// ════════════════════════════════════════════════════════════════════
// CHART 4 · DECISION CLOCK  (radius = revenue impact, colour = flip rate)
// ════════════════════════════════════════════════════════════════════
(function drawClock(){{
  const S=360, cx=S/2, cy=S/2;
  const maxR=S/2-32, minR=S/2-116;
  const overallS=(clock.reduce((a,d)=>a+d.sensitivity,0)/clock.length*100).toFixed(1);
  const maxImpact = d3.max(clock,d=>d.impact);
  const avgImpact = Math.round(clock.filter(d=>d.impact>0).reduce((a,d)=>a+d.impact,0)/clock.filter(d=>d.impact>0).length);

  const svg=d3.select("#clock-chart").append("svg").attr("width",S).attr("height",S);
  const g=svg.append("g").attr("transform",`translate(${{cx}},${{cy}})`);

  // Subtle guide rings
  [.25,.5,.75,1].forEach(f=>
    g.append("circle").attr("r",minR+(maxR-minR)*f)
      .attr("fill","none").attr("stroke","rgba(0,0,0,.07)").attr("stroke-width",.8));

  // Arc: radius ∝ revenue impact, colour = flip-rate sensitivity
  const arc=d3.arc()
    .innerRadius(minR)
    .outerRadius(d=>d.impact>0 ? minR+(maxR-minR)*(d.impact/maxImpact) : minR+4)
    .startAngle(d=>(d.hour/24)*2*Math.PI-Math.PI/2)
    .endAngle(d=>((d.hour+1)/24)*2*Math.PI-Math.PI/2)
    .padAngle(.018).cornerRadius(3);

  // Colour: grey=safe → amber=medium → deep red=most sensitive
  const clr=d3.scaleLinear().domain([0,0.6,1])
    .range(["#C9E8D4","#F59E0B","#991B1B"]);

  g.selectAll("path.seg").data(clock).join("path").attr("class","seg")
    .attr("d",arc).attr("fill",d=>clr(d.sensitivity)).attr("opacity",.9)
    .on("mousemove",(ev,d)=>showTip(ev,`${{d.hour}}:00–${{d.hour+1}}:00`,
      `Flip rate: <b>${{(d.sensitivity*100).toFixed(0)}}%</b><br>Avg revenue impact: <b>${{fmtE(d.impact)}}</b>`))
    .on("mouseleave",hideTip);

  // Hour labels every 3h
  d3.range(0,24,3).forEach(h=>{{
    const angle=(h/24)*2*Math.PI-Math.PI/2;
    const r=maxR+20;
    g.append("text").attr("x",r*Math.cos(angle)).attr("y",r*Math.sin(angle))
      .attr("text-anchor","middle").attr("dominant-baseline","middle")
      .style("font-size","11px").style("fill","#A8A29E").text(h===0?"midnight":h+"h");
  }});

  // Annotate the single "safe" hour
  const safeD=clock.find(d=>d.sensitivity<0.1);
  if(safeD){{
    const ha=(safeD.hour/24+0.5/24)*2*Math.PI-Math.PI/2;
    const rl=maxR+38;
    g.append("text").attr("x",rl*Math.cos(ha)).attr("y",rl*Math.sin(ha))
      .attr("text-anchor","middle").attr("dominant-baseline","middle")
      .style("font-size","9px").style("font-weight","600").style("fill","#1B7A45").text("safe ✓");
  }}

  // Centre stats
  g.append("text").attr("text-anchor","middle").attr("y",-22)
    .style("font-size","28px").style("font-family","'Playfair Display',serif")
    .style("fill","#991B1B").style("font-weight","700").text(overallS+"%");
  g.append("text").attr("text-anchor","middle").attr("y",-3)
    .style("font-size","10px").style("fill","#78716C").text("of hours flip on");
  g.append("text").attr("text-anchor","middle").attr("y",12)
    .style("font-size","10px").style("fill","#78716C").text("a ±10 €/MWh shift");
  g.append("line").attr("x1",-28).attr("x2",28).attr("y1",22).attr("y2",22)
    .attr("stroke","#E5E0D8").attr("stroke-width",1);
  g.append("text").attr("text-anchor","middle").attr("y",36)
    .style("font-size","13px").style("font-family","'Playfair Display',serif")
    .style("fill","#D4540A").style("font-weight","700").text(`€${{avgImpact}} avg`);
  g.append("text").attr("text-anchor","middle").attr("y",50)
    .style("font-size","9px").style("fill","#A8A29E").text("revenue at risk / hour");

  // Colour legend
  const lgG=svg.append("g").attr("transform",`translate(${{cx-44}},${{S-13}})`);
  const ld=svg.append("defs").append("linearGradient").attr("id","ck-g").attr("x1","0%").attr("x2","100%");
  [["0%","#C9E8D4"],["50%","#F59E0B"],["100%","#991B1B"]].forEach(([o,c])=>
    ld.append("stop").attr("offset",o).attr("stop-color",c));
  lgG.append("rect").attr("width",88).attr("height",6).attr("rx",3).attr("fill","url(#ck-g)");
  lgG.append("text").attr("y",17).style("font-size","8px").style("fill","#A8A29E").text("safe");
  lgG.append("text").attr("x",88).attr("y",17).attr("text-anchor","end")
    .style("font-size","8px").style("fill","#A8A29E").text("highly sensitive");
}})();

// ════════════════════════════════════════════════════════════════════
// CHART 5 · SCATTER  (MAE vs dispatch revenue, per test day)
// ════════════════════════════════════════════════════════════════════
(function drawScatter(){{
  const W=Math.min($("scatter-chart").clientWidth||480,480);
  const H=Math.round(W*0.78);
  const m={{t:20,r:32,b:52,l:66}};
  const iW=W-m.l-m.r, iH=H-m.t-m.b;
  const svg=d3.select("#scatter-chart").append("svg").attr("width",W).attr("height",H);
  const g=svg.append("g").attr("transform",`translate(${{m.l}},${{m.t}})`);

  const xs=scatter.map(d=>d.mae), ys=scatter.map(d=>d.revenue);
  const x=d3.scaleLinear().domain([0,d3.max(xs)*1.06]).nice().range([0,iW]);
  const y=d3.scaleLinear().domain([d3.min(ys)*1.12,d3.max(ys)*1.12]).nice().range([iH,0]);
  const {{slope,intercept,r,p}}=ols;

  // Zero-revenue reference line (profitable vs loss days)
  if(d3.min(ys)<0){{
    g.append("line").attr("x1",0).attr("x2",iW).attr("y1",y(0)).attr("y2",y(0))
      .attr("stroke","#D6D0C8").attr("stroke-width",1).attr("stroke-dasharray","3,3");
    g.append("text").attr("x",iW+4).attr("y",y(0)+4)
      .style("font-size","9px").style("fill","#B0A89E").text("€0");
  }}

  // OLS trend line
  const x1=0, x2=d3.max(xs)*1.04;
  g.append("line").attr("x1",x(x1)).attr("y1",y(slope*x1+intercept))
    .attr("x2",x(x2)).attr("y2",y(slope*x2+intercept))
    .attr("stroke","#D4540A").attr("stroke-width",1.6).attr("opacity",.5)
    .attr("stroke-dasharray","5,3");

  // Annotation badge for OLS stats
  const ax=x(x1)+6, ay=y(slope*x1+intercept)-(y(0)-y(d3.max(ys)*0.55));
  g.append("rect").attr("x",ax-4).attr("y",ay-14).attr("width",116).attr("height",30)
    .attr("rx",5).attr("fill","rgba(255,255,255,.9)").attr("stroke","#E5E0D8");
  g.append("text").attr("x",ax+2).attr("y",ay-2)
    .style("font-size","10px").style("fill","#D4540A").style("font-weight","600")
    .text(`r = ${{r}}   p = ${{p<0.01?"< 0.01":p}}`);
  g.append("text").attr("x",ax+2).attr("y",ay+12)
    .style("font-size","9px").style("fill","#78716C").text("lower MAE → higher revenue");

  // Dots — green = profitable day, red = loss day, size ∝ |revenue|
  const rScale=d3.scaleSqrt().domain([0,d3.max(ys.map(Math.abs))]).range([3.5,8]);
  g.selectAll("circle").data(scatter).join("circle")
    .attr("cx",d=>x(d.mae)).attr("cy",d=>y(d.revenue))
    .attr("r",d=>rScale(Math.abs(d.revenue)))
    .attr("fill",d=>d.revenue>=0?"#1B7A45":"#991B1B")
    .attr("opacity",.72).attr("stroke","#fff").attr("stroke-width",.8)
    .on("mousemove",(ev,d)=>showTip(ev,d.date,`MAE: <b>${{d.mae}} €/MWh</b><br>Revenue: <b>${{fmtE(d.revenue)}}</b>`))
    .on("mouseleave",hideTip);

  // Axes — numbers only on ticks; unit in title
  g.append("g").attr("transform",`translate(0,${{iH}})`)
    .call(d3.axisBottom(x).ticks(5).tickFormat(d=>d))
    .call(g=>g.select(".domain").remove())
    .call(g=>g.selectAll("text").style("font-size","10px").style("fill","#A8A29E"));
  g.append("g").call(d3.axisLeft(y).ticks(5).tickFormat(fmtE))
    .call(g=>g.select(".domain").remove())
    .call(g=>g.selectAll("text").style("font-size","10px").style("fill","#A8A29E"));

  // Axis titles
  g.append("text").attr("x",iW/2).attr("y",iH+40)
    .attr("text-anchor","middle").style("font-size","11px").style("fill","#A8A29E")
    .text("Forecast MAE (€/MWh)");
  svg.append("text").attr("transform",`translate(12,${{m.t+iH/2}}) rotate(-90)`)
    .attr("text-anchor","middle").style("font-size","11px").style("fill","#A8A29E")
    .text("Daily revenue (€)");

  // Legend
  const legG=svg.append("g").attr("transform",`translate(${{m.l+4}},${{m.t+4}})`);
  [["#1B7A45","Profitable day"],["#991B1B","Loss day"]].forEach(([c,lbl],i)=>{{
    legG.append("circle").attr("cx",5).attr("cy",i*16).attr("r",4).attr("fill",c).attr("opacity",.75);
    legG.append("text").attr("x",13).attr("y",i*16+4)
      .style("font-size","9px").style("fill","#78716C").text(lbl);
  }});
}})();

// ════════════════════════════════════════════════════════════════════
// SPO TABLE
// ════════════════════════════════════════════════════════════════════
(function(){{
  const tb=$("spo-table"), oracleRev=spo.find(d=>d.model==="Oracle").revenue;
  tb.innerHTML=`<tr><th>Model</th><th>MAE</th><th>Revenue</th><th>% of Oracle</th><th style="width:70px"></th></tr>`
    +spo.map(d=>`<tr class="${{d.model==="Standard XGBoost"?"hl":""}}">
      <td>${{d.model}}</td>
      <td>${{d.mae===0?"—":d.mae+" €/MWh"}}</td>
      <td>${{fmtE(d.revenue)}}</td>
      <td>${{d.pct.toFixed(1)}}%</td>
      <td><div class="spo-bar" style="width:${{d.pct}}%"></div></td>
    </tr>`).join("");
}})();

// ════════════════════════════════════════════════════════════════════
// ════════════════════════════════════════════════════════════════════
// ML FEATURE EXPORT
// ════════════════════════════════════════════════════════════════════
(function initFeatures(){{
  if (!features || !features.length) return;

  const maxImp = features[0].pct;
  const cats = ["All", ...new Set(features.map(f=>f.category))];

  // Populate count badge and toggle label
  $("feat-count").textContent = features.length + " features";
  $("feat-toggle-label").textContent = "Show all " + features.length + " features";

  // Category tabs
  const tabsEl = $("feat-tabs");
  cats.forEach(cat => {{
    const btn = document.createElement("button");
    btn.className = "ftab" + (cat==="All"?" on":"");
    btn.textContent = cat;
    btn.dataset.cat = cat;
    btn.addEventListener("click", () => {{
      tabsEl.querySelectorAll(".ftab").forEach(b=>b.classList.toggle("on", b===btn));
      renderRows(cat);
    }});
    tabsEl.appendChild(btn);
  }});

  // Category colour helper
  function catClass(c){{
    if(c==="Temporal")      return "cat-Temporal";
    if(c==="Price History") return "cat-Price";
    if(c==="Supply-Demand") return "cat-Supply";
    if(c==="Generation Mix")return "cat-Generation";
    return "";
  }}
  function catShort(c){{
    if(c==="Price History") return "Price Hist.";
    if(c==="Supply-Demand") return "Supply / Demand";
    if(c==="Generation Mix")return "Generation";
    return c;
  }}

  // Render rows
  function renderRows(cat){{
    const list = cat==="All" ? features : features.filter(f=>f.category===cat);
    $("feat-rows").innerHTML = list.map(f=>`
      <div class="feat-row">
        <div class="feat-name">${{f.name}}</div>
        <div class="feat-cat"><span class="${{catClass(f.category)}}">${{catShort(f.category)}}</span></div>
        <div class="feat-src">${{f.source}}</div>
        <div class="feat-desc">${{f.description}}</div>
        <div class="feat-bar-wrap">
          <div class="feat-bar-bg">
            <div class="feat-bar" style="width:${{Math.round(f.pct/maxImp*100)}}%"></div>
          </div>
          <span class="feat-pct">${{f.pct}}%</span>
        </div>
      </div>`).join("");
  }}
  renderRows("All");

  // Toggle open/close
  const toggle = $("feat-toggle");
  const body   = $("feat-body");
  toggle.addEventListener("click", () => {{
    const open = toggle.classList.contains("open");
    toggle.classList.toggle("open", !open);
    $("feat-toggle-label").textContent = open
      ? "Show all " + features.length + " features"
      : "Hide features";
    body.style.display = open ? "none" : "block";
  }});
}})();

// ════════════════════════════════════════════════════════════════════
// HERO COUNTERS + SCROLL
// ════════════════════════════════════════════════════════════════════
function animCount(el,end,dur){{
  const s=performance.now();
  (function step(now){{
    const t=Math.min((now-s)/dur,1);
    const ease=t<.5?2*t*t:-1+(4-2*t)*t;
    el.textContent="€"+fmt(Math.round(ease*end));
    if(t<1)requestAnimationFrame(step);
  }})(performance.now());
}}

// Fade-in on scroll
document.querySelectorAll(".fade").forEach(el=>{{
  new IntersectionObserver(([e])=>{{
    if(e.isIntersecting) el.classList.add("in");
  }},{{threshold:0.1}}).observe(el);
}});

// Nav dot highlight + hero counter trigger
document.querySelectorAll("section").forEach((s,i)=>{{
  new IntersectionObserver(([e])=>{{
    if(!e.isIntersecting) return;
    document.querySelectorAll(".dot").forEach(d=>d.classList.remove("on"));
    const dot=document.querySelectorAll(".dot")[i];
    if(dot) dot.classList.add("on");
    if(s.id==="hero"){{
      setTimeout(()=>{{
        animCount($("h-oracle"),stats.oracle,1600);
        animCount($("h-naive"),stats.naive,1600);
        animCount($("h-gap"),stats.gap,1800);
      }},200);
    }}
  }},{{threshold:.35}}).observe(s);
}});

document.querySelectorAll(".dot").forEach((d,i)=>{{
  d.addEventListener("click",()=>document.querySelectorAll("section")[i].scrollIntoView({{behavior:"smooth"}}));
}});
</script>
</body>
</html>"""


def main():
    print("Loading pipeline outputs...")
    payload = build_payload()
    s = payload["stats"]
    print(f"  Oracle: €{s['oracle']:,}  |  Naive: €{s['naive']:,}  |  Gap: €{s['gap']:,}")
    data_json = json.dumps(payload, separators=(",", ":"))
    OUT_HTML.write_text(html(data_json), encoding="utf-8")
    kb = OUT_HTML.stat().st_size // 1024
    print(f"\n✓  Generated: {OUT_HTML}  ({kb} KB)")
    print("   Open track1.html in any browser — no server required.")


if __name__ == "__main__":
    main()

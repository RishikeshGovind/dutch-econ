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
section{{min-height:100vh;display:flex;flex-direction:column;justify-content:center;padding:80px 64px;max-width:1160px;margin:0 auto;position:relative}}
section+section{{border-top:1px solid var(--border)}}
.eyebrow{{font-size:10px;font-weight:600;letter-spacing:.18em;text-transform:uppercase;color:var(--orange);margin-bottom:10px}}
h1{{font-family:'Playfair Display',serif;font-size:clamp(32px,4vw,56px);line-height:1.15;margin-bottom:18px}}
h2{{font-family:'Playfair Display',serif;font-size:clamp(26px,3vw,40px);line-height:1.2;margin-bottom:14px}}
.lead{{font-size:16px;color:var(--muted);max-width:580px;margin-bottom:36px;font-weight:300}}

/* Hero */
#hero{{min-height:100vh;padding-top:120px}}
#hero h1 em{{font-style:italic;color:var(--orange)}}
.hero-line{{width:40px;height:3px;background:var(--orange);margin:20px 0 32px}}
.hero-stats{{display:flex;gap:48px;flex-wrap:wrap;margin-bottom:52px}}
.stat .num{{font-family:'Playfair Display',serif;font-size:clamp(38px,5vw,64px);font-weight:700;line-height:1;color:var(--orange)}}
.stat .num.blue{{color:var(--blue)}}.stat .num.green{{color:var(--green)}}
.stat .lbl{{font-size:11px;color:var(--muted);margin-top:5px;text-transform:uppercase;letter-spacing:.1em}}

/* Insight */
.insight{{display:inline-flex;gap:14px;align-items:flex-start;background:var(--surface);border-left:3px solid var(--orange);padding:14px 20px;border-radius:0 8px 8px 0;margin-top:24px;max-width:620px}}
.insight-icon{{font-size:18px;flex-shrink:0;margin-top:1px}}
.insight-text{{font-size:13px;color:var(--muted);line-height:1.6}}
.insight-text strong{{display:block;color:var(--text);margin-bottom:3px;font-size:11px;text-transform:uppercase;letter-spacing:.08em}}

/* Simulation section */
#sim-controls{{display:flex;align-items:center;gap:14px;margin-bottom:18px;flex-wrap:wrap}}
#sim-play-btn{{
  background:var(--orange);color:#fff;border:none;border-radius:6px;
  padding:8px 20px;font-size:13px;font-weight:500;cursor:pointer;
  font-family:'Inter',sans-serif;letter-spacing:.02em;transition:background .2s;min-width:90px
}}
#sim-play-btn:hover{{background:#B84508}}
#sim-slider{{flex:1;min-width:160px;accent-color:var(--orange);height:4px;cursor:pointer}}
.sim-time{{font-family:'Playfair Display',serif;font-size:22px;color:var(--text);min-width:54px}}
.sim-stat-row{{display:flex;gap:0;flex-wrap:wrap;margin-top:16px;border:1px solid var(--border);border-radius:10px;overflow:hidden;background:var(--surface)}}
.sim-stat{{flex:1;min-width:140px;padding:14px 20px;border-right:1px solid var(--border)}}
.sim-stat:last-child{{border-right:none}}
.sim-stat .sv{{font-family:'Playfair Display',serif;font-size:22px;font-weight:700;color:var(--text);line-height:1.2;transition:color .3s}}
.sim-stat .sl{{font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:var(--subtle);margin-top:4px}}
.soc-track{{height:5px;background:var(--border);border-radius:3px;overflow:hidden;margin-bottom:6px;width:100%}}
#sim-soc-bar{{height:100%;background:var(--blue);border-radius:3px;transition:width .5s ease}}
#sim-status{{transition:color .3s}}

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
</style>
</head>
<body>

<div id="sidenav">
  <div class="dot on"  data-i="0" title="Overview"></div>
  <div class="dot"     data-i="1" title="Simulation"></div>
  <div class="dot"     data-i="2" title="Price Calendar"></div>
  <div class="dot"     data-i="3" title="Dispatch Portrait"></div>
  <div class="dot"     data-i="4" title="Revenue Race"></div>
  <div class="dot"     data-i="5" title="Decision Sensitivity"></div>
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
  <div class="eyebrow fade">Live Simulation</div>
  <h2 class="fade">Watch the Battery Work</h2>
  <p class="lead fade">Each circle is an energy packet. Watch them migrate from the grid into the battery
  during cheap or negative-price hours — then flow out into the market at peak prices.
  Scrub the timeline or hit play to animate a full day.</p>

  <div class="fade">
    <div id="sim-controls">
      <button id="sim-play-btn">▶ Play</button>
      <input type="range" id="sim-slider" min="0" max="23" value="0" step="1">
      <span class="sim-time" id="sim-hour-disp">00:00</span>
    </div>
    <div class="chart-wrap"><div id="sim-svg-wrap"></div></div>
    <div class="sim-stat-row">
      <div class="sim-stat">
        <div class="sv" id="sim-price">—</div>
        <div class="sl">Price (€/MWh)</div>
      </div>
      <div class="sim-stat">
        <div class="sv" id="sim-status" style="font-size:15px;padding-top:4px">—</div>
        <div class="sl">Battery action</div>
      </div>
      <div class="sim-stat" style="min-width:180px">
        <div class="soc-track"><div id="sim-soc-bar"></div></div>
        <div class="sv" id="sim-soc" style="font-size:16px;margin-top:4px">—</div>
        <div class="sl">State of charge</div>
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

<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
const DATA = {data_json};
const {{heatmap,dispatch,revenue,clock,scatter,spo,ols,stats}} = DATA;
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
// SIMULATION — D3 Force Particle System
// ════════════════════════════════════════════════════════════════════
(function initSim(){{
  const simDay = dispatch.slice(0,24);   // first 24 h of data
  const W = Math.min($("sim-svg-wrap").clientWidth||920, 920);
  const H = 340;
  const PAD = 16;
  const iW = W - PAD*2;

  // Three zone centres (x only; y is always centred)
  const ZX = [iW*0.16, iW*0.5, iW*0.84];
  const ZY = H*0.5;
  const ZW = iW/3;

  const N_E = 44;   // energy dots (move between zones)
  const N_BG = 28;  // static background dots (always in zone 0)
  const R = 5.5;    // dot radius

  const initBatt = Math.round(simDay[0].soc / 2 * N_E);

  // Build dot array
  const dots = [];
  for (let i=0; i<N_E+N_BG; i++) {{
    const isBg = i >= N_E;
    const zone = (!isBg && i < initBatt) ? 1 : 0;
    dots.push({{
      id:i, bg:isBg, zone,
      flying:false,           // true while flying off-screen to "sold"
      x: ZX[zone]+(Math.random()-.5)*90,
      y: ZY+(Math.random()-.5)*110,
      vx:0, vy:0
    }});
  }}

  // SVG
  const svg = d3.select("#sim-svg-wrap").append("svg")
    .attr("width",W).attr("height",H);
  const g = svg.append("g").attr("transform",`translate(${{PAD}},0)`);

  // Zone backgrounds
  const zoneBg  = ["#F2EDE5","#E8EEF6","#E8F2EA"];
  const zoneLbl = [["GRID","SOURCE"],["BATTERY","STORAGE"],["SOLD","GRID"]];
  for (let z=0;z<3;z++) {{
    g.append("rect")
      .attr("x",z*ZW+4).attr("y",8)
      .attr("width",ZW-8).attr("height",H-16)
      .attr("rx",14).attr("fill",zoneBg[z]).attr("opacity",.82);
    zoneLbl[z].forEach((line,li)=>
      g.append("text").attr("x",ZX[z]).attr("y",28+li*14)
       .attr("text-anchor","middle")
       .style("font-size","9.5px").style("font-weight","600")
       .style("fill","#B0A89E").style("letter-spacing","0.12em").text(line));
  }}

  // Flow arrows (shown during charge/discharge)
  const arr01 = g.append("text").attr("x",(ZX[0]+ZX[1])/2).attr("y",ZY+5)
    .attr("text-anchor","middle").style("font-size","22px").style("opacity",0)
    .style("fill","#8EAEBF").text("→");
  const arr12 = g.append("text").attr("x",(ZX[1]+ZX[2])/2).attr("y",ZY+5)
    .attr("text-anchor","middle").style("font-size","22px").style("opacity",0)
    .style("fill","#D4540A").text("→");

  // Dot elements
  const dotColor = d => {{
    if (d.bg)      return "#C4B9AD";
    if (d.flying)  return "#D4540A";
    if (d.zone===1) return "#1B5E96";
    if (d.zone===2) return "#1B7A45";
    return "#8EAEBF";
  }};
  const dotOp = d => d.bg ? 0.28 : d.flying ? 0.85 : 0.9;

  const circles = g.selectAll("circle.d").data(dots).join("circle")
    .attr("class","d").attr("r",R)
    .attr("fill", dotColor).attr("opacity", dotOp).attr("stroke","none");

  // Force targets
  const tx = d => d.flying ? iW+120 : ZX[d.zone];
  const ty = ()  => ZY;

  const sim = d3.forceSimulation(dots)
    .force("x", d3.forceX(tx).strength(d => d.flying?0.38:0.07))
    .force("y", d3.forceY(ty).strength(0.065))
    .force("collide", d3.forceCollide(R+1.6).strength(0.88))
    .force("charge", d3.forceManyBody().strength(-1.2))
    .alphaDecay(0.015)
    .on("tick", () => {{
      circles
        .attr("cx", d=>d.x).attr("cy", d=>d.y)
        .attr("fill", dotColor)
        .attr("opacity", d => {{
          if (d.bg)     return 0.25;
          if (d.flying) return Math.max(0, 1-(d.x-iW*0.68)/(iW*0.32));
          return 0.9;
        }});

      // Recycle dots that flew off-screen back to source zone
      dots.forEach(d=>{{
        if (d.flying && d.x > iW+60) {{
          d.flying=false; d.zone=0;
          d.x=ZX[0]+(Math.random()-.5)*80;
          d.y=ZY+(Math.random()-.5)*100;
        }}
      }});
    }});

  let curH=0, cumRev=0, playing=false, timer=null;

  function updateForces(){{
    sim.force("x", d3.forceX(tx).strength(d=>d.flying?0.38:0.07));
  }}

  function jump(h){{
    // Reset dots to hour-0 initial state, then fast-forward
    dots.forEach(d=>{{d.flying=false;d.zone=0;}});
    let b=0;
    dots.filter(d=>!d.bg).forEach(d=>{{ if(b<initBatt){{d.zone=1;b++;}} }});
    cumRev=0;

    for (let i=1;i<=h;i++) {{
      const D=simDay[i];
      const target=Math.round(D.soc/2*N_E);
      const eDots=dots.filter(d=>!d.bg&&!d.flying);
      const inBatt=eDots.filter(d=>d.zone===1).length;
      const delta=target-inBatt;
      if (delta>0) {{
        let mv=0;
        eDots.forEach(d=>{{if(d.zone===0&&mv<delta){{d.zone=1;mv++;}}}});
      }} else if (delta<0) {{
        let mv=0;
        eDots.forEach(d=>{{if(d.zone===1&&mv<-delta){{
          d.zone=2;
          cumRev+=Math.max(0,D.price)*(2/N_E);
          mv++;
        }}}});
      }}
    }}
    // Scatter dots into their zones
    dots.forEach(d=>{{
      const z=d.zone;
      d.x=ZX[z]+(Math.random()-.5)*80; d.y=ZY+(Math.random()-.5)*100;
    }});
    updateForces();
    sim.alpha(0.55).restart();
    refreshUI(h);
    curH=h;
  }}

  function stepHour(h){{
    const D=simDay[h];
    const target=Math.round(D.soc/2*N_E);
    const eDots=dots.filter(d=>!d.bg&&!d.flying);
    const inBatt=eDots.filter(d=>d.zone===1).length;
    const delta=target-inBatt;

    arr01.style("opacity",0); arr12.style("opacity",0);

    if (delta>0){{
      let mv=0;
      eDots.forEach(d=>{{if(d.zone===0&&mv<delta){{d.zone=1;mv++;}}}});
      arr01.style("opacity",.55);
    }} else if(delta<0){{
      let mv=0;
      eDots.forEach(d=>{{if(d.zone===1&&mv<-delta){{
        d.zone=2; d.flying=true;
        cumRev+=Math.max(0,D.price)*(2/N_E);
        mv++;
      }}}});
      arr12.style("opacity",.55);
    }}

    updateForces();
    sim.alpha(0.45).restart();
    refreshUI(h);
    curH=h;

    setTimeout(()=>{{arr01.style("opacity",0);arr12.style("opacity",0);}}, 700);
  }}

  function refreshUI(h){{
    const D=simDay[h];
    const realBatt=dots.filter(d=>!d.bg&&!d.flying&&d.zone===1).length;
    const socPct=Math.round(realBatt/N_E*100);
    const status=D.charge>0.1?"⚡ Charging":D.discharge>0.1?"💰 Discharging":"— Idle";
    const priceStr=(D.price>0?"+":"")+D.price.toFixed(0)+" €/MWh";

    $("sim-price").textContent=priceStr;
    $("sim-price").style.color=D.price<0?"#6D28D9":D.price>100?"#D4540A":"var(--text)";
    $("sim-status").textContent=status;
    $("sim-status").style.color=D.charge>0.1?"#1B5E96":D.discharge>0.1?"#D4540A":"var(--muted)";
    $("sim-soc").textContent=(realBatt/N_E*2).toFixed(1)+" MWh ("+socPct+"%)";
    $("sim-soc-bar").style.width=socPct+"%";
    $("sim-revenue").textContent=fmtE(Math.round(cumRev));
    $("sim-hour-disp").textContent=String(h).padStart(2,"0")+":00";
    $("sim-slider").value=h;
  }}

  // Controls
  const SPEED=950;
  function advance(){{
    if(!playing) return;
    stepHour(curH);
    if(curH>=23){{
      playing=false;
      $("sim-play-btn").textContent="↺ Replay";
      $("sim-play-btn").dataset.mode="replay";
      return;
    }}
    curH++;
    timer=setTimeout(advance,SPEED);
  }}

  $("sim-play-btn").addEventListener("click",function(){{
    if(this.dataset.mode==="replay"){{
      this.dataset.mode=""; playing=true;
      this.textContent="⏸ Pause";
      curH=0; jump(0); setTimeout(advance,400);
    }} else {{
      playing=!playing;
      this.textContent=playing?"⏸ Pause":"▶ Play";
      if(playing) advance();
      else if(timer){{clearTimeout(timer);timer=null;}}
    }}
  }});

  $("sim-slider").addEventListener("input",function(){{
    playing=false; if(timer){{clearTimeout(timer);timer=null;}}
    $("sim-play-btn").textContent="▶ Play";
    $("sim-play-btn").dataset.mode="";
    jump(parseInt(this.value));
  }});

  // Auto-start after a short delay
  setTimeout(()=>{{
    playing=true; $("sim-play-btn").textContent="⏸ Pause"; advance();
  }},900);
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
// CHART 4 · DECISION CLOCK
// ════════════════════════════════════════════════════════════════════
(function drawClock(){{
  const S=330, cx=S/2, cy=S/2;
  const maxR=S/2-28, minR=S/2-100;
  const overallS=(clock.reduce((a,d)=>a+d.sensitivity,0)/clock.length*100).toFixed(1);
  const svg=d3.select("#clock-chart").append("svg").attr("width",S).attr("height",S);
  const g=svg.append("g").attr("transform",`translate(${{cx}},${{cy}})`);
  [.25,.5,.75,1].forEach(f=>
    g.append("circle").attr("r",minR+(maxR-minR)*f)
     .attr("fill","none").attr("stroke","#E5E0D8").attr("stroke-width",.8));
  const arc=d3.arc()
    .innerRadius(minR).outerRadius(d=>minR+(maxR-minR)*d.sensitivity)
    .startAngle(d=>(d.hour/24)*2*Math.PI-Math.PI/2)
    .endAngle(d=>((d.hour+1)/24)*2*Math.PI-Math.PI/2)
    .padAngle(.025).cornerRadius(3);
  const clr=d3.scaleSequential(d3.interpolateYlOrRd).domain([0,1]);
  g.selectAll("path.seg").data(clock).join("path").attr("class","seg")
    .attr("d",arc).attr("fill",d=>clr(d.sensitivity)).attr("opacity",.88)
    .on("mousemove",(ev,d)=>showTip(ev,`${{d.hour}}:00–${{d.hour+1}}:00`,
      `Flip rate: <b>${{(d.sensitivity*100).toFixed(0)}}%</b><br>Avg impact: ${{fmtE(d.impact)}}`))
    .on("mouseleave",hideTip);
  d3.range(0,24,3).forEach(h=>{{
    const angle=(h/24)*2*Math.PI-Math.PI/2;
    const r=maxR+16;
    g.append("text").attr("x",r*Math.cos(angle)).attr("y",r*Math.sin(angle))
      .attr("text-anchor","middle").attr("dominant-baseline","middle")
      .style("font-size","11px").style("fill","#A8A29E").text(h+"h");
  }});
  g.append("text").attr("text-anchor","middle").attr("y",-9)
   .style("font-size","26px").style("font-family","'Playfair Display',serif")
   .style("fill","#D4540A").style("font-weight","700").text(overallS+"%");
  g.append("text").attr("text-anchor","middle").attr("y",12)
   .style("font-size","10px").style("fill","#78716C").text("of hours sensitive");
}})();

// ════════════════════════════════════════════════════════════════════
// CHART 5 · SCATTER
// ════════════════════════════════════════════════════════════════════
(function drawScatter(){{
  const m={{t:16,r:24,b:48,l:60}};
  const S=320, iW=S-m.l-m.r, iH=S-m.t-m.b;
  const svg=d3.select("#scatter-chart").append("svg").attr("width",S).attr("height",S);
  const g=svg.append("g").attr("transform",`translate(${{m.l}},${{m.t}})`);
  const xs=scatter.map(d=>d.mae), ys=scatter.map(d=>d.revenue);
  const x=d3.scaleLinear().domain(d3.extent(xs)).nice().range([0,iW]);
  const y=d3.scaleLinear().domain(d3.extent(ys)).nice().range([iH,0]);
  const {{slope,intercept,r,p}}=ols;
  const x1=d3.min(xs), x2=d3.max(xs);
  g.append("line").attr("x1",x(x1)).attr("y1",y(slope*x1+intercept))
    .attr("x2",x(x2)).attr("y2",y(slope*x2+intercept))
    .attr("stroke","#D4540A").attr("stroke-width",1.8).attr("opacity",.6).attr("stroke-dasharray","5,3");
  g.append("text").attr("x",x(x1)+4).attr("y",y(slope*x1+intercept)-8)
    .style("font-size","10px").style("fill","#D4540A").text(`r = ${{r}}, p = ${{p}}`);
  const dc=d3.scaleSequential(d3.interpolateRdYlGn).domain([d3.max(xs),d3.min(xs)]);
  g.selectAll("circle").data(scatter).join("circle")
    .attr("cx",d=>x(d.mae)).attr("cy",d=>y(d.revenue)).attr("r",5)
    .attr("fill",d=>dc(d.mae)).attr("opacity",.82).attr("stroke","#fff").attr("stroke-width",.8)
    .on("mousemove",(ev,d)=>showTip(ev,d.date,`MAE: <b>${{d.mae}} €/MWh</b><br>Revenue: <b>${{fmtE(d.revenue)}}</b>`))
    .on("mouseleave",hideTip);
  g.append("g").attr("transform",`translate(0,${{iH}})`)
    .call(d3.axisBottom(x).ticks(5).tickFormat(d=>d+" €/MWh"))
    .call(g=>g.select(".domain").remove()).call(g=>g.selectAll("text").style("font-size","10px").style("fill","#A8A29E"));
  g.append("g").call(d3.axisLeft(y).ticks(5).tickFormat(fmtE))
    .call(g=>g.select(".domain").remove()).call(g=>g.selectAll("text").style("font-size","10px").style("fill","#A8A29E"));
  g.append("text").attr("x",iW/2).attr("y",iH+38)
    .attr("text-anchor","middle").style("font-size","11px").style("fill","#A8A29E").text("Forecast MAE (€/MWh)");
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

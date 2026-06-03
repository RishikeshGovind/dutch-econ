#!/usr/bin/env python3
"""
build_track1.py — Generates track1.html, a self-contained visual essay on
the Track 1 Predict-Then-Optimize battery dispatch pipeline.

Inspired by FlowingData / The Pudding: each chart answers one question,
annotations tell the story, and everything is interactable.

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

# ── Data processing ──────────────────────────────────────────────────────────

def check_files():
    needed = ["price_predictions.csv", "battery_results.csv",
              "decision_sensitivity.csv", "spo_comparison.csv"]
    missing = [f for f in needed if not (DATA_DIR / f).exists()]
    if missing:
        print(f"Missing pipeline outputs: {missing}")
        print("Run: python price_forecast.py && python battery_optimize.py && python spo_train.py")
        sys.exit(1)


def heatmap_data(preds):
    preds = preds.copy()
    preds["datetime_utc"] = pd.to_datetime(preds["datetime_utc"], utc=True)
    preds["date"] = preds["datetime_utc"].dt.strftime("%Y-%m-%d")
    preds["hour"] = preds["datetime_utc"].dt.hour
    return [
        {"date": r["date"], "hour": int(r["hour"]), "price": round(float(r["actual"]), 1)}
        for _, r in preds.head(14 * 24).iterrows()
    ]


def dispatch_data(results):
    results = results.copy()
    results["datetime_utc"] = pd.to_datetime(results["datetime_utc"])
    return [
        {
            "dt": r["datetime_utc"].strftime("%Y-%m-%dT%H:00"),
            "price": round(float(r["price_actual"]), 1),
            "charge": round(float(r["charge_oracle_mw"]), 3),
            "discharge": round(float(r["discharge_oracle_mw"]), 3),
            "soc": round(float(r["soc_oracle_mwh"]), 3),
        }
        for _, r in results.head(72).iterrows()
    ]


def revenue_data(results):
    out, cum_o, cum_n = [], 0.0, 0.0
    for i, (day, g) in enumerate(results.groupby("date")):
        o = float(np.sum(g["price_actual"] * (g["discharge_oracle_mw"] - g["charge_oracle_mw"])))
        n = float(np.sum(g["price_actual"] * (g["discharge_naive_mw"] - g["charge_naive_mw"])))
        cum_o += o; cum_n += n
        out.append({"day": i + 1, "date": str(day),
                    "oracle": round(cum_o, 0), "naive": round(cum_n, 0)})
    return out


def clock_data(sensitivity):
    h = sensitivity.groupby("hour").agg(
        sensitivity=("sensitivity_score", "mean"),
        impact=("max_revenue_impact", "mean"),
    ).reset_index()
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
    xs, ys = np.array([d["mae"] for d in sc]), np.array([d["revenue"] for d in sc])
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
            "oracle": int(oracle_total),
            "naive":  int(naive_total),
            "gap":    int(oracle_total - naive_total),
            "gap_pct": round((oracle_total - naive_total) / oracle_total * 100, 1) if oracle_total else 0,
            "sens_pct": round(sens["sensitivity_score"].mean() * 100, 1),
            "mae":    round(float(np.mean(np.abs(preds["actual"] - preds["forecast"]))), 1),
        },
    }


# ── HTML template ─────────────────────────────────────────────────────────────

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
  --bg:#F7F4EE; --surface:#FBF9F5; --border:#E5E0D8;
  --text:#1C1917; --muted:#78716C; --subtle:#A8A29E;
  --orange:#D4540A; --blue:#1B5E96; --green:#1B7A45;
  --purple:#6D28D9; --red:#9B1C1C;
  --gap:24px;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth}}
body{{background:var(--bg);color:var(--text);font-family:'Inter',-apple-system,sans-serif;font-size:15px;line-height:1.6;overflow-x:hidden}}

/* ── Navigation ── */
#sidenav{{position:fixed;right:22px;top:50%;transform:translateY(-50%);z-index:300;display:flex;flex-direction:column;gap:9px}}
.dot{{width:7px;height:7px;border-radius:50%;background:var(--border);cursor:pointer;transition:all .25s}}
.dot.on{{background:var(--orange);transform:scale(1.4)}}

/* ── Sections ── */
section{{min-height:100vh;display:flex;flex-direction:column;justify-content:center;
  padding:80px 64px;max-width:1160px;margin:0 auto;position:relative}}
section+section{{border-top:1px solid var(--border)}}

.eyebrow{{font-size:10px;font-weight:600;letter-spacing:.18em;text-transform:uppercase;
  color:var(--orange);margin-bottom:10px}}
h1{{font-family:'Playfair Display',serif;font-size:clamp(32px,4vw,56px);
  line-height:1.15;margin-bottom:18px}}
h2{{font-family:'Playfair Display',serif;font-size:clamp(26px,3vw,40px);
  line-height:1.2;margin-bottom:14px}}
.lead{{font-size:16px;color:var(--muted);max-width:580px;margin-bottom:36px;font-weight:300}}

/* ── Hero stats ── */
.hero-stats{{display:flex;gap:48px;flex-wrap:wrap;margin-bottom:52px}}
.stat .num{{font-family:'Playfair Display',serif;font-size:clamp(38px,5vw,64px);
  font-weight:700;line-height:1;color:var(--orange)}}
.stat .num.blue{{color:var(--blue)}}
.stat .num.green{{color:var(--green)}}
.stat .lbl{{font-size:11px;color:var(--muted);margin-top:5px;text-transform:uppercase;letter-spacing:.1em}}

/* ── Chart wraps ── */
.chart-wrap{{width:100%;overflow-x:auto}}
.chart-row{{display:grid;grid-template-columns:1fr 1fr;gap:56px;align-items:start}}

/* ── Insight callout ── */
.insight{{display:inline-flex;gap:14px;align-items:flex-start;
  background:var(--surface);border-left:3px solid var(--orange);
  padding:14px 20px;border-radius:0 8px 8px 0;margin-top:24px;max-width:600px}}
.insight-icon{{font-size:18px;flex-shrink:0;margin-top:1px}}
.insight-text{{font-size:13px;color:var(--muted);line-height:1.6}}
.insight-text strong{{display:block;color:var(--text);margin-bottom:3px;font-size:12px;
  text-transform:uppercase;letter-spacing:.08em}}

/* ── Tooltip ── */
#tip{{position:fixed;background:#fff;border:1px solid var(--border);
  border-radius:8px;padding:10px 14px;font-size:12.5px;pointer-events:none;
  opacity:0;transition:opacity .15s;z-index:999;
  box-shadow:0 4px 16px rgba(0,0,0,.09);max-width:200px;line-height:1.5}}
#tip .tip-label{{font-weight:600;margin-bottom:4px;color:var(--text)}}
#tip .tip-val{{color:var(--muted)}}

/* ── Legend pill ── */
.legend{{display:flex;gap:18px;flex-wrap:wrap;margin-top:14px;margin-bottom:4px}}
.legend-item{{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--muted)}}
.legend-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0}}
.legend-rect{{width:20px;height:10px;border-radius:2px;flex-shrink:0}}

/* ── Fade animations ── */
.fade{{opacity:0;transform:translateY(28px);transition:opacity .65s ease,transform .65s ease}}
.fade.in{{opacity:1;transform:none}}
.fade.delay-1{{transition-delay:.12s}}
.fade.delay-2{{transition-delay:.24s}}

/* ── Hero flourish ── */
#hero{{min-height:100vh;padding-top:120px}}
#hero h1 em{{font-style:italic;color:var(--orange)}}
.hero-line{{width:40px;height:3px;background:var(--orange);margin:20px 0 32px}}

/* ── SPO table ── */
.spo-table{{width:100%;border-collapse:collapse;font-size:13.5px;margin-top:8px}}
.spo-table th{{font-size:10px;letter-spacing:.12em;text-transform:uppercase;
  color:var(--subtle);font-weight:500;padding:0 12px 10px 0;border-bottom:1px solid var(--border);
  text-align:left}}
.spo-table td{{padding:11px 12px 11px 0;border-bottom:1px solid var(--border);vertical-align:middle}}
.spo-table tr.highlight td{{color:var(--text);font-weight:500}}
.spo-bar{{height:6px;border-radius:3px;background:var(--orange);opacity:.8}}

svg text{{font-family:'Inter',-apple-system,sans-serif}}
</style>
</head>
<body>

<div id="sidenav">
  <div class="dot on" data-target="hero"    title="Overview"></div>
  <div class="dot"    data-target="heatmap" title="Price Calendar"></div>
  <div class="dot"    data-target="dispatch" title="Dispatch Portrait"></div>
  <div class="dot"    data-target="revenue"  title="Revenue Race"></div>
  <div class="dot"    data-target="explain"  title="Decision Sensitivity"></div>
</div>
<div id="tip"><div class="tip-label"></div><div class="tip-val"></div></div>

<!-- ════════════════════════════════════════════════════════ HERO -->
<section id="hero">
  <div class="eyebrow fade">Track 1 · Predict-Then-Optimize</div>
  <h1 class="fade delay-1">Between <em>Oracle</em> and Reality:<br>A 60-Day Energy Storage Experiment</h1>
  <div class="hero-line fade delay-1"></div>
  <p class="lead fade delay-2">
    A 1 MW / 2 MWh battery charges from the Dutch day-ahead electricity market when prices are low
    and discharges when they peak. The only problem — prices must be forecast 24 hours ahead.
    How much does forecast error cost?
  </p>
  <div class="hero-stats">
    <div class="stat fade"><div class="num green" id="h-oracle">0</div><div class="lbl">Oracle revenue (€) — perfect foresight</div></div>
    <div class="stat fade delay-1"><div class="num blue" id="h-naive">0</div><div class="lbl">Naive P-T-O revenue (€) — XGBoost forecast</div></div>
    <div class="stat fade delay-2"><div class="num" id="h-gap">0</div><div class="lbl">Decision quality gap (€) — lost to forecast error</div></div>
  </div>
  <div class="insight fade delay-2">
    <span class="insight-icon">↓</span>
    <div class="insight-text">
      <strong>The Research Question</strong>
      Minimising forecast MSE is not the same as maximising dispatch profit.
      The five charts below trace exactly where and why this gap opens — and motivate
      decision-focused learning (SPO+) as the remedy.
    </div>
  </div>
</section>

<!-- ════════════════════════════════════════════════════════ HEATMAP -->
<section id="heatmap">
  <div class="eyebrow fade">Chart 1 of 5</div>
  <h2 class="fade">What the Market Looks Like</h2>
  <p class="lead fade">
    Netherlands day-ahead prices across 14 test days and 24 hours.
    Each cell is one hour. <span style="color:var(--purple);font-weight:500">Purple = negative prices</span>
    (renewables flood the grid) and <span style="color:var(--orange);font-weight:500">deep orange = scarcity peaks</span>.
    These are the signals the battery must read — one day ahead.
  </p>
  <div class="chart-wrap fade"><div id="heatmap-chart"></div></div>
  <div class="insight fade">
    <span class="insight-icon">⚡</span>
    <div class="insight-text">
      <strong>Why this matters for the LP</strong>
      Negative price hours (purple) are golden: charge then, get paid to consume electricity.
      The battery's entire profit depends on forecasting these relative rankings correctly.
    </div>
  </div>
</section>

<!-- ════════════════════════════════════════════════════════ DISPATCH -->
<section id="dispatch">
  <div class="eyebrow fade">Chart 2 of 5</div>
  <h2 class="fade">Charge Low, Sell High</h2>
  <p class="lead fade">
    72 hours of oracle dispatch decisions. The battery charges during cheap or negative-price
    periods (blue, below zero) and discharges at peaks (orange, above zero).
    The state of charge (grey line) governs what's physically possible.
  </p>
  <div class="chart-wrap fade"><div id="dispatch-chart"></div></div>
  <div class="legend fade">
    <div class="legend-item"><div class="legend-rect" style="background:var(--orange);opacity:.75"></div>Discharge — selling into grid</div>
    <div class="legend-item"><div class="legend-rect" style="background:var(--blue);opacity:.75"></div>Charge — buying from grid</div>
    <div class="legend-item"><div class="legend-rect" style="background:#999;opacity:.5;height:3px;margin-top:3px"></div>State of charge (MWh)</div>
  </div>
</section>

<!-- ════════════════════════════════════════════════════════ REVENUE -->
<section id="revenue">
  <div class="eyebrow fade">Chart 3 of 5</div>
  <h2 class="fade">The Growing Gap</h2>
  <p class="lead fade">
    Cumulative revenue over 60 test days. The oracle (dashed) represents the upper bound of what
    is physically achievable. Every missed negative-price hour and misjudged peak compounds the loss.
  </p>
  <div class="chart-wrap fade"><div id="revenue-chart"></div></div>
  <div class="insight fade">
    <span class="insight-icon">📉</span>
    <div class="insight-text">
      <strong>The compounding effect</strong>
      The gap does not grow uniformly — it spikes on high-volatility days where price spikes
      were missed or negative prices were forecast as positive.
      These are exactly the days SPO+ is designed to target.
    </div>
  </div>
</section>

<!-- ════════════════════════════════════════════════════════ EXPLAIN -->
<section id="explain">
  <div class="eyebrow fade">Charts 4 & 5 of 5</div>
  <h2 class="fade">When Forecast Errors Matter</h2>
  <p class="lead fade">
    Not all forecast errors are equal. A 10 €/MWh error at 3 am changes nothing;
    the same error at 6 pm can flip the charge/discharge decision entirely.
  </p>
  <div class="chart-row">
    <div>
      <p style="font-size:13px;color:var(--muted);margin-bottom:16px" class="fade">
        <strong style="color:var(--text)">Decision sensitivity clock</strong><br>
        Arc radius = probability that a ±10 €/MWh forecast shift flips the dispatch decision.
        Colour = average price at that hour.
      </p>
      <div class="fade"><div id="clock-chart"></div></div>
    </div>
    <div>
      <p style="font-size:13px;color:var(--muted);margin-bottom:16px" class="fade">
        <strong style="color:var(--text)">Lower MAE → Higher revenue</strong><br>
        Each point is one test day. The OLS trend confirms the core thesis: forecast accuracy
        and decision quality move together.
      </p>
      <div class="fade"><div id="scatter-chart"></div></div>
      <div class="fade" style="margin-top:28px">
        <p style="font-size:12px;color:var(--subtle);margin-bottom:10px;text-transform:uppercase;letter-spacing:.1em;font-weight:500">Model comparison · 60-day dispatch revenue</p>
        <table class="spo-table" id="spo-table"></table>
      </div>
    </div>
  </div>
  <div class="insight fade" style="margin-top:40px">
    <span class="insight-icon">🎯</span>
    <div class="insight-text">
      <strong>The SPO+ research agenda</strong>
      Standard XGBoost minimises MSE uniformly across all hours.
      Smart Predict-Then-Optimize (Elmachtoub & Grigas, 2022) trains the model to minimise
      <em>decision regret</em> — concentrating accuracy precisely at the sensitive hours shown in the clock.
    </div>
  </div>
</section>

<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
const DATA = {data_json};
const {{heatmap, dispatch, revenue, clock, scatter, spo, ols, stats}} = DATA;

// ── Tooltip ──────────────────────────────────────────────────────────────────
const tip = document.getElementById("tip");
function showTip(event, label, val) {{
  tip.querySelector(".tip-label").textContent = label;
  tip.querySelector(".tip-val").innerHTML = val;
  tip.style.opacity = 1;
  moveTip(event);
}}
function moveTip(event) {{
  const {{clientX:x, clientY:y}} = event;
  const tw = tip.offsetWidth, th = tip.offsetHeight;
  tip.style.left = (x + 14 > window.innerWidth - tw - 8 ? x - tw - 14 : x + 14) + "px";
  tip.style.top  = (y - th / 2 < 4 ? 4 : y - th / 2) + "px";
}}
function hideTip() {{ tip.style.opacity = 0; }}

// ── Colour helpers ────────────────────────────────────────────────────────────
const priceColor = d3.scaleLinear()
  .domain([-60, 0, 50, 120, 175])
  .range(["#6D28D9","#F7F4EE","#FCD34D","#D4540A","#7F1D1D"])
  .clamp(true);

const fmt = d3.format(",.0f");
const fmtE = v => "€" + fmt(v);

// ── 1 · PRICE HEATMAP ────────────────────────────────────────────────────────
(function drawHeatmap() {{
  const dates = [...new Set(heatmap.map(d => d.date))].sort();
  const W0 = Math.min(document.querySelector("#heatmap-chart").clientWidth || 900, 960);
  const cellW = Math.floor((W0 - 90) / 24);
  const cellH = Math.max(22, Math.floor(Math.min(42, (460 - 50) / dates.length)));
  const margin = {{top:30,right:20,bottom:44,left:86}};
  const W = cellW * 24 + margin.left + margin.right;
  const H = cellH * dates.length + margin.top + margin.bottom;

  const svg = d3.select("#heatmap-chart").append("svg")
    .attr("width", W).attr("height", H);
  const g = svg.append("g").attr("transform", `translate(${{margin.left}},${{margin.top}})`);

  const xBand = d3.scaleBand().domain(d3.range(24)).range([0, cellW*24]).padding(0.06);
  const yBand = d3.scaleBand().domain(dates).range([0, cellH*dates.length]).padding(0.06);

  g.selectAll("rect.cell").data(heatmap).join("rect")
    .attr("class","cell")
    .attr("x", d => xBand(d.hour)).attr("y", d => yBand(d.date))
    .attr("width", xBand.bandwidth()).attr("height", yBand.bandwidth())
    .attr("fill", d => priceColor(d.price))
    .attr("rx", 2)
    .on("mousemove", (ev,d) => showTip(ev, `${{d.date}} · ${{d.hour}}:00h`,
      `<span style="color:${{priceColor(d.price)}};font-weight:600">${{d.price > 0 ? "+" : ""}}${{d.price}} €/MWh</span>`))
    .on("mouseleave", hideTip);

  // X axis — hours
  const xAx = d3.axisBottom(xBand).tickValues(d3.range(0,24,3)).tickFormat(h => h+"h").tickSize(4);
  g.append("g").attr("transform",`translate(0,${{cellH*dates.length+4}})`).call(xAx)
    .call(g => g.select(".domain").remove())
    .call(g => g.selectAll("text").style("font-size","11px").style("fill","#78716C"));

  // Y axis — dates
  const yAx = d3.axisLeft(yBand).tickFormat(d => {{
    const dt = new Date(d+"T00:00:00");
    return d3.timeFormat("%d %b")(dt);
  }}).tickSize(0);
  g.append("g").attr("transform","translate(-8,0)").call(yAx)
    .call(g => g.select(".domain").remove())
    .call(g => g.selectAll("text").style("font-size","11px").style("fill","#78716C"));

  // Colour legend
  const lgW = 200, lgH = 10;
  const lg = svg.append("g").attr("transform", `translate(${{margin.left}},${{H-12}})`);
  const defs = svg.append("defs");
  const grad = defs.append("linearGradient").attr("id","hm-grad").attr("x1","0%").attr("x2","100%");
  [[-60,"#6D28D9"],[0,"#F7F4EE"],[50,"#FCD34D"],[120,"#D4540A"],[175,"#7F1D1D"]].forEach(([v,c]) => {{
    grad.append("stop").attr("offset", `${{(v+60)/235*100}}%`).attr("stop-color",c);
  }});
  lg.append("rect").attr("width",lgW).attr("height",lgH).attr("rx",3).attr("fill","url(#hm-grad)");
  ["−60","0","","120","175+"].forEach((t,i) => {{
    const x = lgW/4*i;
    lg.append("text").attr("x",x).attr("y",lgH+13).style("font-size","9px").style("fill","#A8A29E").text(t+" €/MWh");
  }});
}})();

// ── 2 · DISPATCH PORTRAIT ────────────────────────────────────────────────────
(function drawDispatch() {{
  const margin = {{top:16,right:24,bottom:44,left:48}};
  const W0 = Math.min(document.querySelector("#dispatch-chart").clientWidth || 920, 960);
  const W = W0, H = 340;
  const iW = W - margin.left - margin.right;
  const iH = H - margin.top - margin.bottom;

  const svg = d3.select("#dispatch-chart").append("svg").attr("width",W).attr("height",H);
  const g = svg.append("g").attr("transform",`translate(${{margin.left}},${{margin.top}})`);

  const times = dispatch.map(d => new Date(d.dt));
  const x = d3.scaleTime().domain(d3.extent(times)).range([0,iW]);
  const midY = iH * 0.54;  // zero line
  const yPrice = d3.scaleLinear()
    .domain([d3.min(dispatch,d=>d.price)*1.05, d3.max(dispatch,d=>d.price)*1.1])
    .range([iH, 0]).clamp(true);
  const barScale = midY / 1.05;   // MW 0→1 maps to this many px
  const socScale = d3.scaleLinear().domain([0,2]).range([12, 0]);

  // Background price bands (subtle colour behind chart)
  const bw = iW / dispatch.length;
  g.selectAll("rect.pbg").data(dispatch).join("rect")
    .attr("x", (_,i)=>i*bw).attr("y",0).attr("width",bw).attr("height",iH)
    .attr("fill", d => priceColor(d.price)).attr("opacity",.13);

  // Zero line
  g.append("line").attr("x1",0).attr("x2",iW).attr("y1",midY).attr("y2",midY)
    .attr("stroke","#C7C0B8").attr("stroke-width",1);

  // Discharge bars (above midY)
  g.selectAll("rect.dis").data(dispatch).join("rect")
    .attr("class","dis")
    .attr("x", (_,i)=>i*bw+1).attr("width",bw-2)
    .attr("y", d => midY - d.discharge*barScale)
    .attr("height", d => d.discharge*barScale)
    .attr("fill","#D4540A").attr("opacity",.75).attr("rx",1)
    .on("mousemove",(ev,d)=>showTip(ev,`${{d.dt.slice(0,13)}}h`,
      `Discharge: <b>${{d.discharge.toFixed(2)}} MW</b><br>Price: ${{d.price}} €/MWh`))
    .on("mouseleave",hideTip);

  // Charge bars (below midY)
  g.selectAll("rect.chg").data(dispatch).join("rect")
    .attr("class","chg")
    .attr("x",(_,i)=>i*bw+1).attr("width",bw-2)
    .attr("y", midY).attr("height", d => d.charge*barScale)
    .attr("fill","#1B5E96").attr("opacity",.75).attr("rx",1)
    .on("mousemove",(ev,d)=>showTip(ev,`${{d.dt.slice(0,13)}}h`,
      `Charge: <b>${{d.charge.toFixed(2)}} MW</b><br>Price: ${{d.price}} €/MWh`))
    .on("mouseleave",hideTip);

  // SOC line
  const socLine = d3.line()
    .x((_,i)=>i*bw+bw/2)
    .y(d => midY - socScale(d.soc)*barScale - d.discharge*barScale - 2)
    .curve(d3.curveMonotoneX);
  g.append("path").datum(dispatch).attr("d",socLine)
    .attr("fill","none").attr("stroke","#999").attr("stroke-width",1.5)
    .attr("stroke-dasharray","4,3").attr("opacity",.7);

  // Price line
  const priceLine = d3.line()
    .x((_,i)=>i*bw+bw/2).y(d=>yPrice(d.price)).curve(d3.curveMonotoneX);
  g.append("path").datum(dispatch).attr("d",priceLine)
    .attr("fill","none").attr("stroke","#1C1917").attr("stroke-width",1.4).attr("opacity",.35);

  // Midnight guide lines
  dispatch.forEach((d,i)=>{{ if(d.dt.endsWith("T00:00")) {{
    g.append("line").attr("x1",i*bw).attr("x2",i*bw)
     .attr("y1",0).attr("y2",iH).attr("stroke","#C7C0B8").attr("stroke-width",0.8).attr("stroke-dasharray","3,3");
    g.append("text").attr("x",i*bw+4).attr("y",12)
     .style("font-size","10px").style("fill","#A8A29E")
     .text(new Date(d.dt).toLocaleDateString("en-GB",{{day:"numeric",month:"short"}}));
  }}}});

  // Y axis
  const yAx = d3.axisLeft(d3.scaleLinear().domain([-1,1]).range([midY+barScale,midY-barScale]))
    .ticks(3).tickFormat(d=>Math.abs(d)+" MW");
  g.append("g").call(yAx).call(g=>g.select(".domain").remove())
    .call(g=>g.selectAll("text").style("font-size","10px").style("fill","#A8A29E"));

  // Labels
  g.append("text").attr("x",iW).attr("y",midY-barScale*0.5)
    .attr("text-anchor","end").style("font-size","10px").style("fill","#D4540A").text("discharge ↑");
  g.append("text").attr("x",iW).attr("y",midY+barScale*0.5)
    .attr("text-anchor","end").style("font-size","10px").style("fill","#1B5E96").text("charge ↓");
}})();

// ── 3 · REVENUE RACE ─────────────────────────────────────────────────────────
(function drawRevenue() {{
  const margin = {{top:20,right:80,bottom:44,left:68}};
  const W0 = Math.min(document.querySelector("#revenue-chart").clientWidth || 920, 960);
  const W = W0, H = 320;
  const iW = W-margin.left-margin.right, iH = H-margin.top-margin.bottom;

  const svg = d3.select("#revenue-chart").append("svg").attr("width",W).attr("height",H);
  const g = svg.append("g").attr("transform",`translate(${{margin.left}},${{margin.top}})`);

  const allVals = revenue.flatMap(d=>[d.oracle,d.naive]);
  const x = d3.scaleLinear().domain([1,revenue.length]).range([0,iW]);
  const y = d3.scaleLinear().domain([Math.min(0,d3.min(allVals))-500, d3.max(allVals)*1.05]).range([iH,0]);

  // Gap area
  const gapArea = d3.area()
    .x(d=>x(d.day)).y0(d=>y(d.naive)).y1(d=>y(d.oracle)).curve(d3.curveMonotoneX);
  const defs = svg.append("defs");
  const gapGrad = defs.append("linearGradient").attr("id","gap-grad").attr("x1","0%").attr("x2","100%");
  gapGrad.append("stop").attr("offset","0%").attr("stop-color","#D4540A").attr("stop-opacity",.06);
  gapGrad.append("stop").attr("offset","100%").attr("stop-color","#D4540A").attr("stop-opacity",.18);
  g.append("path").datum(revenue).attr("d",gapArea).attr("fill","url(#gap-grad)");

  // Oracle line
  const oLine = d3.line().x(d=>x(d.day)).y(d=>y(d.oracle)).curve(d3.curveMonotoneX);
  g.append("path").datum(revenue).attr("d",oLine)
    .attr("fill","none").attr("stroke","#1B7A45").attr("stroke-width",1.5)
    .attr("stroke-dasharray","5,4").attr("opacity",.7);

  // Naive line
  const nLine = d3.line().x(d=>x(d.day)).y(d=>y(d.naive)).curve(d3.curveMonotoneX);
  g.append("path").datum(revenue).attr("d",nLine)
    .attr("fill","none").attr("stroke","#1B5E96").attr("stroke-width",2.2);

  // Hover scrubber
  const scrub = g.append("line").attr("y1",0).attr("y2",iH)
    .attr("stroke","#C7C0B8").attr("stroke-width",1).attr("opacity",0);
  const bisect = d3.bisector(d=>d.day).left;
  svg.on("mousemove", ev => {{
    const [mx] = d3.pointer(ev, g.node());
    const day = Math.round(x.invert(mx));
    const idx = Math.max(0,Math.min(bisect(revenue, day),revenue.length-1));
    const d = revenue[idx];
    scrub.attr("x1",x(d.day)).attr("x2",x(d.day)).attr("opacity",.6);
    showTip(ev,`Day ${{d.day}} · ${{d.date}}`,
      `Oracle: <b>${{fmtE(d.oracle)}}</b><br>Naive: <b>${{fmtE(d.naive)}}</b><br>Gap: ${{fmtE(d.oracle-d.naive)}}`);
  }}).on("mouseleave", ()=>{{ scrub.attr("opacity",0); hideTip(); }});

  // Axes
  g.append("g").attr("transform",`translate(0,${{iH}})`).call(d3.axisBottom(x).ticks(10).tickFormat(d=>`Day ${{d}}`))
    .call(g=>g.select(".domain").remove()).call(g=>g.selectAll("text").style("font-size","10px").style("fill","#A8A29E"));
  g.append("g").call(d3.axisLeft(y).ticks(5).tickFormat(fmtE))
    .call(g=>g.select(".domain").remove()).call(g=>g.selectAll("text").style("font-size","10px").style("fill","#A8A29E"));

  // End labels
  const last = revenue[revenue.length-1];
  g.append("text").attr("x",iW+6).attr("y",y(last.oracle))
    .attr("dominant-baseline","middle").style("font-size","11px").style("fill","#1B7A45").text("Oracle");
  g.append("text").attr("x",iW+6).attr("y",y(last.naive))
    .attr("dominant-baseline","middle").style("font-size","11px").style("fill","#1B5E96").text("Naive");

  // Gap annotation
  const midDay = Math.floor(revenue.length*0.75);
  const md = revenue[midDay];
  g.append("text").attr("x",x(md.day)).attr("y",(y(md.oracle)+y(md.naive))/2)
    .attr("text-anchor","middle").attr("dominant-baseline","middle")
    .style("font-size","11px").style("fill","#D4540A").style("font-style","italic")
    .text(`${{fmtE(md.oracle-md.naive)}} gap`);
}})();

// ── 4 · DECISION CLOCK ───────────────────────────────────────────────────────
(function drawClock() {{
  const S = 340;
  const cx = S/2, cy = S/2;
  const maxR = S/2 - 28, minR = S/2 - 100;
  const overallSens = (clock.reduce((a,d)=>a+d.sensitivity,0)/clock.length*100).toFixed(1);

  const svg = d3.select("#clock-chart").append("svg").attr("width",S).attr("height",S);
  const g = svg.append("g").attr("transform",`translate(${{cx}},${{cy}})`);

  // Grid circles
  [0.25,0.5,0.75,1].forEach(f => {{
    g.append("circle").attr("r",minR+(maxR-minR)*f)
     .attr("fill","none").attr("stroke","#E5E0D8").attr("stroke-width",.8);
  }});

  // Arcs
  const arc = d3.arc()
    .innerRadius(minR)
    .outerRadius(d => minR + (maxR-minR)*d.sensitivity)
    .startAngle(d => (d.hour/24)*2*Math.PI - Math.PI/2)
    .endAngle(d => ((d.hour+1)/24)*2*Math.PI - Math.PI/2)
    .padAngle(0.025).cornerRadius(3);

  const clr = d3.scaleSequential(d3.interpolateYlOrRd).domain([0,1]);

  g.selectAll("path.seg").data(clock).join("path")
    .attr("class","seg").attr("d",arc)
    .attr("fill", d => clr(d.sensitivity))
    .attr("opacity",.88)
    .on("mousemove",(ev,d)=>showTip(ev,`${{d.hour}}:00 – ${{d.hour+1}}:00`,
      `Flip rate: <b>${{(d.sensitivity*100).toFixed(0)}}%</b><br>Avg impact: ${{fmtE(d.impact)}}`))
    .on("mouseleave",hideTip);

  // Hour labels (every 3h)
  d3.range(0,24,3).forEach(h => {{
    const angle = (h/24)*2*Math.PI - Math.PI/2;
    const r = maxR + 16;
    g.append("text")
     .attr("x", r*Math.cos(angle)).attr("y", r*Math.sin(angle))
     .attr("text-anchor","middle").attr("dominant-baseline","middle")
     .style("font-size","11px").style("fill","#A8A29E")
     .text(h+"h");
  }});

  // Centre label
  g.append("text").attr("text-anchor","middle").attr("y",-9)
   .style("font-size","26px").style("font-family","'Playfair Display',serif")
   .style("fill","#D4540A").style("font-weight","700").text(overallSens+"%");
  g.append("text").attr("text-anchor","middle").attr("y",12)
   .style("font-size","10px").style("fill","#78716C").text("of hours sensitive");
}})();

// ── 5 · SCATTER ──────────────────────────────────────────────────────────────
(function drawScatter() {{
  const margin = {{top:16,right:24,bottom:48,left:60}};
  const S = 320;
  const iW = S-margin.left-margin.right, iH = S-margin.top-margin.bottom;
  const svg = d3.select("#scatter-chart").append("svg").attr("width",S).attr("height",S);
  const g = svg.append("g").attr("transform",`translate(${{margin.left}},${{margin.top}})`);

  const xs = scatter.map(d=>d.mae), ys = scatter.map(d=>d.revenue);
  const x = d3.scaleLinear().domain(d3.extent(xs)).nice().range([0,iW]);
  const y = d3.scaleLinear().domain(d3.extent(ys)).nice().range([iH,0]);

  // OLS line
  const {{slope,intercept,r,p}} = ols;
  const x1 = d3.min(xs), x2 = d3.max(xs);
  g.append("line")
    .attr("x1",x(x1)).attr("y1",y(slope*x1+intercept))
    .attr("x2",x(x2)).attr("y2",y(slope*x2+intercept))
    .attr("stroke","#D4540A").attr("stroke-width",1.8).attr("opacity",.6)
    .attr("stroke-dasharray","5,3");

  // OLS annotation
  g.append("text").attr("x",x(x1)+4).attr("y",y(slope*x1+intercept)-8)
    .style("font-size","10px").style("fill","#D4540A")
    .text(`r = ${{r}}, p = ${{p}}`);

  // Dots
  const dotColor = d3.scaleSequential(d3.interpolateRdYlGn).domain([d3.max(xs),d3.min(xs)]);
  g.selectAll("circle").data(scatter).join("circle")
    .attr("cx",d=>x(d.mae)).attr("cy",d=>y(d.revenue))
    .attr("r",5).attr("fill",d=>dotColor(d.mae)).attr("opacity",.8)
    .attr("stroke","#fff").attr("stroke-width",.8)
    .on("mousemove",(ev,d)=>showTip(ev,d.date,`MAE: <b>${{d.mae}} €/MWh</b><br>Revenue: <b>${{fmtE(d.revenue)}}</b>`))
    .on("mouseleave",hideTip);

  // Axes
  g.append("g").attr("transform",`translate(0,${{iH}})`).call(d3.axisBottom(x).ticks(5).tickFormat(d=>d+" €/MWh"))
    .call(g=>g.select(".domain").remove()).call(g=>g.selectAll("text").style("font-size","10px").style("fill","#A8A29E"));
  g.append("g").call(d3.axisLeft(y).ticks(5).tickFormat(fmtE))
    .call(g=>g.select(".domain").remove()).call(g=>g.selectAll("text").style("font-size","10px").style("fill","#A8A29E"));
  g.append("text").attr("x",iW/2).attr("y",iH+38)
    .attr("text-anchor","middle").style("font-size","11px").style("fill","#A8A29E").text("Forecast MAE (€/MWh)");
}})();

// ── SPO table ────────────────────────────────────────────────────────────────
(function buildSpoTable() {{
  const tb = document.getElementById("spo-table");
  const oracle_rev = spo.find(d=>d.model==="Oracle").revenue;
  tb.innerHTML = `<tr>
    <th>Model</th><th>MAE</th><th>Revenue</th><th>% of Oracle</th><th style="width:80px"></th>
  </tr>` + spo.map(d => `<tr class="${{d.model==="Standard XGBoost"?"highlight":""}}">
    <td>${{d.model}}</td>
    <td>${{d.mae===0?"—":d.mae+" €/MWh"}}</td>
    <td>${{fmtE(d.revenue)}}</td>
    <td>${{d.pct.toFixed(1)}}%</td>
    <td><div class="spo-bar" style="width:${{d.pct}}%"></div></td>
  </tr>`).join("");
}})();

// ── Hero animated counters ────────────────────────────────────────────────────
function animCount(el, end, prefix, dur) {{
  const start = performance.now();
  function step(now) {{
    const t = Math.min((now-start)/dur, 1);
    const ease = t<.5 ? 2*t*t : -1+(4-2*t)*t;
    el.textContent = prefix + fmt(Math.round(ease*end));
    if(t<1) requestAnimationFrame(step);
  }}
  requestAnimationFrame(step);
}}

// ── Scroll + IntersectionObserver ────────────────────────────────────────────
const dots = document.querySelectorAll(".dot");
const sections = document.querySelectorAll("section");
const fadeEls = document.querySelectorAll(".fade");

const fadeObs = new IntersectionObserver(entries => {{
  entries.forEach(e => {{ if(e.isIntersecting) e.target.classList.add("in"); }});
}}, {{threshold: 0.12}});
fadeEls.forEach(el => fadeObs.observe(el));

const secObs = new IntersectionObserver(entries => {{
  entries.forEach(e => {{
    if(e.isIntersecting) {{
      dots.forEach(d=>d.classList.remove("on"));
      const idx = [...sections].indexOf(e.target);
      if(dots[idx]) dots[idx].classList.add("on");
      // Trigger hero counters
      if(e.target.id==="hero") {{
        setTimeout(()=>{{
          animCount(document.getElementById("h-oracle"), stats.oracle, "€", 1600);
          animCount(document.getElementById("h-naive"),  stats.naive,  "€", 1600);
          animCount(document.getElementById("h-gap"),    stats.gap,    "€", 1800);
        }}, 200);
      }}
    }}
  }});
}}, {{threshold: 0.35}});
sections.forEach(s => secObs.observe(s));

dots.forEach((dot, i) => {{
  dot.addEventListener("click", () => sections[i].scrollIntoView({{behavior:"smooth"}}));
}});
</script>
</body>
</html>"""


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Loading pipeline outputs...")
    payload = build_payload()

    s = payload["stats"]
    print(f"  Oracle: €{s['oracle']:,}  |  Naive: €{s['naive']:,}  |  Gap: €{s['gap']:,}")
    print(f"  Sensitivity: {s['sens_pct']}%  |  MAE: {s['mae']} €/MWh")

    data_json = json.dumps(payload, separators=(",", ":"))
    OUT_HTML.write_text(html(data_json), encoding="utf-8")
    print(f"\n✓ Generated: {OUT_HTML}")
    print("  Open track1.html in any browser — no server required.")


if __name__ == "__main__":
    main()

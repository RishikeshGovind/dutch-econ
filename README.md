# Decision-Focused Learning in Modern Operations
## PhD Application Demo · Maastricht University SBE

Interactive demo for a PhD application in Econometrics, Operations Research and Social Choice at Maastricht University (Project 1: Data-driven decision making in modern operations).

---

## The argument in one sentence

Training a machine learning model to minimise forecast error is not the same as training it to make better operational decisions. This demo proves that argument across three real industries.

---

## Entry points

| File | What it is |
|---|---|
| `index.html` | Landing page — states the thesis, explains the method, links to all three cases |
| `track1.html` | Case 1: Battery dispatch on the Dutch day-ahead electricity market |
| `track2.html` | Case 2: ICU nurse staffing at a teaching hospital |
| `track3.html` | Case 3: Last-mile parcel routing in Amsterdam |

Open `index.html` in any browser. All data is embedded in the HTML files — no server needed.

---

## What each case shows

**Case 1 — Energy (primary research fit)**
A 1 MW battery buys from the Dutch day-ahead market when prices are low and sells when they spike. Prices must be forecast 24 hours ahead using XGBoost trained on 4 years of ENTSO-E data. The LP dispatch is then compared against three variants of decision-focused training (regret-weighted, SPO+) and an oracle with perfect foresight. The uncertainty section adds 80% conformal prediction intervals (Romano, Sesia & Candès, 2019).

Key finding: SPO+ earns similar revenue to standard XGBoost in the Oct-Nov 2024 test set because 92.7% of hours are decision-sensitive — there is no specific cluster for SPO+ to target. That is the finding, not a failure. SPO+ gains depend on market structure, and measuring when and by how much it wins is the PhD research question.

**Case 2 — Hospital**
A teaching hospital forecasts ICU admissions for the next day and uses that to plan nurse staffing. Being understaffed costs about 4× more than overstaffing. Standard training treats both errors as equally bad. SPO+ (Elmachtoub & Grigas, 2022) trains on the actual cost of each mistake instead. Data calibrated on LCPS, RIVM, and NZa figures for a hospital modelled on Maastricht UMC+.

**Case 3 — Logistics**
A Dutch delivery company forecasts parcel demand by postcode zone and plans van routes. At 12 zones, the routing problem is too large for an exact solution so the planner uses heuristics (nearest-neighbour and 2-opt). This is the hardest case: unlike Cases 1 and 2, the routing heuristic cannot send feedback back to the forecast model to improve it. Extending SPO+ to this setting is the open research problem that connects all three cases.

---

## Scripts

| Script | Purpose |
|---|---|
| `entsoe_fetch.py` | Fetches Dutch day-ahead prices from ENTSO-E (basic mode) |
| `entsoe_fetch_rich.py` | Fetches full panel: prices, load, wind, solar, generation mix |
| `price_forecast.py` | Trains XGBoost price forecaster; auto-detects basic vs rich features |
| `battery_optimize.py` | Solves the 24-hour battery dispatch LP; runs decision sensitivity analysis |
| `spo_train.py` | Trains SPO+ and regret-weighted variants; compares 60-day dispatch revenue |
| `price_uncertainty.py` | Conformal quantile regression; produces 80% prediction intervals |
| `hospital_data.py` | Generates hospital dataset calibrated on LCPS, RIVM, and NZa figures |
| `build_track1.py` | Rebuilds track1.html with fresh embedded data |
| `build_track2.py` | Rebuilds track2.html with fresh embedded data |
| `build_track3.py` | Rebuilds track3.html with fresh embedded data |

---

## Data files

| File | Content |
|---|---|
| `data/nl_panel.parquet` | ENTSO-E panel: prices, load, wind, solar, generation (Jan 2021 – Nov 2024) |
| `data/price_predictions.csv` | XGBoost point forecasts for the test period (Oct-Nov 2024) |
| `data/price_intervals.csv` | CQR 80% prediction intervals for the uncertainty section |
| `data/battery_results.csv` | Oracle and naive LP dispatch results, hour by hour |
| `data/spo_comparison.csv` | Revenue: oracle, standard XGBoost, regret-weighted, SPO+ |
| `data/decision_sensitivity.csv` | Per-hour flip analysis under ±10 EUR/MWh perturbation |
| `data/shap_values.csv` | SHAP feature attributions for the price forecast model |
| `data/uncertainty_stats.json` | CQR coverage, interval width, and robust dispatch results |

---

## Running locally

```bash
pip install -r requirements.txt
```

To regenerate Case 1 data from scratch:

```bash
python entsoe_fetch_rich.py   # fetch live ENTSO-E data (requires API key in .env)
python price_forecast.py      # train the XGBoost forecaster
python battery_optimize.py    # run the LP and sensitivity analysis
python spo_train.py           # train SPO+ variants and compare revenue
python price_uncertainty.py   # run conformal quantile regression
python build_track1.py        # rebuild track1.html with embedded data
```

The `.env` file should contain `ENTSOE_TOKEN=your_api_key`. Without it, `entsoe_fetch.py` falls back to the calibrated synthetic dataset already in `data/`.

---

## Academic context

**Target position:** PhD in Quantitative Economics, Department of Quantitative Economics, School of Business and Economics, Maastricht University. Project 1 — Data-driven decision making in modern operations.

**Core method:** Smart Predict-Then-Optimize, SPO+ (Elmachtoub & Grigas, 2022, Management Science).

**Key papers:**
- Elmachtoub & Grigas (2022) — SPO+, the theoretical foundation this demo implements
- Mandi et al. (2024, JAIR) — definitive survey of decision-focused learning methods
- Sadana et al. (2024, ACM Computing Surveys) — survey of predict-then-optimize methods
- Romano, Sesia & Candès (2019, NeurIPS) — conformal quantile regression for Case 1

**Industry partners named in the PhD call:** university hospital (Case 2), last-mile logistics providers (Case 3), energy companies (Case 1). All three are covered.

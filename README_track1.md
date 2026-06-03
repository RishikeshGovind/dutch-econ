# Track 1 Demo: Predict-Then-Optimize for Dutch Battery Storage

**Target position:** Maastricht University — Department of Quantitative Economics  
**Track:** Data-Driven Decision-Making (Econometrics / Operations Research)  
**Research partners:** Energy management sector

---

## The Problem

A battery storage operator must decide each hour whether to **charge** (buy electricity) or **discharge** (sell electricity). Profit depends on buying cheap and selling dear — but prices are only known for the current period, not the future. The operator needs a price forecast to plan the schedule.

The standard approach: *Predict the price, then solve the dispatch optimization.* This is the **Predict-Then-Optimize (P-T-O)** paradigm.

The scientific gap: Minimising forecast MSE is not the same as maximising dispatch profit. A forecast that is 20 €/MWh wrong at a stable-price hour costs nothing in decision quality; the same error at a peak/trough hour can flip the entire charge/discharge decision. **This misalignment is the motivation for decision-focused learning.**

---

## Pipeline Architecture

```
ENTSO-E API / synthetic data
       ↓
data/nl_day_ahead_prices.csv       (hourly NL prices, 2022–2023)
       ↓  [price_forecast.py]
data/price_predictions.csv         (actual vs. XGBoost forecast, 60-day test set)
data/price_model.joblib
       ↓  [battery_optimize.py]
data/battery_results.csv           (hourly dispatch decisions + P&L)
       ↓  [demo_chart.py]
data/figures/price_forecast.png
data/figures/battery_dispatch.png
data/figures/value_of_better_forecast.png
```

---

## Scripts

| Script | What it does |
|--------|-------------|
| `entsoe_fetch.py` | Downloads NL day-ahead prices from ENTSO-E API (A44, zone `10YNL----------L`). Falls back to synthetic data if no API key is set. |
| `price_forecast.py` | Trains XGBoost on lag/calendar features. Reports MAE, RMSE, R² vs. naive persistence baseline. |
| `battery_optimize.py` | Solves a daily 24-hour LP with SciPy HiGHS. Compares oracle dispatch (true prices) vs. naive P-T-O (forecast prices). |
| `demo_chart.py` | Generates three publication-quality figures. |

---

## Running the Demo

### Prerequisites

```bash
pip install -r requirements.txt
```

### With real ENTSO-E data (optional)

1. Register free at <https://transparency.entsoe.eu>
2. Generate an API key under *My Account → Security Token*
3. `export ENTSOE_API_KEY=your_key_here`

### Without API key (default — fully self-contained)

The demo runs immediately with synthetic NL price data that reproduces:
- 2022 energy-crisis dynamics (elevated base ≈145 €/MWh, high volatility, price spikes)
- 2023 market normalization (≈72 €/MWh, calmer)
- Intraday shape (night valley, morning/evening peaks)
- Weekly seasonality (weekends ~20% cheaper)
- Monthly seasonality (winters expensive, summers cheap)
- Negative price events (≈3% of hours) from renewable oversupply

### Run the full pipeline

```bash
python entsoe_fetch.py       # ~instant (synthetic) or ~2 min (API)
python price_forecast.py     # ~30 seconds
python battery_optimize.py   # ~10 seconds
python demo_chart.py         # ~5 seconds
```

---

## Key Results (60-day test period)

| Metric | Value |
|--------|-------|
| XGBoost MAE vs. naive | ~15–25% reduction |
| Oracle annual revenue | ≈ upper bound |
| Naive P-T-O revenue | oracle − decision-quality gap |
| **Decision quality gap** | **the core research object** |

The figure `value_of_better_forecast.png` shows a statistically significant **negative correlation** between daily forecast MAE and realized dispatch revenue. This is the empirical motivation: lower prediction error leads to better dispatch timing and higher profit — even though the model was trained to minimise MSE, not profit.

---

## The Scientific Contribution (Track 1 Research Agenda)

### Standard P-T-O (this demo)

```
Forecast loss (MSE)   →   Trained model   →   LP optimizer   →   Dispatch decisions
```

The forecaster is blind to how errors affect the downstream optimization.

### Smart Predict-Then-Optimize — SPO+ (Elmachtoub & Grigas, 2022)

```
Decision regret       →   Trained model   →   LP optimizer   →   Better decisions
```

SPO+ defines a surrogate loss that directly measures how much profit is lost due to forecast error. Gradients of this loss flow back through the LP, teaching the model to prioritize accuracy where it matters most for dispatch.

### Extensions for the PhD

- **Non-stationary markets:** When the price distribution shifts (policy changes, new capacity), how should the forecaster adapt? Online learning, domain adaptation, regime detection.
- **Robust optimization:** Rather than point forecasts, use forecast intervals as uncertainty sets; solve robust dispatch that hedges against imbalance penalties.
- **Fleet coordination:** Multi-asset dispatch (multiple batteries + demand-response) with shared grid constraints — a much harder LP/MIP with richer predict-then-optimize interactions.
- **Real-world partner integration:** Empirical validation on operational data from energy management companies; bridging academic SPO+ theory to industry constraints.

---

## Battery Model Specification

| Parameter | Value |
|-----------|-------|
| Max charge / discharge | 1 MW |
| Usable capacity | 2 MWh |
| Round-trip efficiency | 90% (applied to charge) |
| Initial SOC | 50% (1 MWh) |
| Optimization horizon | 24 hours (daily rolling LP) |
| SOC carryover | Yes — terminal SOC feeds next day |

---

## Data Source

**ENTSO-E Transparency Platform**  
- URL: <https://transparency.entsoe.eu>  
- Document type: A44 (Day-Ahead Prices)  
- Bidding zone: `10YNL----------L` (Netherlands)  
- Period: 2022-01-01 to 2023-12-31  
- Resolution: PT60M (hourly), currency: EUR/MWh  

---

## References

1. Elmachtoub, A. N., & Grigas, P. (2022). Smart "predict, then optimize." *Management Science*, 68(1), 9–26.
2. Kotary, J., Fioretto, F., Van Hentenryck, P., & Wilder, B. (2021). End-to-end constrained optimization learning and prediction. *IJCAI-21*.
3. Morales, J. M., Conejo, A. J., Madsen, H., Pinson, P., & Zugno, M. (2014). *Integrating Renewables in Electricity Markets.* Springer.
4. Bertsimas, D., & Kallus, N. (2020). From predictive to prescriptive analytics. *Management Science*, 66(3), 1025–1044.

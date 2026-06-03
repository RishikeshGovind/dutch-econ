# AreaStat DK

Interactive research platform for exploring demographic, socioeconomic, fiscal, climate, and green transition indicators across all 98 Danish municipalities (kommuner). Built as proof-of-concept infrastructure for a PhD research proposal on municipal fiscal resilience under the green transition, submitted to Aalborg University's MaMTEP programme.

**Live:** https://rishikeshgovind.github.io/areastat-de/

**Proposal:** [`PhD_Proposal_Draft.md`](PhD_Proposal_Draft.md)

---

## What it does

Select any combination of municipalities or regions on the map, then explore across eight tabs:

| Tab | Content |
|---|---|
| **Demographics** | Age structure, population dynamics, migration, ancestry, welfare dependency |
| **Economics** | Income, employment, education, housing, vehicles, businesses |
| **Financial** | Per-capita fiscal accounts (operating expenditure, debt, capital investment, equalization grants); SFC government sector cards; debt dynamics chart; SFC flow diagram |
| **Green Transition** | Fossil-sector share, renewable capacity (wind + solar), transition vulnerability index; comparative bar charts |
| **SFC Scenario** | Prototype two-sector SFC simulation: Albertslund (high exposure) vs Lemvig (low exposure), 2024–2034; Transaction Flow Matrix; Balance Sheet Matrix; scenario projection charts |
| **Analysis** | XGBoost ML distress prediction + SHAP explanations; fiscal risk scoring; socioeconomic profiling; trend time-series |
| **ML Export** | Feature matrix download (CSV/Excel) for external modelling; pre-built panel dataset |
| **DST Explorer** | Live query of 100+ Statistics Denmark StatBank tables for selected municipalities |

---

## Research context

This platform implements all four phases of the PhD research proposal:

**Phase 1 — Data infrastructure**
- DST StatBank API pipeline: 15+ series across demographics, labour market, fiscal accounts, income, businesses
- Energistyrelsen (Stamdataregisteret): renewable energy capacity by municipality (onshore wind, solar, offshore wind)
- DMI climate API: mean temperature, summer days, annual precipitation, heating degree days by municipality
- NACE sector employment from DST RAS: fossil-linked vs green sector shares

**Phase 2 — Analytics**
- K-means clustering with climate and green transition variables included
- Transition Vulnerability Index: fossil employment share × relative debt burden
- Unemployment model reframed with sector composition features

**Phase 3 — SFC framing**
- `SFCAccounts` domain for all 98 municipalities: estimated T (tax revenue), G (operating expenditure), I (capital investment), L (debt stock), ΔL, capital stock proxy, net financial worth, climate risk scores
- `sfc_scenario` block in `data.json`: calibrated BAU and Green Transition trajectories for archetype municipalities, Transaction Flow Matrix, Balance Sheet Matrix
- SFC Scenario tab visualising debt and fiscal balance projections under three scenarios

**Phase 4 — Proposal**
- Full PhD proposal document targeting Aalborg University MaMTEP
- Theoretical grounding in Godley & Lavoie (2007) SFC, Minsky (1986), Dafermos et al. (2017) ecological SFC

---

## Architecture

| Component | Stack | Hosting |
|---|---|---|
| Frontend | Vanilla JS, MapLibre GL, Chart.js | GitHub Pages |
| R API | R Plumber — clustering, fiscal summaries, typology | HuggingFace Spaces (Docker) |
| Python API | FastAPI + XGBoost — ML distress prediction, SHAP | HuggingFace Spaces (Docker) |

---

## Data sources

| Dataset | Source |
|---|---|
| Municipal fiscal accounts | Statistics Denmark StatBank — REGNSKAB series |
| Income and employment | DST StatBank — INDKP, ERHV series |
| NACE sector employment | DST StatBank — RAS series |
| Demographic indicators | DST StatBank — BEF, FOLK series |
| Renewable energy capacity | Energistyrelsen — Stamdataregisteret |
| Climate observations | DMI — municipalityValue API |
| Municipal boundaries | DAWA — api.dataforsyningen.dk (GeoJSON) |
| Urban-rural typology | Derived from DST settlement classification |

---

## Project structure

```
.
├── index.html                       Map and municipality selection
├── profile.html                     Profile tabs, charts, SFC scenario, analysis
├── style.css                        Shared styles
├── js/
│   ├── shared.js                    API URLs, i18n helpers, shared utilities
│   ├── dst-catalogue.js             DST table catalogue for Explorer tab
│   └── dst-explorer.js              Live DST StatBank query interface
├── plumber.R                        R API entry point (clustering, fiscal endpoints)
├── fiscal_ml_api.py                 Python ML API (XGBoost distress, SHAP)
├── sfc_enrichment.py                Adds SFCAccounts + sfc_scenario to data.json
├── requirements.txt                 Python dependencies
├── Dockerfile.plumber               Docker build for R API
├── Dockerfile.python                Docker build for Python API
├── data.json                        Pre-built frontend data (all 98 municipalities)
├── PhD_Proposal_Draft.md            Full PhD research proposal (Aalborg MaMTEP)
├── data/
│   ├── final_json.rds               R data cache
│   ├── kommuner.geojson             Municipality boundaries (Denmark)
│   ├── regioner.geojson             Region boundaries (Denmark)
│   ├── panel_dataset.csv            Fiscal panel (time-series)
│   ├── dk_unemp_model.joblib        Unemployment prediction model
│   └── xgb_fiscal_model.joblib      XGBoost fiscal distress model
├── areastat-dk-r-api/               R API source (HuggingFace deployment)
│   └── plumber.R
├── areastat-dk-python-api/          Python API source (HuggingFace deployment)
│   └── fiscal_ml_api.py
└── create-js/
    ├── create_data.R                Main data build script
    ├── fetch_denmark_data.R         DST + Energistyrelsen + DMI pipeline
    ├── build_panel.R                Fiscal panel builder
    └── config.R                     R dependencies
```

---

## Running locally

### 1. Rebuild `data.json`

```r
source("create-js/create_data.R")
```

Then enrich with SFC accounts:

```bash
python3 sfc_enrichment.py
```

### 2. Start the R API

```r
plumber::plumb("plumber.R")$run(port = 8000)
```

### 3. Start the Python ML API

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn fiscal_ml_api:app --port 8001 --reload
```

### 4. Serve the frontend

Use VS Code Live Server or any local static file server. Do not open via `file://` — browser CORS restrictions will block `data.json` and API calls.

---

## API reference

### R Plumber

| Endpoint | Description |
|---|---|
| `GET /cluster_typology` | Socioeconomic k-means typology for selected municipalities |
| `GET /fiscal_profile` | Per-capita expenditure and revenue profile |
| `GET /fiscal_risk_summary` | Rule-based fiscal risk scoring |
| `GET /fiscal_clustering` | Fiscal k-means groupings |
| `GET /fiscal_timeseries` | Time-series for key fiscal metrics |
| `GET /zone_timeseries` | Indicator time-series for a single zone |

All endpoints accept `ids` as a comma-separated list of municipality codes.

### Python ML API

| Endpoint | Description |
|---|---|
| `GET /health` | Service status |
| `POST /predict_distress` | XGBoost fiscal distress probability per zone |
| `POST /shap_explain` | SHAP feature attributions (top-N drivers) |
| `POST /fiscal_forecast` | Indicative multi-year fiscal forecast |
| `GET /model_performance` | AUC-ROC, precision-recall metrics |
| `GET /feature_importance` | Global XGBoost feature importance |

---

## Key data links

- Statistics Denmark StatBank: https://www.statbank.dk
- Energistyrelsen open data: https://www.energidataservice.dk
- DMI climate API: https://www.dmi.dk/friedata/guides-til-frie-data
- DAWA municipality API: https://api.dataforsyningen.dk/kommuner

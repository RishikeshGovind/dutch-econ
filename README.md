# Maastricht Predict-Then-Optimize Demo

Interactive demo package for a Maastricht University PhD application in data-driven decision-making in operations.

The repository is now centered on one core case and two transfer cases:

- Core case: Dutch battery dispatch under day-ahead price forecasting
- Transfer case: hospital staffing under asymmetric shortage costs
- Transfer case: last-mile logistics with heuristic-enhanced routing

The main objective is to show research fit for predict-then-optimize, explainability, and decision-focused learning. The demos are prototypes: they rely on synthetic or calibrated data to illustrate the methods and the downstream optimization logic.

## Entry points

- `proposal.html`: landing page for the application demo
- `track1.html`: primary Maastricht fit, energy storage and dispatch
- `track2.html`: hospital operations transfer case
- `track3.html`: logistics transfer case
- `README_track1.md`: technical note for the energy case

## Project note

An older Aalborg / AreaStat DK draft is still present in `PhD_Proposal_Draft.md` for reference, but it is not the current application package this demo is built around.

## Running locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Serve the folder with a local static server or VS Code Live Server, then open `proposal.html` through that server. Opening files directly with `file://` can break external fetches and some browser APIs.

## Repository contents

- `entsoe_fetch.py`: fetches or synthesizes Dutch day-ahead prices
- `price_forecast.py`: trains the forecasting model for Track 1
- `battery_optimize.py`: solves the battery dispatch LP
- `hospital_data.py`: generates the hospital demo dataset
- `build_track1.py`: prepares Track 1 outputs
- `spo_train.py`: SPO-related model experimentation
- `data/`: generated CSV outputs, fitted models, and figures used by the demos

## Positioning

The package is designed to communicate three things clearly:

- Forecast quality should be judged by downstream decision quality, not only prediction error.
- The same methodological idea can transfer across energy, healthcare, and logistics.
- Track 1 is the main research fit; Tracks 2 and 3 demonstrate breadth rather than separate applications.

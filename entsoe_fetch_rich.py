#!/usr/bin/env python3
"""
entsoe_fetch_rich.py — Extended ENTSO-E Netherlands data pull
=============================================================
Pulls five time-series from the ENTSO-E REST API and merges them into
a single wide hourly panel: data/nl_panel.parquet (+ .csv copy).

Series fetched:
  A44  Day-ahead prices              (€/MWh)
  A65  Actual system load            (MW)   processType=A16
  A65  Day-ahead load forecast       (MW)   processType=A01
  A69  Wind + solar generation forecast (MW) by psrType
  A75  Actual generation per type    (MW)   processType=A16

If ENTSOE_API_KEY is not set the script falls back to a synthetic
multi-variate panel that preserves realistic NL market correlations
(price ↑ when wind ↓ + load ↑, negative prices on sunny low-load Sundays,
2022 gas-crisis base-price regime).

Usage:
    export ENTSOE_API_KEY=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    python entsoe_fetch_rich.py

    # or without a key (synthetic):
    python entsoe_fetch_rich.py
"""

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
DATA_DIR       = Path(__file__).parent / "data"
PANEL_PARQUET  = DATA_DIR / "nl_panel.parquet"
PANEL_CSV      = DATA_DIR / "nl_panel.csv"

ENTSO_BASE = "https://web-api.tp.entsoe.eu/api"
NL_ZONE    = "10YNL----------L"
START      = datetime(2021,  1,  1, tzinfo=timezone.utc)
END        = datetime(2024, 12,  1, tzinfo=timezone.utc)   # exclusive

# ENTSO-E production-type codes → friendly column names
PSR_MAP = {
    "B04": "gas",
    "B05": "hard_coal",
    "B10": "hydro_pump",
    "B11": "hydro_ror",
    "B14": "nuclear",
    "B16": "solar",
    "B17": "waste",
    "B18": "wind_offshore",
    "B19": "wind_onshore",
}


# ── XML parsing ───────────────────────────────────────────────────────────────

def _detect_ns(root_tag: str) -> str:
    return root_tag[1:root_tag.index("}")] if root_tag.startswith("{") else ""


def _parse_document(content: bytes, value_tag: str = "quantity") -> list[dict]:
    """
    Parse any ENTSO-E GL_MarketDocument or Publication_MarketDocument.
    Returns list of {ts, value, psr} dicts (psr=None if not a typed document).
    """
    root = ET.fromstring(content)
    ns   = _detect_ns(root.tag)
    p    = f"{{{ns}}}" if ns else ""

    rows = []
    for ts_el in root.findall(f".//{p}TimeSeries"):
        psr_el = ts_el.find(f"{p}MktPSRType/{p}psrType")
        psr    = psr_el.text if psr_el is not None else None

        for period in ts_el.findall(f"{p}Period"):
            start_el = period.find(f"{p}timeInterval/{p}start")
            if start_el is None:
                continue
            p_start  = datetime.fromisoformat(start_el.text.replace("Z", "+00:00"))
            res_el   = period.find(f"{p}resolution")
            res_text = res_el.text if res_el is not None else "PT60M"
            delta    = {"PT15M": timedelta(minutes=15),
                        "PT30M": timedelta(minutes=30)}.get(res_text, timedelta(hours=1))

            for pt in period.findall(f"{p}Point"):
                pos_el = pt.find(f"{p}position")
                val_el = pt.find(f"{p}{value_tag}")
                if pos_el is None or val_el is None:
                    continue
                try:
                    rows.append({
                        "ts":    p_start + (int(pos_el.text) - 1) * delta,
                        "value": float(val_el.text),
                        "psr":   psr,
                    })
                except (ValueError, TypeError):
                    pass
    return rows


def _to_hourly(rows: list[dict], name: str) -> pd.Series:
    """Aggregate raw rows to a clean hourly UTC Series."""
    if not rows:
        return pd.Series(dtype=float, name=name)
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    s = df.groupby("ts")["value"].mean()
    s = s[~s.index.duplicated(keep="first")]
    return s.resample("h").mean().rename(name)


# ── REST helpers ──────────────────────────────────────────────────────────────

def _month_ranges(start: datetime, end: datetime):
    cur = start.replace(day=1, hour=0, minute=0, second=0)
    while cur < end:
        nxt = (cur.replace(month=cur.month % 12 + 1)
               if cur.month < 12
               else cur.replace(year=cur.year + 1, month=1))
        yield cur, min(nxt, end)
        cur = nxt


def _get(api_key: str, params: dict, retries: int = 3) -> bytes | None:
    for attempt in range(retries):
        try:
            r = requests.get(
                ENTSO_BASE,
                params={"securityToken": api_key, **params},
                timeout=60,
            )
            if r.status_code == 200:
                return r.content
            if r.status_code == 429:
                time.sleep(15 * (attempt + 1))
                continue
            log.debug("HTTP %d: %s", r.status_code, r.text[:200])
            return None
        except requests.RequestException as exc:
            log.debug("Request error (attempt %d): %s", attempt + 1, exc)
            time.sleep(3)
    return None


def _ts(dt: datetime) -> str:
    return dt.strftime("%Y%m%d%H%M")


# ── Per-series fetchers ───────────────────────────────────────────────────────

def _fetch_prices(key: str) -> pd.Series:
    """A44 — day-ahead market clearing prices."""
    rows = []
    for s, e in _month_ranges(START, END):
        raw = _get(key, {"documentType": "A44",
                         "in_Domain": NL_ZONE, "out_Domain": NL_ZONE,
                         "periodStart": _ts(s), "periodEnd": _ts(e)})
        if raw:
            rows += _parse_document(raw, value_tag="price.amount")
        time.sleep(0.35)
    log.info("  prices: %d raw points", len(rows))
    return _to_hourly(rows, "price_da")


def _fetch_load(key: str, process: str, col: str) -> pd.Series:
    """A65 — actual (A16) or day-ahead-forecast (A01) system load."""
    rows = []
    for s, e in _month_ranges(START, END):
        raw = _get(key, {"documentType": "A65", "processType": process,
                         "outBiddingZone_Domain": NL_ZONE,
                         "periodStart": _ts(s), "periodEnd": _ts(e)})
        if raw:
            rows += _parse_document(raw)
        time.sleep(0.35)
    log.info("  %s: %d raw points", col, len(rows))
    return _to_hourly(rows, col)


def _fetch_typed(key: str, doc: str, process: str, suffix: str) -> pd.DataFrame:
    """A69 or A75 — documents that split series by psrType."""
    buckets: dict[str, list] = {}
    for s, e in _month_ranges(START, END):
        raw = _get(key, {"documentType": doc, "processType": process,
                         "in_Domain": NL_ZONE,
                         "periodStart": _ts(s), "periodEnd": _ts(e)})
        if raw:
            for row in _parse_document(raw):
                psr = row["psr"] or "unknown"
                buckets.setdefault(psr, []).append(row)
        time.sleep(0.35)

    frames: dict[str, pd.Series] = {}
    for psr, rows in buckets.items():
        col = f"{PSR_MAP.get(psr, psr.lower())}_{suffix}"
        frames[col] = _to_hourly(rows, col)
        log.info("  %s: %d raw points", col, len(rows))

    return pd.DataFrame(frames) if frames else pd.DataFrame()


def fetch_live(api_key: str) -> pd.DataFrame:
    """Pull all series and return merged hourly UTC panel."""
    log.info("── A44 day-ahead prices ──────────────────────────────")
    prices = _fetch_prices(api_key)

    log.info("── A65 actual load ───────────────────────────────────")
    load_act = _fetch_load(api_key, "A16", "load_actual")

    log.info("── A65 day-ahead load forecast ───────────────────────")
    load_fcst = _fetch_load(api_key, "A01", "load_forecast")

    log.info("── A69 wind + solar day-ahead forecast ───────────────")
    res_fcst = _fetch_typed(api_key, "A69", "A01", "forecast")

    log.info("── A75 actual generation mix ─────────────────────────")
    gen_act = _fetch_typed(api_key, "A75", "A16", "actual")

    df = prices.to_frame()
    for s in [load_act, load_fcst]:
        df = df.join(s, how="outer")
    for frame in [res_fcst, gen_act]:
        if not frame.empty:
            df = df.join(frame, how="outer")

    df = (df.sort_index()
            .loc[pd.Timestamp(START, tz="UTC"):pd.Timestamp(END, tz="UTC")])
    return df


# ── Synthetic fallback ────────────────────────────────────────────────────────

def generate_synthetic() -> pd.DataFrame:
    """
    Realistic synthetic NL panel preserving key market correlations:
      • Price ~ f(net_load, gas_price_regime, hour, season)
      • Negative prices on sunny + low-load windows
      • 2022 energy-crisis base regime vs 2023 normalisation
      • Wind/solar anti-correlated with price
    """
    log.info("Generating synthetic multi-variate NL panel 2021–2024 …")
    rng   = np.random.default_rng(42)
    hours = pd.date_range(START, END, freq="h", inclusive="left", tz="UTC")
    n     = len(hours)
    local = hours.tz_convert("Europe/Amsterdam")

    h   = local.hour.values
    dow = local.dayofweek.values
    mon = local.month.values - 1   # 0-indexed
    yr  = local.year.values

    # ── Load profile ──────────────────────────────────────────────────────────
    load_base   = 13_500  # MW average NL system load
    hour_load   = np.array([-0.18,-0.22,-0.23,-0.22,-0.17,-0.06,
                             0.09, 0.17, 0.16, 0.11, 0.07, 0.05,
                             0.04, 0.01, 0.03, 0.07, 0.11, 0.16,
                             0.20, 0.17, 0.12, 0.07,-0.04,-0.12])
    month_load  = np.array([ 0.14, 0.12, 0.06, 0.00,-0.04,-0.10,
                             -0.12,-0.09,-0.03, 0.00, 0.07, 0.11])
    dow_load    = np.array([ 0.06, 0.06, 0.05, 0.04, 0.02,-0.14,-0.18])
    load_actual = (load_base
                   * (1 + hour_load[h] + month_load[mon] + dow_load[dow])
                   + rng.normal(0, 300, n))
    # Day-ahead forecast ≈ actual + small noise
    load_forecast = load_actual + rng.normal(0, 150, n)

    # ── Wind ──────────────────────────────────────────────────────────────────
    # Onshore: mean ~2800 MW; offshore: growing from ~700 to ~2400 MW by end 2023
    year_frac    = (yr - 2021) / 3
    offshore_cap = 700 + year_frac * 1700   # MW installed capacity growing

    wind_shape   = 0.5 + 0.5 * np.cos(2 * np.pi * (mon - 11) / 12)   # stronger in winter
    wind_onshore_forecast = np.clip(
        rng.lognormal(np.log(np.maximum(2500 * (1 + 0.3 * wind_shape), 100)), 0.7, n),
        0, 5800)
    wind_offshore_forecast = np.clip(
        rng.lognormal(np.log(np.maximum(offshore_cap * (1 + 0.3 * wind_shape), 50)), 0.7, n),
        0, offshore_cap * 1.15)

    # actual ≈ forecast + small error
    wind_onshore_actual  = np.clip(wind_onshore_forecast  + rng.normal(0, 120, n), 0, None)
    wind_offshore_actual = np.clip(wind_offshore_forecast + rng.normal(0, 80,  n), 0, None)

    # ── Solar ─────────────────────────────────────────────────────────────────
    # Peaks in summer afternoons; NL installed ~5 GW by 2023
    solar_cap     = 3000 + year_frac * 2000
    is_daylight   = (h >= 6) & (h <= 19)
    solar_angle   = np.where(is_daylight, np.sin(np.pi * (h - 6) / 13), 0)
    summer_boost  = np.maximum(0, np.cos(2 * np.pi * (mon - 5) / 12))
    solar_forecast = np.clip(
        solar_cap * solar_angle * summer_boost * (0.7 + rng.random(n) * 0.3),
        0, solar_cap * 1.05)
    solar_actual   = np.clip(solar_forecast + rng.normal(0, 100, n), 0, None)

    # ── Nuclear (Borssele, ~485 MW, ~92% availability) ────────────────────────
    nuclear_actual = np.clip(
        485 * (rng.random(n) > 0.06).astype(float) + rng.normal(0, 15, n),
        0, 510)

    # ── Net load → merit-order gas dispatch proxy ─────────────────────────────
    net_load = load_actual - wind_onshore_actual - wind_offshore_actual - solar_actual - nuclear_actual
    gas_actual = np.clip(net_load + rng.normal(0, 200, n), 0, 14_000)

    # ── Price (merit-order model) ─────────────────────────────────────────────
    # Gas price regime: 2021~50 €/MWh fuel equivalent, 2022~160 (crisis), 2023~90, 2024~75
    gas_regime = np.where(yr == 2021, 48.0,
                 np.where(yr == 2022, 155.0,
                 np.where(yr == 2023,  88.0, 72.0)))

    # Base price = gas cost × capacity factor + scarcity premium on net load
    capacity_factor = net_load / 14_000
    price_da = (gas_regime * 0.40            # fuel cost component
                + 30 * capacity_factor        # scarcity term
                + 8  * hour_load[h]           # intraday pattern
                + rng.normal(0, 12 + 20*(yr==2022), n))  # noise (wider in crisis year)

    # Negative prices: solar + wind > load (Sunday afternoons, Q2-Q3)
    oversupply = (wind_onshore_actual + wind_offshore_actual + solar_actual) > load_actual * 0.95
    price_da   = np.where(oversupply & (rng.random(n) < 0.55),
                          rng.uniform(-60, -5, n),
                          price_da)

    # Spike events: ~15 days in 2022, ~5 in other years
    for spike_yr, n_spikes in [(2021,4),(2022,15),(2023,5),(2024,3)]:
        yr_mask = yr == spike_yr
        yr_hours = np.where(yr_mask)[0]
        if len(yr_hours) < 24:
            continue
        spike_starts = rng.choice(yr_hours[::24], size=min(n_spikes, len(yr_hours)//24), replace=False)
        for ss in spike_starts:
            price_da[ss:ss+24] *= rng.uniform(1.8, 3.5)

    price_da = price_da.clip(-100, 1000)

    # ── Assemble panel ────────────────────────────────────────────────────────
    df = pd.DataFrame({
        "price_da":               price_da.round(2),
        "load_actual":            load_actual.round(0),
        "load_forecast":          load_forecast.round(0),
        "wind_onshore_forecast":  wind_onshore_forecast.round(0),
        "wind_offshore_forecast": wind_offshore_forecast.round(0),
        "solar_forecast":         solar_forecast.round(0),
        "wind_onshore_actual":    wind_onshore_actual.round(0),
        "wind_offshore_actual":   wind_offshore_actual.round(0),
        "solar_actual":           solar_actual.round(0),
        "nuclear_actual":         nuclear_actual.round(0),
        "gas_actual":             gas_actual.round(0),
    }, index=hours)

    log.info("Synthetic panel: %d rows, price range %.1f–%.1f €/MWh",
             len(df), df["price_da"].min(), df["price_da"].max())
    return df


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    DATA_DIR.mkdir(exist_ok=True)
    api_key = os.environ.get("ENTSOE_API_KEY", "").strip()

    if api_key and api_key != "YOUR_API_KEY_HERE":
        log.info("ENTSOE_API_KEY found — fetching live ENTSO-E data …")
        try:
            df = fetch_live(api_key)
            if df.empty or "price_da" not in df.columns:
                raise ValueError("API returned empty/price-less panel")
        except Exception as exc:
            log.warning("Live fetch failed (%s) — falling back to synthetic data", exc)
            df = generate_synthetic()
    else:
        log.info("ENTSOE_API_KEY not set — generating synthetic panel")
        log.info("  (Register free at https://transparency.entsoe.eu → My Account)")
        df = generate_synthetic()

    df.to_parquet(PANEL_PARQUET)
    df.to_csv(PANEL_CSV)
    log.info("Saved %d rows × %d columns → %s", *df.shape, PANEL_PARQUET)

    print("\n=== Panel Summary ===")
    print(df.describe().round(1).to_string())
    print(f"\nColumns: {list(df.columns)}")


if __name__ == "__main__":
    main()

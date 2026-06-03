#!/usr/bin/env python3
"""
entsoe_fetch.py — Fetch Netherlands day-ahead electricity prices from ENTSO-E.

If ENTSOE_API_KEY is not set (or the API call fails), falls back to synthetic
data with realistic Dutch market patterns (2022 energy crisis + 2023 normalization).

Output: data/nl_day_ahead_prices.csv  [datetime_utc, price_eur_mwh]
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

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_CSV = DATA_DIR / "nl_day_ahead_prices.csv"

ENTSO_BASE = "https://web-api.tp.entsoe.eu/api"
BIDDING_ZONE = "10YNL----------L"
START_DATE = datetime(2022, 1, 1, tzinfo=timezone.utc)
END_DATE = datetime(2024, 1, 1, tzinfo=timezone.utc)  # exclusive

# ENTSO-E XML namespace for publication documents v7
_NS = {"ns": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:0"}


def _parse_xml(content: bytes) -> list[tuple]:
    """Return list of (datetime_utc, price_eur_mwh) from GL_MarketDocument XML."""
    root = ET.fromstring(content)
    results = []
    for ts in root.findall(".//ns:TimeSeries", _NS):
        for period in ts.findall("ns:Period", _NS):
            start_el = period.find("ns:timeInterval/ns:start", _NS)
            if start_el is None:
                continue
            p_start = datetime.fromisoformat(start_el.text.replace("Z", "+00:00"))
            res_el = period.find("ns:resolution", _NS)
            res_text = res_el.text if res_el is not None else "PT60M"
            delta = timedelta(minutes=30) if res_text == "PT30M" else timedelta(hours=1)
            for point in period.findall("ns:Point", _NS):
                pos_el = point.find("ns:position", _NS)
                price_el = point.find("ns:price.amount", _NS)
                if pos_el is None or price_el is None:
                    continue
                position = int(pos_el.text) - 1  # 1-based → 0-based
                dt = p_start + position * delta
                results.append((dt, float(price_el.text)))
    return results


def _fetch_chunk(api_key: str, start: datetime, end: datetime) -> list[tuple]:
    params = {
        "securityToken": api_key,
        "documentType": "A44",
        "in_Domain": BIDDING_ZONE,
        "out_Domain": BIDDING_ZONE,
        "periodStart": start.strftime("%Y%m%d%H%M"),
        "periodEnd": end.strftime("%Y%m%d%H%M"),
    }
    resp = requests.get(ENTSO_BASE, params=params, timeout=60)
    resp.raise_for_status()
    return _parse_xml(resp.content)


def fetch_live(api_key: str) -> pd.DataFrame:
    """Fetch 2022-2023 data in monthly chunks to stay within API limits."""
    all_rows: list[tuple] = []
    current = START_DATE
    while current < END_DATE:
        # Advance to first day of next month
        if current.month == 12:
            chunk_end = current.replace(year=current.year + 1, month=1, day=1)
        else:
            chunk_end = current.replace(month=current.month + 1, day=1)
        chunk_end = min(chunk_end, END_DATE)
        log.info("Fetching %s → %s ...", current.date(), chunk_end.date())
        try:
            rows = _fetch_chunk(api_key, current, chunk_end)
            all_rows.extend(rows)
            time.sleep(0.4)  # polite rate limiting
        except Exception as exc:
            log.warning("Chunk %s failed: %s — skipping", current.date(), exc)
        current = chunk_end

    df = pd.DataFrame(all_rows, columns=["datetime_utc", "price_eur_mwh"])
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True)
    return (
        df.drop_duplicates("datetime_utc")
        .sort_values("datetime_utc")
        .reset_index(drop=True)
    )


def generate_synthetic() -> pd.DataFrame:
    """
    Synthetic NL day-ahead prices that mimic key features:
    - 2022 energy crisis (elevated base, high volatility, frequent spikes)
    - 2023 normalization (lower base, calmer markets)
    - Intraday shape: low nights, morning/evening peaks
    - Weekly seasonality: weekends cheaper
    - Monthly seasonality: winters expensive, summers cheap
    - Occasional negative prices (~3% of hours) from renewable oversupply
    - Occasional positive spike events (demand/supply crunch, ~15 days/year in 2022)
    """
    log.info("Generating synthetic NL day-ahead prices (2022-2023)...")
    rng = np.random.default_rng(42)
    hours = pd.date_range(START_DATE, END_DATE, freq="h", inclusive="left", tz="UTC")
    n = len(hours)

    # Hourly shape relative to daily mean (24 values, index = hour-of-day)
    hour_mult = np.array([
        -0.28, -0.33, -0.36, -0.36, -0.30, -0.10,   # 00-05 deep night
         0.14,  0.26,  0.22,  0.12,  0.06,  0.04,   # 06-11 morning ramp
         0.01, -0.04,  0.01,  0.06,  0.12,  0.22,   # 12-17 midday/afternoon
         0.28,  0.24,  0.16,  0.06, -0.09, -0.20,   # 18-23 evening/decline
    ])
    # Monthly multiplier (index = month-1)
    month_mult = np.array([
        0.32, 0.26, 0.10, 0.00, -0.06, -0.18,
       -0.22, -0.18, -0.06,  0.00,  0.16,  0.26,
    ])
    # Day-of-week multiplier (Mon=0 … Sun=6)
    dow_mult = np.array([0.05, 0.05, 0.05, 0.03, 0.00, -0.16, -0.22])

    h = hours.hour.values
    m = hours.month.values - 1
    d = hours.dayofweek.values

    year_base = np.where(hours.year == 2022, 145.0, 72.0)
    price = year_base * (1.0 + hour_mult[h] + month_mult[m] + dow_mult[d])

    # Gaussian noise scaled by year
    noise_std = np.where(hours.year == 2022, 42.0, 22.0)
    price += rng.normal(0.0, noise_std, n)

    # Negative price events (~3% of hours, renewable oversupply)
    neg_mask = rng.random(n) < 0.03
    price[neg_mask] = rng.uniform(-60.0, -5.0, neg_mask.sum())

    # Positive spike events — choose ~18 random days in 2022, ~6 in 2023
    dates_2022 = pd.date_range("2022-01-01", "2022-12-31", freq="D", tz="UTC")
    dates_2023 = pd.date_range("2023-01-01", "2023-12-31", freq="D", tz="UTC")
    spike_days = list(
        rng.choice(dates_2022, size=18, replace=False)
    ) + list(
        rng.choice(dates_2023, size=6, replace=False)
    )
    for spike_day in spike_days:
        mask = (hours.date == spike_day.date())
        multiplier = rng.uniform(2.2, 3.5)
        price[mask] *= multiplier

    df = pd.DataFrame({"datetime_utc": hours, "price_eur_mwh": price.round(2)})
    log.info(
        "Synthetic data: %.1f–%.1f EUR/MWh, mean=%.1f",
        df["price_eur_mwh"].min(), df["price_eur_mwh"].max(),
        df["price_eur_mwh"].mean(),
    )
    return df


def main():
    DATA_DIR.mkdir(exist_ok=True)
    api_key = os.environ.get("ENTSOE_API_KEY", "").strip()

    if api_key:
        log.info("ENTSOE_API_KEY detected — fetching live ENTSO-E data...")
        df = fetch_live(api_key)
        if df.empty:
            log.warning("API returned no usable rows; falling back to synthetic data.")
            df = generate_synthetic()
    else:
        log.info("ENTSOE_API_KEY not set — using synthetic data (set key for real prices).")
        df = generate_synthetic()

    df.to_csv(OUTPUT_CSV, index=False)
    log.info("Saved %d hourly rows to %s", len(df), OUTPUT_CSV)
    print("\n=== Price Summary ===")
    print(df["price_eur_mwh"].describe().round(2).to_string())


if __name__ == "__main__":
    main()

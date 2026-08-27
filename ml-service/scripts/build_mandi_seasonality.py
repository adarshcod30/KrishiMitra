#!/usr/bin/env python3
"""Distil two years of Agmarknet mandi prices into seasonality baselines.

Source: Kaggle arjunyadav99/indian-agricultural-mandi-prices-20232025 (CC0),
737k daily rows for Potato, Onion, Wheat, Tomato and Rice - five of the most
traded staples. The committed artefact answers two questions the live single-day
feed cannot:

  * is today's price high or low FOR THIS TIME OF YEAR? (seasonal index)
  * what is a typical price band for this commodity in this state?

Method: within each (commodity, year) the monthly median is divided by that
year's median, and the resulting indices are averaged across years - so a
general price-level shift between 2023 and 2025 does not masquerade as
seasonality. Prices are clipped to each commodity's 1st-99th percentile first;
the raw file has a 460,000 Rs/quintal typo-row.

    python scripts/build_mandi_seasonality.py --source <csv>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "mandi_seasonality.csv.gz"
MIN_STATE_OBS = 300  # below this a state's own median is noise; use national


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    args = ap.parse_args()

    df = pd.read_csv(args.source)
    df["date"] = pd.to_datetime(df["Price Date"], format="%m/%d/%Y", errors="coerce")
    df = df.dropna(subset=["date", "Modal_Price"])
    df = df[df.Modal_Price > 0]

    # Per-commodity outlier clip (the raw file contains a 460,000 Rs row).
    def clip(group: pd.DataFrame) -> pd.DataFrame:
        lo, hi = group.Modal_Price.quantile([0.01, 0.99])
        return group[(group.Modal_Price >= lo) & (group.Modal_Price <= hi)]

    before = len(df)
    df = df.groupby("Commodity", group_keys=False)[df.columns].apply(clip)
    print(f"{before:,} rows -> {len(df):,} after 1-99% clip")

    df["month"] = df.date.dt.month
    df["year"] = df.date.dt.year

    # --- seasonal index, level-shift-proof -----------------------------------
    yearly = df.groupby(["Commodity", "year"]).Modal_Price.median().rename("year_median")
    monthly = (
        df.groupby(["Commodity", "year", "month"]).Modal_Price.median().rename("month_median")
    )
    joined = monthly.reset_index().merge(yearly.reset_index(), on=["Commodity", "year"])
    joined["index"] = joined.month_median / joined.year_median
    seasonal = (
        joined.groupby(["Commodity", "month"])
        .agg(seasonal_index=("index", "mean"), years=("index", "size"))
        .reset_index()
    )

    # --- typical bands: state where dense enough, else national --------------
    rows = []
    national = df.groupby(["Commodity", "month"]).Modal_Price
    nat = national.agg(median="median",
                       p25=lambda s: s.quantile(0.25),
                       p75=lambda s: s.quantile(0.75),
                       n_obs="size").reset_index()
    nat["state"] = "ALL"
    rows.append(nat)

    st = (
        df.groupby(["Commodity", "STATE", "month"]).Modal_Price
        .agg(median="median",
             p25=lambda s: s.quantile(0.25),
             p75=lambda s: s.quantile(0.75),
             n_obs="size")
        .reset_index()
        .rename(columns={"STATE": "state"})
    )
    st = st[st.n_obs >= MIN_STATE_OBS]
    rows.append(st)

    bands = pd.concat(rows, ignore_index=True)
    out = bands.merge(seasonal, on=["Commodity", "month"], how="left")
    out = out.rename(columns={"Commodity": "commodity"})
    for col in ("median", "p25", "p75"):
        out[col] = out[col].round(0)
    out["seasonal_index"] = out["seasonal_index"].round(3)
    out.to_csv(OUT, index=False, compression="gzip")

    print(f"wrote {len(out):,} rows -> {OUT.name} ({OUT.stat().st_size/1e3:.0f} KB)")
    print("\nSanity - onion seasonality (should peak in autumn, dip at rabi harvest):")
    o = out[(out.commodity == "Onion") & (out.state == "ALL")].sort_values("month")
    print(o[["month", "median", "seasonal_index"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

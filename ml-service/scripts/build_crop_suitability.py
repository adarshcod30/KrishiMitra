#!/usr/bin/env python3
"""Feature-engineer the APY long table into a district crop-suitability index.

Why not simply rank crops by yield? Because DES reports yield in per-crop units
- coconut is nuts/hectare, giving a median of 8,519 against wheat's 3 - so an
absolute cross-crop comparison is meaningless. Every signal below is therefore
computed WITHIN a crop, then combined:

  suitability  percentile of this district's median yield among all districts
               growing that crop in that season. Unit-free by construction.
  adoption     share of the district's cropped area in that season. A crop
               neighbours actually plant is evidence the land and market suit it.
  reliability  fraction of years it was grown, and 1 - coefficient of variation
               of yield. A crop that yields well but only in one year in five is
               a gamble, and a smallholder cannot absorb that.

score = 0.45*suitability + 0.35*adoption + 0.20*reliability

Output: data/crop_suitability.csv.gz, one row per (state, district, season, crop).

    python scripts/build_crop_suitability.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "apy_long.csv.gz"
OUT = ROOT / "data" / "crop_suitability.csv.gz"

# Below this a "crop" is a trial plot or a reporting artefact, not something to
# recommend to a farmer.
MIN_AREA_HA = 5.0
# Coconut is reported in nuts/hectare; flagged so nothing ever prints it as tonnes.
NON_TONNE_UNITS = {"Coconut": "nuts/ha"}


def main() -> int:
    if not SRC.is_file():
        print(f"missing {SRC}; run build_apy_dataset.py first", file=sys.stderr)
        return 1

    df = pd.read_csv(SRC)
    before = len(df)
    df = df[(df.area_ha.fillna(0) >= MIN_AREA_HA) & (df.yield_t_per_ha.fillna(0) > 0)]
    print(f"{before:,} rows -> {len(df):,} after dropping sub-{MIN_AREA_HA:g}ha and zero-yield")

    n_years = df.year.nunique()
    grouped = df.groupby(["state", "district", "season", "crop"])
    agg = grouped.agg(
        yield_median=("yield_t_per_ha", "median"),
        yield_std=("yield_t_per_ha", "std"),
        area_median_ha=("area_ha", "median"),
        production_median_t=("production_t", "median"),
        years_present=("year", "nunique"),
    ).reset_index()

    # --- suitability: percentile within crop+season, so units cancel ---------
    agg["yield_pctile"] = (
        agg.groupby(["crop", "season"]).yield_median.rank(pct=True)
    )
    # A crop grown in only a handful of districts has an unstable percentile.
    cohort = agg.groupby(["crop", "season"]).district.transform("size")
    agg.loc[cohort < 5, "yield_pctile"] = np.nan

    # --- adoption: share of this district-season's cropped area -------------
    district_area = agg.groupby(["state", "district", "season"]).area_median_ha.transform("sum")
    agg["area_share"] = agg.area_median_ha / district_area.replace(0, np.nan)

    # --- reliability: grown consistently, and yield not wildly variable ------
    agg["year_coverage"] = agg.years_present / n_years
    cv = agg.yield_std / agg.yield_median.replace(0, np.nan)
    agg["yield_cv"] = cv.fillna(cv.median())
    agg["stability"] = (1 - agg.yield_cv.clip(0, 1)).clip(0, 1)
    agg["reliability"] = 0.6 * agg.year_coverage + 0.4 * agg.stability

    # --- combined score ------------------------------------------------------
    suitability = agg.yield_pctile.fillna(agg.yield_pctile.median())
    # Area share is extremely skewed (a staple can be 0.6, a spice 0.001), so
    # rank it rather than using the raw fraction, keeping the weights meaningful.
    adoption = agg.groupby(["state", "district", "season"]).area_share.rank(pct=True)
    agg["score"] = (
        0.45 * suitability + 0.35 * adoption.fillna(0.5) + 0.20 * agg.reliability
    ).round(4)

    agg["yield_unit"] = agg.crop.map(NON_TONNE_UNITS).fillna("t/ha")
    agg["rank_in_district"] = (
        agg.groupby(["state", "district", "season"]).score
        .rank(ascending=False, method="min").astype(int)
    )

    for column in ("yield_median", "area_median_ha", "production_median_t"):
        agg[column] = agg[column].round(3)
    for column in ("yield_pctile", "area_share", "reliability", "yield_cv"):
        agg[column] = agg[column].round(4)

    agg = agg.drop(columns=["yield_std", "stability", "year_coverage"])
    agg.sort_values(["state", "district", "season", "rank_in_district"], inplace=True)
    agg.to_csv(OUT, index=False, compression="gzip")

    print(f"wrote {len(agg):,} rows -> {OUT.name} ({OUT.stat().st_size/1e6:.1f} MB)")
    print(f"  districts {agg.district.nunique()} | crops {agg.crop.nunique()} | seasons {agg.season.nunique()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

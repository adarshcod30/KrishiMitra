#!/usr/bin/env python3
"""Harvest district soil-nutrient baselines from the Soil Health Card portal.

Source: the public GraphQL API at soilhealth4.dac.gov.in that backs the
official nutrient dashboard (soilhealth.dac.gov.in/nutrient-dashboard) - the
same queries every dashboard visitor's browser issues, fetched sequentially
with a delay out of courtesy. ~34 states -> ~750 districts x 2 cycles.

The portal reports per-block SAMPLE COUNTS in classes (N/P/K Low-Medium-High,
OC, pH Acidic-Neutral-Alkaline, EC, S and micronutrient sufficiency). Blocks
are summed to district level and both cycles are combined; the committed
artefact stores class percentages plus the sample count so the app can say
"based on N soil tests in your district".

    python scripts/fetch_shc_baselines.py            # full run (~8 min)
    python scripts/fetch_shc_baselines.py --states 2 # smoke test
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
import time
from pathlib import Path

import httpx

API = "https://soilhealth4.dac.gov.in/"
HEADERS = {"Content-Type": "application/json", "Origin": "https://soilhealth.dac.gov.in"}
CYCLES = ("2024-25", "2023-24")
OUT = Path(__file__).resolve().parents[1] / "data" / "shc_district_baselines.csv.gz"
DELAY_S = 0.25

Q_STATE = "query GetState($getStateId: String, $code: String) { getState(id: $getStateId, code: $code) }"
Q_DISTRICT = (
    "query D($state: ID) { getdistrictAndSubdistrictBystate(state: $state) }"
)
Q_NUTRIENT = (
    "query N($state: ID, $district: ID, $cycle: String) "
    "{ getNutrientDashboardForPortal(state: $state, district: $district, cycle: $cycle) }"
)

# portal class name -> our column stem
MACROS = {"n": "n", "p": "p", "k": "k", "OC": "oc"}
MICROS = ("S", "Fe", "Zn", "Cu", "Mn", "B")


def gql(client: httpx.Client, query: str, variables: dict) -> dict:
    for attempt in (1, 2, 3):
        try:
            r = client.post(API, headers=HEADERS, json={"query": query, "variables": variables})
            r.raise_for_status()
            payload = r.json()
            if "errors" in payload:
                raise RuntimeError(payload["errors"][:1])
            return payload["data"]
        except Exception:
            if attempt == 3:
                raise
            time.sleep(1.5 * attempt)
    raise RuntimeError("unreachable")


def add(into: dict, results: dict) -> None:
    for key, classes in (results or {}).items():
        if not isinstance(classes, dict):
            continue
        bucket = into.setdefault(key, {})
        for cls, count in classes.items():
            if isinstance(count, (int, float)):
                bucket[cls] = bucket.get(cls, 0) + int(count)


def pct(bucket: dict, cls: str) -> float | None:
    total = sum(bucket.values())
    if not total:
        return None
    return round(100.0 * bucket.get(cls, 0) / total, 2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", type=int, default=0, help="limit for smoke tests")
    args = ap.parse_args()

    client = httpx.Client(timeout=45)
    states = gql(client, Q_STATE, {})["getState"]
    if args.states:
        states = states[: args.states]
    print(f"{len(states)} states")

    rows: list[dict] = []
    failures: list[str] = []
    for si, state in enumerate(states, 1):
        try:
            districts = gql(client, Q_DISTRICT, {"state": state["_id"]})[
                "getdistrictAndSubdistrictBystate"
            ]
        except Exception as exc:
            failures.append(f"{state['name']}: districts ({exc})")
            continue
        print(f"[{si}/{len(states)}] {state['name']}: {len(districts)} districts")
        for district in districts:
            merged: dict = {}
            for cycle in CYCLES:
                time.sleep(DELAY_S)
                try:
                    data = gql(client, Q_NUTRIENT, {
                        "state": state["_id"], "district": district["_id"], "cycle": cycle,
                    })["getNutrientDashboardForPortal"]
                except Exception as exc:
                    failures.append(f"{state['name']}/{district['name']}/{cycle}: {exc}")
                    continue
                for block in data or []:
                    add(merged, block.get("results") or {})

            # Nutrients are tested very unevenly (a district can have 7,000 P
            # samples and 22 N samples), so every nutrient carries its own
            # sample count and the headline count is the best-covered one.
            all_counts = [sum(v.values()) for v in merged.values() if isinstance(v, dict)]
            row = {
                "state": state["name"].title(),
                "district": district["name"].title(),
                "samples_n": max(all_counts) if all_counts else 0,
            }
            for src, stem in MACROS.items():
                bucket = merged.get(src) or {}
                row[f"{stem}_samples"] = sum(bucket.values())
                for cls in ("Low", "Medium", "High"):
                    row[f"{stem}_{cls.lower()}_pct"] = pct(bucket, cls)
            ph = merged.get("pH") or {}
            row["ph_samples"] = sum(ph.values())
            for cls in ("Acidic", "Neutral", "Alkaline"):
                row[f"ph_{cls.lower()}_pct"] = pct(ph, cls)
            row["ec_saline_pct"] = pct(merged.get("EC") or {}, "Saline")
            for micro in MICROS:
                row[f"{micro.lower()}_deficient_pct"] = pct(
                    merged.get(micro) or {}, "Deficient"
                )
            rows.append(row)

    fields = list(rows[0].keys()) if rows else []
    with gzip.open(OUT, "wt", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nwrote {len(rows)} district rows -> {OUT.name} "
          f"({OUT.stat().st_size/1e3:.0f} KB)")
    if failures:
        print(f"{len(failures)} failures (first 5): {failures[:5]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

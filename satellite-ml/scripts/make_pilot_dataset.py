#!/usr/bin/env python3
"""Generate (or ingest) the pilot ARD cube once and cache it to disk.

Useful when you want to iterate on models/advisory without regenerating data
each time, or to inspect the raw cube.

    python scripts/make_pilot_dataset.py                 # -> data/processed/pilot_cube.npz
    python scripts/make_pilot_dataset.py --source gee
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402

from krishimitra_rs.config import load_config  # noqa: E402
from krishimitra_rs.data.ard import save_cube  # noqa: E402
from krishimitra_rs.pipeline import get_cube  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--source", choices=["simulate", "gee"], default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.source:
        cfg.data["source"] = args.source

    print(f"Building ARD cube (source={cfg.data.get('source')}) ...")
    cube = get_cube(cfg)
    out = Path(args.out) if args.out else (cfg.root / "data" / "processed" / "pilot_cube.npz")
    save_cube(cube, out)

    print(f"Saved cube -> {out}")
    print(f"  grid {cube.H}x{cube.W}, {cube.T} composites "
          f"({cube.dates[0]} -> {cube.dates[-1]})")
    if cube.labels is not None:
        codes, counts = np.unique(cube.labels, return_counts=True)
        names = cube.meta.get("crop_names", {})
        dist = {names.get(str(c), names.get(int(c), c)): int(n) for c, n in zip(codes, counts)}
        print(f"  label distribution: {dist}")
    print(f"  optical cloud fraction: {float(np.isnan(cube.optical['red']).mean()):.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

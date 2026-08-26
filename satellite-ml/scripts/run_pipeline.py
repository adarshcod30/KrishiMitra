#!/usr/bin/env python3
"""Convenience entry point: run the full KrishiMitra-RS pipeline.

    python scripts/run_pipeline.py                 # simulated pilot (default)
    python scripts/run_pipeline.py --source gee    # real Sentinel-1/2 (needs EE auth)
    python scripts/run_pipeline.py --no-figures    # metrics only, faster

Equivalent to ``python -m krishimitra_rs.pipeline`` once the package is installed.
"""
import sys
from pathlib import Path

# allow running from a source checkout without `pip install`
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from krishimitra_rs.pipeline import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

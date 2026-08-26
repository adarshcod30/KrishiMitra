"""Configuration loading and season/time-axis helpers.

`Config` is a thin, well-typed wrapper over ``config/pilot_area.yaml`` so the
rest of the code can ask for domain concepts (``cfg.composite_dates``,
``cfg.crop_by_code(1)``) instead of digging through nested dicts.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Repo layout anchors (…/satellite-ml/…).
PKG_ROOT = Path(__file__).resolve().parents[2]           # satellite-ml/
DEFAULT_CONFIG = PKG_ROOT / "config" / "pilot_area.yaml"


def _to_date(s: str | _dt.date) -> _dt.date:
    if isinstance(s, _dt.date):
        return s
    return _dt.date.fromisoformat(str(s))


@dataclass
class Config:
    """Parsed pilot configuration with convenience accessors."""

    raw: dict[str, Any]
    path: Path
    root: Path = field(default=PKG_ROOT)

    # ---- sections ---------------------------------------------------------
    @property
    def pilot(self) -> dict[str, Any]:
        return self.raw["pilot"]

    @property
    def season(self) -> dict[str, Any]:
        return self.raw["season"]

    @property
    def data(self) -> dict[str, Any]:
        return self.raw["data"]

    @property
    def crops(self) -> list[dict[str, Any]]:
        return self.raw["crops"]

    @property
    def meteorology(self) -> dict[str, Any]:
        return self.raw["meteorology"]

    @property
    def ground_truth(self) -> dict[str, Any]:
        return self.raw["ground_truth"]

    @property
    def stress(self) -> dict[str, Any]:
        return self.raw["stress"]

    @property
    def advisory(self) -> dict[str, Any]:
        return self.raw["advisory"]

    @property
    def output(self) -> dict[str, Any]:
        return self.raw.get("output", {})

    # ---- time axis --------------------------------------------------------
    @property
    def start_date(self) -> _dt.date:
        return _to_date(self.season["start_date"])

    @property
    def end_date(self) -> _dt.date:
        return _to_date(self.season["end_date"])

    @property
    def composite_days(self) -> int:
        return int(self.season["composite_days"])

    @property
    def composite_dates(self) -> list[_dt.date]:
        """Centre dates of each temporal composite across the season."""
        step = self.composite_days
        n = (self.end_date - self.start_date).days // step + 1
        return [self.start_date + _dt.timedelta(days=step * i) for i in range(n)]

    @property
    def n_timesteps(self) -> int:
        return len(self.composite_dates)

    @property
    def doys(self) -> list[int]:
        """Day-of-year for each composite (used by phenology curves)."""
        return [d.timetuple().tm_yday for d in self.composite_dates]

    # ---- grid -------------------------------------------------------------
    @property
    def grid_hw(self) -> tuple[int, int]:
        h, w = self.data.get("grid_hw", [128, 128])
        return int(h), int(w)

    @property
    def seed(self) -> int:
        return int(self.data.get("seed", 0))

    # ---- crop lookups -----------------------------------------------------
    def crop_by_code(self, code: int) -> dict[str, Any]:
        for c in self.crops:
            if int(c["code"]) == int(code):
                return c
        raise KeyError(f"No crop with code {code}")

    @property
    def crop_codes(self) -> list[int]:
        return [int(c["code"]) for c in self.crops]

    @property
    def crop_names(self) -> list[str]:
        return [c["name"] for c in self.crops]

    @property
    def code_to_name(self) -> dict[int, str]:
        return {int(c["code"]): c["name"] for c in self.crops}

    @property
    def code_to_color(self) -> dict[int, str]:
        return {int(c["code"]): c["color"] for c in self.crops}

    # ---- paths ------------------------------------------------------------
    def out_dir(self, *parts: str) -> Path:
        d = self.root / self.output.get("dir", "outputs")
        for p in parts:
            d = d / p
        d.mkdir(parents=True, exist_ok=True)
        return d


def load_config(path: str | Path | None = None) -> Config:
    """Load pilot config from ``path`` (defaults to config/pilot_area.yaml)."""
    p = Path(path) if path else DEFAULT_CONFIG
    with open(p, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return Config(raw=raw, path=p)

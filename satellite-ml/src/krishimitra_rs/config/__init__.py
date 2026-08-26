"""Configuration loading and season/time-axis helpers.

`Config` is a thin, well-typed wrapper over ``pilot_area.yaml`` so the rest of
the code can ask for domain concepts (``cfg.composite_dates``,
``cfg.crop_by_code(1)``) instead of digging through nested dicts.

Where the default config comes from
-----------------------------------
1. an explicit ``--config`` / ``load_config(path)`` argument;
2. ``<repo>/config/pilot_area.yaml`` when running from a source checkout — the
   file the README tells you to edit;
3. ``krishimitra_rs/config/pilot_area.yaml`` shipped *inside the package* and
   resolved with :mod:`importlib.resources`, so a plain (non-editable)
   ``pip install .`` followed by ``krishimitra-rs`` works from any directory.

The two files are byte-identical and ``tests/test_pipeline.py`` asserts it, so
they cannot drift.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CONFIG_FILENAME = "pilot_area.yaml"

# Repo layout anchor: …/satellite-ml/src/krishimitra_rs/config/__init__.py
#   parents[0] config/  [1] krishimitra_rs/  [2] src/  [3] satellite-ml/
PKG_ROOT = Path(__file__).resolve().parents[3]           # satellite-ml/ (source tree)
REPO_CONFIG = PKG_ROOT / "config" / CONFIG_FILENAME
PACKAGED_CONFIG = Path(__file__).resolve().parent / CONFIG_FILENAME


def packaged_config_path() -> Path:
    """Locate the config shipped as package data (works inside a wheel/zip)."""
    try:
        from importlib.resources import as_file, files
        res = files(__name__) / CONFIG_FILENAME
        with as_file(res) as p:
            if Path(p).is_file():
                return Path(p)
    except Exception:  # pragma: no cover - importlib fallback
        pass
    return PACKAGED_CONFIG


def default_config_path() -> Path:
    """Default pilot config: the source checkout's copy, else the packaged one."""
    if REPO_CONFIG.is_file():
        return REPO_CONFIG
    return packaged_config_path()


def _default_root() -> Path:
    """Where ``outputs/`` and ``data/`` live.

    In a source checkout that is the repo root; for an installed package
    (site-packages is not writable and must not be polluted) it is the current
    working directory.
    """
    if (PKG_ROOT / "pyproject.toml").is_file():
        return PKG_ROOT
    return Path.cwd()


def _to_date(s: str | _dt.date) -> _dt.date:
    if isinstance(s, _dt.date):
        return s
    return _dt.date.fromisoformat(str(s))


@dataclass
class Config:
    """Parsed pilot configuration with convenience accessors."""

    raw: dict[str, Any]
    path: Path
    root: Path | None = field(default=None)   # None -> resolved lazily, see out_dir

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

    def resolve_doy(self, doy: int | None) -> _dt.date | None:
        """Resolve an agronomic day-of-year to a date inside this season.

        A DOY alone is ambiguous for a Rabi season that straddles the Dec->Jan
        boundary (sowing DOY 320 is *last* year, harvest DOY 105 is *this*
        year), so pick the calendar year whose date lands nearest the season
        midpoint. Returns ``None`` for an unset / zero DOY (e.g. fallow).
        """
        if not doy:
            return None
        mid = self.start_date + _dt.timedelta(days=(self.end_date - self.start_date).days // 2)
        best: _dt.date | None = None
        for yr in (self.start_date.year - 1, self.start_date.year, self.start_date.year + 1):
            try:
                d = _dt.date(yr, 1, 1) + _dt.timedelta(days=int(doy) - 1)
            except ValueError:
                continue
            if best is None or abs((d - mid).days) < abs((best - mid).days):
                best = d
        return best

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
    @property
    def base_dir(self) -> Path:
        """Root under which ``outputs/`` and ``data/`` are written."""
        return self.root if self.root is not None else _default_root()

    def out_dir(self, *parts: str) -> Path:
        d = self.base_dir / self.output.get("dir", "outputs")
        for p in parts:
            d = d / p
        d.mkdir(parents=True, exist_ok=True)
        return d


def load_config(path: str | Path | None = None) -> Config:
    """Load the pilot config from ``path`` (default: :func:`default_config_path`)."""
    p = Path(path) if path else default_config_path()
    with open(p, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return Config(raw=raw, path=p)

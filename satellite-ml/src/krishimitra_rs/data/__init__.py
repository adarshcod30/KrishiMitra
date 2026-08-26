"""Data ingestion + analysis-ready-data (ARD) assembly.

Two interchangeable sources produce the same :class:`~krishimitra_rs.data.ard.DataCube`:

* :mod:`krishimitra_rs.data.simulate` — a physically-grounded optical+SAR
  generator that runs anywhere (default; used for the demo/hackathon).
* :mod:`krishimitra_rs.data.gee_ingest` — real Sentinel-1/2 (+MODIS/Landsat)
  ingestion via Google Earth Engine (used for a real pilot command area).
"""
from .ard import DataCube, composite_gapfill, load_cube, save_cube  # noqa: F401

__all__ = ["DataCube", "composite_gapfill", "save_cube", "load_cube"]

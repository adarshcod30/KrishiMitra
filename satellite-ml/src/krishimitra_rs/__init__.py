"""KrishiMitra-RS — AI-driven crop-type mapping, phenology-aware moisture-stress
detection and FAO-56 irrigation advisory from optical + SAR satellite data.

The package is organised as a linear, inspectable pipeline:

    data      -> ingest real (GEE) or simulate an analysis-ready data cube (ARD)
    features  -> spectral indices, GLCM texture, phenology metrics
    models    -> crop-type classifier (RF/XGBoost) + moisture-stress detector
    advisory  -> growth-stage detection + FAO-56 water balance -> irrigation map
    validation-> overall accuracy, kappa, stage-wise stress checks
    viz       -> colour-coded maps and time-series figures

`pipeline.run()` wires these together end-to-end.
"""

__version__ = "0.1.0"

from .config import Config, load_config  # noqa: E402,F401

__all__ = ["Config", "load_config", "__version__"]

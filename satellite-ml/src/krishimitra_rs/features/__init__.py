"""Feature extraction: spectral/SAR indices, GLCM texture, phenology metrics,
and assembly into a per-pixel feature table for the classifiers.
"""
from .build import FeatureStack, build_feature_stack  # noqa: F401
from .indices import compute_indices  # noqa: F401
from .phenology import phenology_metrics  # noqa: F401
from .texture import texture_features  # noqa: F401

__all__ = [
    "compute_indices",
    "texture_features",
    "phenology_metrics",
    "build_feature_stack",
    "FeatureStack",
]

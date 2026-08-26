"""Models: crop-type classification (RF / XGBoost, DL optional) and
phenology-aware moisture-stress detection.
"""
from .crop_classifier import ClassificationResult, classify_crops, sample_ground_truth  # noqa: F401
from .stress import StressResult, detect_moisture_stress  # noqa: F401

__all__ = [
    "sample_ground_truth",
    "classify_crops",
    "ClassificationResult",
    "detect_moisture_stress",
    "StressResult",
]

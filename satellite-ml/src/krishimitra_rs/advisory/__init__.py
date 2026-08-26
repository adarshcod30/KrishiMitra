"""Irrigation advisory: growth-stage Kc reconstruction, FAO-56 root-zone water
balance (8-day crop water deficit), and translation to an irrigation-status map.
"""
from .irrigation import AdvisoryResult, generate_advisory  # noqa: F401
from .phenology_stage import detect_growth_stage, kc_from_detected_stage  # noqa: F401
from .water_balance import WaterBalanceResult, water_balance  # noqa: F401

__all__ = [
    "detect_growth_stage",
    "kc_from_detected_stage",
    "water_balance",
    "WaterBalanceResult",
    "generate_advisory",
    "AdvisoryResult",
]

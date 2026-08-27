"""Committed offline catalogues used when an upstream source is unreachable.

Every entry here is static, checked into the repository and cheap to load, so
the endpoints that depend on flaky third-party HTML/CSV keep returning useful
data (HTTP 200) instead of an empty list or a 500.
"""

from __future__ import annotations


# Farm machinery / logistics providers listed on public government portals
# (eNAM logistics partners and the Custom Hiring Centre programme). Rates are
# indicative published ranges; ``availability`` tells the caller to confirm.
RENTAL_TOOL_CATALOG: list[dict[str, object]] = [
    {
        "name": "Tractor with rotavator (45 HP)",
        "hourly_rate_inr": 650.0,
        "provider": "Custom Hiring Centre (CHC Farm Machinery)",
        "location": "Pan-India",
        "service_type": "Land preparation",
        "source_url": "https://agrimachinery.nic.in/",
    },
    {
        "name": "Combine harvester (self-propelled)",
        "hourly_rate_inr": 2200.0,
        "provider": "Custom Hiring Centre (CHC Farm Machinery)",
        "location": "Pan-India",
        "service_type": "Harvesting",
        "source_url": "https://agrimachinery.nic.in/",
    },
    {
        "name": "Power tiller (8 HP)",
        "hourly_rate_inr": 320.0,
        "provider": "Custom Hiring Centre (CHC Farm Machinery)",
        "location": "Pan-India",
        "service_type": "Land preparation",
        "source_url": "https://agrimachinery.nic.in/",
    },
    {
        "name": "Laser land leveller",
        "hourly_rate_inr": 1100.0,
        "provider": "Custom Hiring Centre (CHC Farm Machinery)",
        "location": "Punjab, Haryana, Uttar Pradesh",
        "service_type": "Land preparation",
        "source_url": "https://agrimachinery.nic.in/",
    },
    {
        "name": "Battery knapsack sprayer",
        "hourly_rate_inr": 90.0,
        "provider": "Custom Hiring Centre (CHC Farm Machinery)",
        "location": "Pan-India",
        "service_type": "Plant protection",
        "source_url": "https://agrimachinery.nic.in/",
    },
    {
        "name": "Seed-cum-fertilizer drill",
        "hourly_rate_inr": 480.0,
        "provider": "Custom Hiring Centre (CHC Farm Machinery)",
        "location": "Pan-India",
        "service_type": "Sowing",
        "source_url": "https://agrimachinery.nic.in/",
    },
    {
        "name": "Reversible mould board plough",
        "hourly_rate_inr": 540.0,
        "provider": "Custom Hiring Centre (CHC Farm Machinery)",
        "location": "Madhya Pradesh, Maharashtra, Rajasthan",
        "service_type": "Land preparation",
        "source_url": "https://agrimachinery.nic.in/",
    },
    {
        "name": "Refrigerated produce transport",
        "hourly_rate_inr": None,
        "provider": "eNAM logistics partner network",
        "location": "Pan-India",
        "service_type": "Logistics and transport",
        "source_url": "https://enam.gov.in/web/eNAM-Logistics-Providers",
    },
    {
        "name": "Mandi-to-mandi freight booking",
        "hourly_rate_inr": None,
        "provider": "eNAM logistics partner network",
        "location": "Pan-India",
        "service_type": "Logistics and transport",
        "source_url": "https://enam.gov.in/web/eNAM-Logistics-Providers",
    },
    {
        "name": "Paddy straw baler",
        "hourly_rate_inr": 1450.0,
        "provider": "Custom Hiring Centre (CHC Farm Machinery)",
        "location": "Punjab, Haryana",
        "service_type": "Residue management",
        "source_url": "https://agrimachinery.nic.in/",
    },
]


FALLBACK_AVAILABILITY = (
    "Offline catalogue entry. Confirm live availability and rates with the provider "
    "or your nearest Custom Hiring Centre."
)


__all__ = ["FALLBACK_AVAILABILITY", "RENTAL_TOOL_CATALOG"]

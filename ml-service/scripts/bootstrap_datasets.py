"""Materialise the datasets the trainer needs.

Everything here is best-effort over the network and authoritative offline: the
canonical ``data/Crop_dataset.csv`` (2200 rows) is committed to the repository,
so this script must succeed on a machine with no internet access. The upstream
GitHub copy it used to download was deleted (the raw URL now 404s), which made
the very first action fatal and the whole bootstrap unusable.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Kept for provenance. Optional: the committed CSV is the canonical copy and
# this mirror is only consulted when --refresh-remote is passed.
CROP_DATASET_MIRRORS = (
    "https://raw.githubusercontent.com/Gaiban-Khan/Crop-Recommendation-System/master/Dataset/Crop_dataset.csv",
)

CROP_DATASET_HEADER = "N,P,K,temperature,humidity,ph,rainfall,label"
USER_AGENT = "agrotech-ml-bootstrap/1.0"
NETWORK_TIMEOUT_SECONDS = 20


def fetch(url: str, *, timeout: int = NETWORK_TIMEOUT_SECONDS) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https URLs
        return response.read()


def looks_like_crop_dataset(payload: bytes) -> bool:
    try:
        first_line = payload.decode("utf-8", errors="replace").splitlines()[0]
    except IndexError:
        return False
    return first_line.strip().lower() == CROP_DATASET_HEADER


def ensure_crop_dataset(path: Path, *, refresh_remote: bool) -> bool:
    """Return True when a usable dataset is in place.

    The committed file always wins unless ``--refresh-remote`` is given, and a
    failed refresh never destroys or invalidates the committed copy.
    """
    committed_ok = path.is_file() and path.stat().st_size > 0

    if refresh_remote:
        for url in CROP_DATASET_MIRRORS:
            try:
                payload = fetch(url)
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                print(f"- Crop_dataset.csv: remote refresh from {url} failed ({exc}); keeping committed copy")
                continue
            if not looks_like_crop_dataset(payload):
                print(f"- Crop_dataset.csv: remote payload from {url} is not the expected CSV; ignoring")
                continue
            path.write_bytes(payload)
            print(f"- Crop_dataset.csv: refreshed from {url}")
            return True
    elif not committed_ok:
        # No committed copy and no explicit refresh request: try anyway.
        for url in CROP_DATASET_MIRRORS:
            try:
                payload = fetch(url)
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                print(f"- Crop_dataset.csv: download from {url} failed ({exc})")
                continue
            if looks_like_crop_dataset(payload):
                path.write_bytes(payload)
                print(f"- Crop_dataset.csv: downloaded from {url}")
                return True

    if committed_ok:
        rows = max(0, sum(1 for _ in path.open(encoding="utf-8", errors="replace")) - 1)
        print(f"- Crop_dataset.csv: using committed copy ({rows} rows)")
        return True

    print("- Crop_dataset.csv: MISSING and no mirror reachable", file=sys.stderr)
    return False


def write_market_sample(path: Path) -> None:
    """Offline mandi-price fallback covering every crop the UI dropdown offers.

    Served only when the live data.gov.in feed is unreachable. Prices are
    representative values inside the modal-price ranges reported by public
    mandi trackers for late August 2026 (see data/README.md for the ranges and
    sources); mandi names are real APMCs known for those commodities.
    """
    rows = [
        ["date", "crop", "mandi", "state", "modal_price_inr_quintal", "trend"],
        ["2026-08-26", "Wheat", "Khanna", "Punjab", 2600, "stable"],
        ["2026-08-26", "Wheat", "Karnal", "Haryana", 2900, "stable"],
        ["2026-08-26", "Wheat", "Indore", "Madhya Pradesh", 2500, "stable"],
        ["2026-08-26", "Rice", "Karnal", "Haryana", 3800, "stable"],
        ["2026-08-26", "Rice", "Amritsar", "Punjab", 3400, "stable"],
        ["2026-08-26", "Rice", "Jorhat", "Assam", 4200, "stable"],
        ["2026-08-26", "Potato", "Agra", "Uttar Pradesh", 800, "down"],
        ["2026-08-26", "Potato", "Jalandhar", "Punjab", 900, "down"],
        ["2026-08-26", "Potato", "Sheoraphuli", "West Bengal", 750, "down"],
        ["2026-08-26", "Tomato", "Kolar", "Karnataka", 1900, "down"],
        ["2026-08-26", "Tomato", "Madanapalle", "Andhra Pradesh", 2100, "down"],
        ["2026-08-26", "Tomato", "Pimpalgaon", "Maharashtra", 2200, "down"],
        ["2026-08-26", "Onion", "Lasalgaon", "Maharashtra", 4100, "up"],
        ["2026-08-26", "Onion", "Bengaluru", "Karnataka", 4300, "up"],
        ["2026-08-26", "Onion", "Indore", "Madhya Pradesh", 3900, "up"],
        ["2026-08-26", "Chilli", "Guntur", "Andhra Pradesh", 2600, "stable"],
        ["2026-08-26", "Chilli", "Raipur", "Chhattisgarh", 2400, "stable"],
        ["2026-08-26", "Chilli", "Surat", "Gujarat", 2500, "stable"],
        ["2026-08-26", "Cotton", "Rajkot", "Gujarat", 6900, "stable"],
        ["2026-08-26", "Cotton", "Adilabad", "Telangana", 7100, "stable"],
        ["2026-08-26", "Cotton", "Sirsa", "Haryana", 6800, "stable"],
        ["2026-08-26", "Maize", "Nizamabad", "Telangana", 1900, "down"],
        ["2026-08-26", "Maize", "Davangere", "Karnataka", 2000, "down"],
        ["2026-08-26", "Maize", "Chhindwara", "Madhya Pradesh", 1800, "down"],
    ]

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerows(rows)


# Diverse subset of the curated dataset used when disease_symptoms.csv itself
# is somehow absent. Never edit content here directly - keep it a verbatim
# copy of rows from data/disease_symptoms.csv (same columns, same sources).
DISEASE_SAMPLE_LABELS = (
    "rice_blast",
    "rice_brown_planthopper",
    "wheat_yellow_rust",
    "cotton_pink_bollworm",
    "tomato_late_blight",
    "chilli_thrips",
    "maize_fall_armyworm",
    "gram_pod_borer",
)

DISEASE_COLUMNS = [
    "crop",
    "symptoms_text",
    "disease",
    "label",
    "severity",
    "treatment",
    "prevention",
    "source",
]


def write_disease_samples(path: Path) -> None:
    """Write the tiny fallback sample as a subset of the curated dataset.

    data/disease_symptoms.csv is the source of truth (50 diseases, treatment +
    prevention + citation per disease); this sample only exists so a checkout
    missing the curated file can still train something. When the curated file
    is present, copy the richest row of a few diverse diseases from it so the
    fallback stays consistent automatically.
    """
    curated = path.parent / "disease_symptoms.csv"
    rows: list[list[str]] = [DISEASE_COLUMNS]

    if curated.is_file():
        seen: set[str] = set()
        with curated.open(encoding="utf-8", newline="") as file:
            for row in csv.DictReader(file):
                label = (row.get("label") or "").strip()
                if label in DISEASE_SAMPLE_LABELS and label not in seen and row.get("treatment"):
                    seen.add(label)
                    rows.append([row.get(column, "") for column in DISEASE_COLUMNS])
        if len(rows) > 1:
            with path.open("w", newline="", encoding="utf-8") as file:
                csv.writer(file).writerows(rows)
            return

    # Curated dataset missing: minimal hand-copied subset (from the same
    # verified extension sources as data/disease_symptoms.csv).
    rows.extend(
        [
            [
                "rice",
                "leaf spots shaped like eyes or spindles with grey centre and brown edge, spots join together and leaves dry up",
                "Rice blast",
                "rice_blast",
                "high",
                "Spray tricyclazole 75 WP at 0.6 g per litre at the first sign of spots; repeat after 12-15 days if new spots keep appearing.",
                "Use blast resistant varieties|Treat seed with tricyclazole or carbendazim 2 g per kg|Split nitrogen doses",
                "TNAU Agritech Portal, Crop Protection: Rice (agritech.tnau.ac.in)",
            ],
            [
                "wheat",
                "yellow orange powder in long stripes along the veins of the leaf, powder sticks to the finger when rubbed",
                "Yellow rust (stripe rust)",
                "wheat_yellow_rust",
                "high",
                "Spray propiconazole 25 EC 1 ml per litre as soon as the first pustules are seen.",
                "Grow rust resistant varieties|Sow on time|Scout weekly in cool humid weeks",
                "ICAR yellow rust advisory (icar.org.in); ICAR-IIWBR (iiwbr.org.in)",
            ],
            [
                "cotton",
                "flowers do not open properly and look like a rosette, pink caterpillars inside green bolls",
                "Pink bollworm",
                "cotton_pink_bollworm",
                "high",
                "Set 8 pheromone traps per acre; spray profenofos 50 EC 2 ml per litre or emamectin benzoate 5 SG 0.4 g per litre when catches cross threshold.",
                "End the crop by December-January, never ratoon|Destroy stalks and unopened bolls after last picking",
                "ICAR-CICR pink bollworm advisories (cicr.org.in)",
            ],
            [
                "tomato",
                "large water soaked dark patches on leaves and stems during cool cloudy wet weather, white fungal ring under the leaf",
                "Late blight",
                "tomato_late_blight",
                "high",
                "Remove infected parts and spray cymoxanil 8% + mancozeb 64% WP 3 g per litre; repeat after 10 days.",
                "Protective mancozeb sprays in cool cloudy weather|Avoid overhead evening irrigation",
                "ICAR-CPRI late blight management (cpri.icar.gov.in); TNAU Agritech Portal",
            ],
            [
                "maize",
                "ragged holes and window like patches on whorl leaves, wet sawdust like droppings inside the funnel",
                "Fall armyworm",
                "maize_fall_armyworm",
                "high",
                "Drop dry sand or soil mixed with lime into the funnel for small larvae; spray emamectin benzoate 5 SG 0.4 g per litre into the whorl if damage crosses 1 in 10 plants.",
                "Pheromone traps 4 per acre from week one|Sow on time together with neighbours|Bird perches",
                "ICAR fall armyworm advisory; Indian field efficacy trials",
            ],
        ]
    )
    with path.open("w", newline="", encoding="utf-8") as file:
        csv.writer(file).writerows(rows)


def write_weather_samples(path: Path) -> bool:
    """Refresh the weather snapshot. Best-effort: keeps the committed file offline."""
    locations = {
        "Ahmedabad": (23.0225, 72.5714),
        "Lucknow": (26.8467, 80.9462),
        "Bengaluru": (12.9716, 77.5946),
    }
    payload: dict[str, dict] = {}

    for name, (lat, lon) in locations.items():
        url = (
            "https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
            "&timezone=auto&forecast_days=5"
        )
        try:
            payload[name] = json.loads(fetch(url).decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            print(f"- weather_forecast_samples.json: {name} refresh failed ({exc})")
            return False

    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap the agrotech-ml datasets.")
    parser.add_argument(
        "--refresh-remote",
        action="store_true",
        help="Try to re-download Crop_dataset.csv and the weather snapshot from upstream.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip every network call and regenerate only the local sample files.",
    )
    args = parser.parse_args(argv)

    print("Bootstrapping datasets...")

    crop_ok = ensure_crop_dataset(
        DATA_DIR / "Crop_dataset.csv",
        refresh_remote=args.refresh_remote and not args.offline,
    )

    write_market_sample(DATA_DIR / "market_prices_sample.csv")
    print("- Wrote market_prices_sample.csv")

    write_disease_samples(DATA_DIR / "disease_symptoms_sample.csv")
    print("- Wrote disease_symptoms_sample.csv")

    weather_path = DATA_DIR / "weather_forecast_samples.json"
    if args.offline:
        print("- weather_forecast_samples.json: offline mode, keeping committed snapshot")
    elif write_weather_samples(weather_path):
        print("- Refreshed weather_forecast_samples.json")
    elif weather_path.is_file():
        print("- weather_forecast_samples.json: keeping committed snapshot")
    else:
        print("- weather_forecast_samples.json: unavailable (no committed snapshot)", file=sys.stderr)

    if not crop_ok:
        print("Dataset bootstrap FAILED: Crop_dataset.csv is required for training.", file=sys.stderr)
        return 1

    print("Dataset bootstrap complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

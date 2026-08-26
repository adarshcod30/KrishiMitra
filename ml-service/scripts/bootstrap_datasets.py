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
    rows = [
        ["date", "crop", "mandi", "state", "modal_price_inr_quintal", "trend"],
        ["2026-03-10", "Wheat", "Azadpur", "Delhi", 2475, "up"],
        ["2026-03-10", "Rice", "Karnal", "Haryana", 3150, "stable"],
        ["2026-03-10", "Maize", "Nizamabad", "Telangana", 2120, "up"],
        ["2026-03-10", "Cotton", "Rajkot", "Gujarat", 6980, "down"],
        ["2026-03-10", "Chickpea", "Indore", "Madhya Pradesh", 5350, "up"],
    ]

    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerows(rows)


def write_disease_samples(path: Path) -> None:
    rows = [
        ["symptoms", "label"],
        ["yellow leaves and hopper insects in paddy", "rice_brown_hopper"],
        ["powdery white growth on leaves", "powdery_mildew"],
        ["rust pustules on wheat leaf", "wheat_rust"],
        ["boll rot and dark lesions in cotton", "cotton_boll_rot"],
        ["leaf spot and drop in vegetables", "leaf_spot"],
    ]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerows(rows)


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

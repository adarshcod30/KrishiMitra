from __future__ import annotations

import csv
import json
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def download_file(url: str, path: Path) -> None:
    with urlopen(url, timeout=30) as response:
        content = response.read()
    path.write_bytes(content)


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


def write_weather_samples(path: Path) -> None:
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
        with urlopen(url, timeout=30) as response:
            payload[name] = json.loads(response.read().decode("utf-8"))

    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    print("Bootstrapping datasets...")

    crop_url = "https://raw.githubusercontent.com/Gaiban-Khan/Crop-Recommendation-System/master/Dataset/Crop_dataset.csv"
    download_file(crop_url, DATA_DIR / "Crop_dataset.csv")
    print("- Downloaded Crop_dataset.csv")

    write_market_sample(DATA_DIR / "market_prices_sample.csv")
    print("- Wrote market_prices_sample.csv")

    write_disease_samples(DATA_DIR / "disease_symptoms_sample.csv")
    print("- Wrote disease_symptoms_sample.csv")

    write_weather_samples(DATA_DIR / "weather_forecast_samples.json")
    print("- Downloaded weather_forecast_samples.json")

    print("Dataset bootstrap complete.")


if __name__ == "__main__":
    main()

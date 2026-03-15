from pathlib import Path

import pandas as pd


FEATURE_COLUMNS = ["N", "P", "K", "temperature", "humidity", "ph", "rainfall"]
TARGET_COLUMN = "label"
REQUIRED_COLUMNS = FEATURE_COLUMNS + [TARGET_COLUMN]


def load_dataset(data_path: Path) -> pd.DataFrame:
    if not data_path.exists():
        raise FileNotFoundError(f"Dataset not found at {data_path}")

    dataframe = pd.read_csv(data_path)
    missing_columns = sorted(set(REQUIRED_COLUMNS) - set(dataframe.columns))
    if missing_columns:
        joined = ", ".join(missing_columns)
        raise ValueError(f"Dataset is missing required columns: {joined}")

    clean = dataframe[REQUIRED_COLUMNS].copy()
    clean = clean.dropna(axis=0)

    for column in FEATURE_COLUMNS:
        clean[column] = pd.to_numeric(clean[column], errors="coerce")

    clean = clean.dropna(axis=0)
    clean[TARGET_COLUMN] = clean[TARGET_COLUMN].astype(str)

    if clean.empty:
        raise ValueError("Dataset has no valid rows after cleaning")

    return clean


def feature_ranges(dataframe: pd.DataFrame) -> dict[str, dict[str, float]]:
    ranges: dict[str, dict[str, float]] = {}
    for feature in FEATURE_COLUMNS:
        series = dataframe[feature]
        ranges[feature] = {
            "min": float(series.min()),
            "max": float(series.max()),
            "mean": float(series.mean()),
            "std": float(series.std(ddof=0)),
        }

    return ranges

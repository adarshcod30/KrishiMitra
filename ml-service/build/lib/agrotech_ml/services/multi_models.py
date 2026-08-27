from __future__ import annotations

from dataclasses import dataclass

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from agrotech_ml.core.settings import AppSettings


@dataclass
class AuxiliaryArtifacts:
    disease_model: str
    fertilizer_model: str
    irrigation_model: str


CROP_WATER_FACTOR = {
    "rice": 1.45,
    "sugarcane": 1.55,
    "banana": 1.3,
    "cotton": 1.05,
    "maize": 0.95,
    "wheat": 0.9,
    "chickpea": 0.72,
    "millet": 0.62,
    "groundnut": 0.8,
}

SOIL_WATER_FACTOR = {
    "sandy": 1.15,
    "loam": 1.0,
    "clay": 0.85,
    "black": 0.9,
    "alluvial": 0.95,
}


def _train_irrigation_model(settings: AppSettings) -> None:
    rng = np.random.default_rng(settings.random_state)
    crops = list(CROP_WATER_FACTOR.keys())
    soils = list(SOIL_WATER_FACTOR.keys())

    records: list[dict] = []
    for _ in range(3500):
        crop = rng.choice(crops)
        soil = rng.choice(soils)
        temperature = float(rng.uniform(15, 42))
        humidity = float(rng.uniform(25, 95))
        rainfall = float(rng.uniform(0, 320))
        ph = float(rng.uniform(5, 8.5))
        acreage = float(rng.uniform(0.5, 15))

        base = 22 * CROP_WATER_FACTOR[crop] * SOIL_WATER_FACTOR[soil]
        climate_component = (temperature - 24) * 0.45 + (65 - humidity) * 0.14
        rain_adjustment = max(0.0, 1.0 - rainfall / 320) * 10
        ph_adjustment = abs(6.8 - ph) * 1.1
        acreage_adjustment = np.log1p(acreage) * 1.2
        water_need = max(6.0, base + climate_component + rain_adjustment + ph_adjustment + acreage_adjustment)

        records.append(
            {
                "crop": crop,
                "soil_type": soil,
                "temperature": temperature,
                "humidity": humidity,
                "rainfall": rainfall,
                "ph": ph,
                "acreage": acreage,
                "water_need_mm": float(water_need),
            }
        )

    frame = pd.DataFrame(records)
    features = frame.drop(columns=["water_need_mm"])
    labels = frame["water_need_mm"]

    model = Pipeline(
        steps=[
            (
                "preprocessor",
                ColumnTransformer(
                    transformers=[
                        (
                            "cat",
                            OneHotEncoder(handle_unknown="ignore"),
                            ["crop", "soil_type"],
                        )
                    ],
                    remainder="passthrough",
                ),
            ),
            (
                "regressor",
                RandomForestRegressor(
                    n_estimators=120,
                    random_state=settings.random_state,
                    min_samples_leaf=2,
                ),
            ),
        ]
    )
    model.fit(features, labels)

    joblib.dump(
        {
            "pipeline": model,
            "crops": crops,
            "soils": soils,
            "target": "water_need_mm",
        },
        settings.irrigation_model_path,
    )


def _fertilizer_label(n_value: float, p_value: float, k_value: float, ph: float) -> str:
    if n_value < 45:
        return "nitrogen_boost"
    if p_value < 35:
        return "phosphorus_boost"
    if k_value < 35:
        return "potassium_boost"
    if ph < 5.8:
        return "lime_and_balanced_npk"
    if ph > 7.8:
        return "organic_and_micronutrient_mix"
    return "balanced_npk"


def _train_fertilizer_model(settings: AppSettings) -> None:
    rng = np.random.default_rng(settings.random_state + 4)
    crops = ["rice", "wheat", "cotton", "maize", "banana", "chickpea", "groundnut", "millet"]
    soils = ["sandy", "loam", "clay", "black", "alluvial"]

    records: list[dict] = []
    for _ in range(5000):
        crop = rng.choice(crops)
        soil = rng.choice(soils)
        n_value = float(rng.uniform(10, 140))
        p_value = float(rng.uniform(8, 90))
        k_value = float(rng.uniform(8, 110))
        ph = float(rng.uniform(4.8, 8.8))

        label = _fertilizer_label(n_value, p_value, k_value, ph)
        records.append(
            {
                "crop": crop,
                "soil_type": soil,
                "N": n_value,
                "P": p_value,
                "K": k_value,
                "ph": ph,
                "label": label,
            }
        )

    frame = pd.DataFrame(records)
    features = frame.drop(columns=["label"])
    labels = frame["label"]

    model = Pipeline(
        steps=[
            (
                "preprocessor",
                ColumnTransformer(
                    transformers=[
                        (
                            "cat",
                            OneHotEncoder(handle_unknown="ignore"),
                            ["crop", "soil_type"],
                        )
                    ],
                    remainder="passthrough",
                ),
            ),
            (
                "classifier",
                RandomForestClassifier(
                    n_estimators=120,
                    random_state=settings.random_state,
                    min_samples_leaf=2,
                ),
            ),
        ]
    )

    model.fit(features, labels)
    joblib.dump({"pipeline": model, "labels": sorted(set(labels))}, settings.fertilizer_model_path)


def _train_disease_model(settings: AppSettings) -> None:
    samples = [
        ("yellow leaves with stunted growth and hopper insects", "rice_brown_hopper"),
        ("leaf blast lesions and drying patches in paddy", "rice_blast"),
        ("boll rot and black spots on cotton bolls", "cotton_boll_rot"),
        ("white powder on leaves and curling in grapes", "powdery_mildew"),
        ("banana leaf streak and dark elongated patches", "banana_sigatoka"),
        ("wilting plants with root rot in chickpea", "root_rot"),
        ("stem borer holes and dead heart symptoms in maize", "stem_borer"),
        ("rust pustules on wheat leaves and yellowing", "wheat_rust"),
        ("sudden wilting and fungal growth at collar", "collar_rot"),
        ("mosaic pattern and twisted leaves on chilli", "viral_mosaic"),
        ("aphid clusters and honeydew on soft leaves", "aphid_infestation"),
        ("leaf spot circular lesions and premature drop", "leaf_spot"),
    ]

    # Increase robustness with paraphrased samples.
    expanded_text: list[str] = []
    expanded_labels: list[str] = []
    paraphrases = [
        "in field condition",
        "during humid weather",
        "seen after irrigation",
        "in early crop stage",
        "with severe spread",
    ]

    for text, label in samples:
        for suffix in paraphrases:
            expanded_text.append(f"{text} {suffix}")
            expanded_labels.append(label)

    model = Pipeline(
        steps=[
            ("vectorizer", TfidfVectorizer(ngram_range=(1, 2), min_df=1)),
            (
                "classifier",
                LogisticRegression(max_iter=2400, random_state=settings.random_state),
            ),
        ]
    )

    model.fit(expanded_text, expanded_labels)
    joblib.dump({"pipeline": model, "labels": sorted(set(expanded_labels))}, settings.disease_model_path)


def train_auxiliary_models(settings: AppSettings) -> AuxiliaryArtifacts:
    _train_irrigation_model(settings)
    _train_fertilizer_model(settings)
    _train_disease_model(settings)

    return AuxiliaryArtifacts(
        disease_model="ready",
        fertilizer_model="ready",
        irrigation_model="ready",
    )

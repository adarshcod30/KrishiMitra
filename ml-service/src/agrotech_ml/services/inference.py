from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from agrotech_ml.db.dataset import FEATURE_COLUMNS
from agrotech_ml.core.i18n import localize_crop_name, tr
from agrotech_ml.db.storage import save_advisory
from agrotech_ml.models.schemas import (
    DiseaseRequest,
    DiseaseResponse,
    FertilizerRequest,
    FertilizerResponse,
    IrrigationEvent,
    IrrigationRequest,
    IrrigationResponse,
    PredictionItem,
    PredictionResponse,
    SoilAnalysisRequest,
    SoilAnalysisResponse,
    SoilWeatherInput,
)
from agrotech_ml.core.settings import AppSettings
from agrotech_ml.services.translation_service import translate_many, translate_text


logger = logging.getLogger(__name__)


CROP_TIPS = {
    "rice": "Maintain standing water in early growth and monitor blast disease during humid weeks.",
    "maize": "Apply split nitrogen doses and ensure drainage to avoid root stress.",
    "chickpea": "Prefer lighter irrigation intervals and avoid over-fertilizing nitrogen.",
    "kidneybeans": "Use organic matter to improve soil structure and avoid waterlogging.",
    "pigeonpeas": "Deep root systems benefit from moderate moisture and well-drained soils.",
    "mothbeans": "Use low-input schedules and prioritize weed control in the first 30 days.",
    "mungbean": "Short-duration crop, ideal for intercropping with balanced phosphorus.",
    "blackgram": "Apply seed treatment to reduce fungal risk and maintain neutral pH.",
    "lentil": "Cool-season pulse that responds well to phosphorus-enriched soil.",
    "pomegranate": "Use drip irrigation and prune canopies for better disease control.",
    "banana": "High potassium feeding and consistent moisture improve fruit quality.",
    "mango": "Avoid heavy irrigation during flowering and protect from powdery mildew.",
    "grapes": "Canopy management and drainage are critical in humid conditions.",
    "watermelon": "Sandy loam and controlled irrigation prevent fruit cracking.",
    "muskmelon": "Maintain warm temperature windows and avoid excess humidity.",
    "apple": "Requires cooler conditions and planned fungicide schedule in wet phases.",
    "orange": "Balanced NPK and micronutrients improve fruit set and juice quality.",
    "papaya": "Well-drained soil and regular potassium feeding are key.",
    "coconut": "Mulching helps conserve moisture in low-rainfall periods.",
    "cotton": "Monitor bollworm pressure and maintain potassium for boll development.",
    "jute": "Thrives in humid climates with consistent moisture and organic matter.",
    "coffee": "Shade management and controlled irrigation improve bean consistency.",
}

DISEASE_LIBRARY = {
    "rice_brown_hopper": {
        "title": "Brown Hopper Stress",
        "advice": "Use yellow sticky traps and neem-based spray. Avoid excess standing water.",
        "actions": [
            "Scout 2 times per week for hopper clusters.",
            "Avoid excessive nitrogen top-dressing.",
            "Maintain clean field bunds.",
        ],
        "severity": "moderate",
    },
    "rice_blast": {
        "title": "Rice Blast",
        "advice": "Improve air circulation and apply blast-safe fungicide as per local guidance.",
        "actions": [
            "Use recommended resistant varieties where possible.",
            "Avoid late evening irrigation.",
            "Remove heavily infected leaves.",
        ],
        "severity": "high",
    },
    "cotton_boll_rot": {
        "title": "Cotton Boll Rot",
        "advice": "Improve drainage and avoid overhead irrigation during humid periods.",
        "actions": [
            "Spray fungicide at early symptom stage.",
            "Harvest mature bolls on time.",
            "Reduce dense canopy humidity.",
        ],
        "severity": "moderate",
    },
    "powdery_mildew": {
        "title": "Powdery Mildew",
        "advice": "Use sulfur-based sprays and maintain canopy ventilation.",
        "actions": [
            "Start spray at first visible powdery patch.",
            "Avoid excess nitrogen use.",
            "Prune infected shoots.",
        ],
        "severity": "moderate",
    },
    "banana_sigatoka": {
        "title": "Banana Sigatoka",
        "advice": "Remove infected leaves and apply targeted fungicide rotation.",
        "actions": [
            "Keep field sanitation high.",
            "Ensure balanced potassium nutrition.",
            "Follow spray interval during rainy weeks.",
        ],
        "severity": "high",
    },
    "root_rot": {
        "title": "Root Rot",
        "advice": "Improve drainage and treat soil with bio-control agents.",
        "actions": [
            "Avoid water stagnation.",
            "Use Trichoderma-based seed treatment.",
            "Rotate with non-host crops.",
        ],
        "severity": "moderate",
    },
    "stem_borer": {
        "title": "Stem Borer",
        "advice": "Use pheromone traps and timely biological control.",
        "actions": [
            "Install pheromone traps per acre.",
            "Destroy affected dead-heart plants.",
            "Follow local IPM thresholds.",
        ],
        "severity": "moderate",
    },
    "wheat_rust": {
        "title": "Wheat Rust",
        "advice": "Apply rust-safe fungicide and monitor neighboring plots.",
        "actions": [
            "Use rust-tolerant cultivars next cycle.",
            "Maintain field scouting after dew periods.",
            "Spray early in outbreak.",
        ],
        "severity": "high",
    },
    "collar_rot": {
        "title": "Collar Rot",
        "advice": "Reduce soil moisture near plant collar and use bio-fungicides.",
        "actions": [
            "Improve root-zone drainage.",
            "Use treated seed lots.",
            "Avoid deep collar wetness.",
        ],
        "severity": "moderate",
    },
    "viral_mosaic": {
        "title": "Viral Mosaic",
        "advice": "Control vectors like whitefly and rogue infected plants early.",
        "actions": [
            "Install yellow traps for vector control.",
            "Remove severely infected plants.",
            "Use clean planting material.",
        ],
        "severity": "high",
    },
    "aphid_infestation": {
        "title": "Aphid Infestation",
        "advice": "Spray neem soap solution and encourage beneficial predators.",
        "actions": [
            "Avoid over-fertilization with nitrogen.",
            "Inspect underside of leaves every 3 days.",
            "Release or conserve ladybird beetles.",
        ],
        "severity": "low",
    },
    "leaf_spot": {
        "title": "Leaf Spot",
        "advice": "Use broad-spectrum preventive fungicide and avoid prolonged leaf wetness.",
        "actions": [
            "Remove severely affected leaves.",
            "Irrigate in morning hours.",
            "Maintain spacing for airflow.",
        ],
        "severity": "low",
    },
}

FERTILIZER_LIBRARY = {
    "nitrogen_boost": "Urea-rich split dose with neem coating",
    "phosphorus_boost": "DAP + phosphate solubilizer combination",
    "potassium_boost": "MOP based potash support",
    "lime_and_balanced_npk": "Lime correction + balanced NPK",
    "organic_and_micronutrient_mix": "Organic compost + micronutrient foliar mix",
    "balanced_npk": "Balanced NPK maintenance dose",
}


def _predict_proba(model: Any, features: pd.DataFrame) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return np.asarray(model.predict_proba(features), dtype=float)

    if hasattr(model, "decision_function"):
        decision = np.asarray(model.decision_function(features), dtype=float)
        if decision.ndim == 1:
            decision = np.column_stack([-decision, decision])
        decision = decision - decision.max(axis=1, keepdims=True)
        exp_values = np.exp(decision)
        return exp_values / exp_values.sum(axis=1, keepdims=True)

    labels = np.asarray(model.predict(features))
    classes = np.asarray(model.classes_)
    matrix = np.zeros((labels.shape[0], classes.shape[0]), dtype=float)
    class_index = {label: idx for idx, label in enumerate(classes)}
    for row_idx, label in enumerate(labels):
        matrix[row_idx, class_index[label]] = 1.0
    return matrix


def _confidence_band(probability: float) -> str:
    if probability >= 0.72:
        return "high"
    if probability >= 0.45:
        return "medium"
    return "low"


def _generate_field_actions(
    settings: AppSettings,
    payload: SoilWeatherInput,
    top_crop: str,
) -> list[str]:
    language = payload.language
    actions: list[str] = [tr(language, "validate_soil"), tr(language, "fertigation_log")]

    if payload.ph < 5.8:
        acidic_note = "Soil is acidic. Consider liming before sowing."
        actions.append(
            acidic_note
            if language == "en"
            else translate_text(
                settings=settings,
                text=acidic_note,
                target_language=language,
            )
        )
    elif payload.ph > 7.8:
        alkaline_note = "Soil is alkaline. Add organic matter and gypsum if needed."
        actions.append(
            alkaline_note
            if language == "en"
            else translate_text(
                settings=settings,
                text=alkaline_note,
                target_language=language,
            )
        )

    if payload.rainfall < 70:
        dry_note = "Rainfall is low. Plan drip irrigation and mulching."
        actions.append(
            dry_note
            if language == "en"
            else translate_text(
                settings=settings,
                text=dry_note,
                target_language=language,
            )
        )
    elif payload.rainfall > 250:
        wet_note = "Heavy rainfall expected. Keep drainage channels ready."
        actions.append(
            wet_note
            if language == "en"
            else translate_text(
                settings=settings,
                text=wet_note,
                target_language=language,
            )
        )

    actions.append(tr(language, "pilot_patch", crop=localize_crop_name(top_crop, language)))
    return actions


def _localize_text(settings: AppSettings, text: str, language: str) -> str:
    if language == "en":
        return text
    return translate_text(settings, text, language)  # type: ignore[arg-type]


def _localize_texts(settings: AppSettings, texts: list[str], language: str) -> list[str]:
    if language == "en":
        return texts
    return translate_many(settings, texts, language)  # type: ignore[arg-type]


def _store_advisory(
    settings: AppSettings,
    *,
    farmer_id: str | None,
    mobile: str | None,
    module: str,
    summary: str,
    language: str,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
) -> None:
    if not mobile and not farmer_id:
        return

    try:
        save_advisory(
            settings,
            mobile=mobile,
            farmer_id=farmer_id,
            module=module,
            summary=summary,
            language=language,
            request_payload=request_payload,
            response_payload=response_payload,
        )
    except Exception:
        pass


@lru_cache(maxsize=1)
def _load_crop_artifact(model_path: str) -> dict[str, Any]:
    return joblib.load(model_path)


@lru_cache(maxsize=1)
def _load_disease_artifact(model_path: str) -> dict[str, Any]:
    return joblib.load(model_path)


@lru_cache(maxsize=1)
def _load_fertilizer_artifact(model_path: str) -> dict[str, Any]:
    return joblib.load(model_path)


@lru_cache(maxsize=1)
def _load_irrigation_artifact(model_path: str) -> dict[str, Any]:
    return joblib.load(model_path)


def clear_artifact_cache() -> None:
    _load_crop_artifact.cache_clear()
    _load_disease_artifact.cache_clear()
    _load_fertilizer_artifact.cache_clear()
    _load_irrigation_artifact.cache_clear()


class ModelArtifactsMissing(RuntimeError):
    """Raised when the trained artifacts a request needs are not on disk.

    Deliberately NOT recoverable in-process: training takes ~35 s and 173 MB, so
    doing it on a request (or on container startup) turns a cold start into a
    timeout. Operators either ship the artifacts in the image (the deployed
    path) or run the training entrypoint locally.
    """


def required_artifact_paths(settings: AppSettings) -> list[Path]:
    return [
        settings.model_path,
        settings.metadata_path,
        settings.disease_model_path,
        settings.fertilizer_model_path,
        settings.irrigation_model_path,
    ]


def missing_artifacts(settings: AppSettings) -> list[Path]:
    return [path for path in required_artifact_paths(settings) if not path.is_file()]


def models_ready(settings: AppSettings) -> bool:
    return not missing_artifacts(settings)


def artifacts_missing_message(settings: AppSettings, missing: list[Path]) -> str:
    names = ", ".join(path.name for path in missing)
    return (
        f"Model artifacts are missing from {settings.artifacts_dir}: {names}. "
        "Run `agrotech-train` (or `python -m agrotech_ml.services.train`) to build them, "
        "or point AGROTECH_ARTIFACTS_DIR at a directory that already holds them. "
        "Training is never performed on the request path."
    )


def ensure_model_artifacts(settings: AppSettings) -> None:
    """Verify the artifacts exist under ``AGROTECH_ARTIFACTS_DIR``.

    Never downloads and never trains. Raises :class:`ModelArtifactsMissing`
    with operator instructions when the artifacts cannot be found.
    """
    missing = missing_artifacts(settings)
    if not missing:
        return

    message = artifacts_missing_message(settings, missing)
    logger.error(message)
    raise ModelArtifactsMissing(message)


def run_prediction(payload: SoilWeatherInput, settings: AppSettings, top_k: int = 3) -> PredictionResponse:
    ensure_model_artifacts(settings)

    artifact = _load_crop_artifact(str(settings.model_path))
    model = artifact["model"]
    best_model_name = artifact.get("best_model", "Unknown")
    feature_columns = artifact.get("feature_columns", FEATURE_COLUMNS)

    sample = {feature: float(getattr(payload, feature)) for feature in feature_columns}
    frame = pd.DataFrame([sample], columns=feature_columns)

    probabilities = _predict_proba(model, frame)[0]
    classes = np.asarray(model.classes_) if hasattr(model, "classes_") else np.asarray(artifact["class_labels"])
    ranked_indices = np.argsort(probabilities)[::-1][:top_k]

    recommendations = []
    for idx in ranked_indices:
        crop_name = str(classes[idx])
        recommendations.append(
            PredictionItem(
                crop=crop_name,
                display_crop=localize_crop_name(crop_name, payload.language),
                probability=float(probabilities[idx]),
                confidence=_confidence_band(float(probabilities[idx])),
                agronomy_tip=_localize_text(
                    settings,
                    CROP_TIPS.get(
                        crop_name,
                        "Validate with local agronomist and adjust irrigation-fertilizer schedule.",
                    ),
                    payload.language,
                ),
            )
        )

    actions = _generate_field_actions(settings, payload, recommendations[0].crop)

    response = PredictionResponse(
        recommendations=recommendations,
        field_actions=actions,
        best_model=best_model_name,
        generated_at=datetime.now(UTC),
    )
    _store_advisory(
        settings,
        farmer_id=payload.farmer_id,
        mobile=payload.mobile,
        module="crop",
        summary=f"Top crop recommendation: {recommendations[0].display_crop}",
        language=payload.language,
        request_payload=payload.model_dump(mode="json"),
        response_payload=response.model_dump(mode="json"),
    )
    return response


def _unit_to_acres(land_size: float, unit: str) -> float:
    mapping = {
        "Acres": 1.0,
        "Hectares": 2.47105,
        "Bigha": 0.6198,
        "Katha": 0.031,
    }
    return land_size * mapping.get(unit, 1.0)


def run_irrigation_schedule(payload: IrrigationRequest, settings: AppSettings) -> IrrigationResponse:
    ensure_model_artifacts(settings)
    artifact = _load_irrigation_artifact(str(settings.irrigation_model_path))
    pipeline = artifact["pipeline"]

    acreage = _unit_to_acres(payload.land_size, payload.land_unit)
    features = pd.DataFrame(
        [
            {
                "crop": payload.crop.lower(),
                "soil_type": payload.soil_type.lower(),
                "temperature": payload.temperature,
                "humidity": payload.humidity,
                "rainfall": payload.rainfall,
                "ph": payload.soil_ph,
                "acreage": acreage,
            }
        ]
    )

    water_need_mm = float(pipeline.predict(features)[0])
    days = max(20, payload.term_period_months * 30)

    interval = 6
    if payload.rainfall < 60:
        interval = 4
    elif payload.rainfall > 220:
        interval = 8

    if payload.crop.lower() in {"rice", "banana", "sugarcane"}:
        interval = max(3, interval - 1)

    start = date.today()
    events: list[IrrigationEvent] = []
    current = 0
    while current <= days:
        event_date = start + timedelta(days=current)
        adjusted_water = max(5.0, water_need_mm * (0.95 if current > days * 0.7 else 1.0))
        message = (
            f"Apply approximately {adjusted_water:.1f} mm irrigation for {payload.crop}. "
            f"Consider recent rainfall before irrigating."
        )
        events.append(
            IrrigationEvent(
                date=event_date,
                time="06:00",
                water_mm=round(adjusted_water, 2),
                message=_localize_text(settings, message, payload.language),
            )
        )
        current += interval

    notes = [tr(payload.language, "irrigation_note"), tr(payload.language, "pilot_patch", crop=payload.crop)]
    response = IrrigationResponse(crop=localize_crop_name(payload.crop, payload.language), events=events, notes=notes)
    _store_advisory(
        settings,
        farmer_id=payload.farmer_id,
        mobile=payload.mobile,
        module="irrigation",
        summary=f"Irrigation plan generated for {payload.crop}",
        language=payload.language,
        request_payload=payload.model_dump(mode="json"),
        response_payload=response.model_dump(mode="json"),
    )
    return response


def run_disease_diagnosis(payload: DiseaseRequest, settings: AppSettings) -> DiseaseResponse:
    ensure_model_artifacts(settings)
    artifact = _load_disease_artifact(str(settings.disease_model_path))
    pipeline = artifact["pipeline"]

    probabilities = pipeline.predict_proba([payload.symptoms])[0]
    classes = pipeline.classes_
    best_idx = int(np.argmax(probabilities))
    best_label = str(classes[best_idx])
    confidence = float(probabilities[best_idx])

    content = DISEASE_LIBRARY.get(
        best_label,
        {
            "title": "General Crop Stress",
            "advice": "Monitor crop for 3-4 days and consult local expert with photos.",
            "actions": ["Keep field records", "Avoid over-irrigation", "Use local extension support"],
            "severity": "low",
        },
    )

    response = DiseaseResponse(
        disease=_localize_text(settings, content["title"], payload.language),
        confidence=confidence,
        severity=content["severity"],
        advice=_localize_text(settings, content["advice"], payload.language),
        preventive_actions=_localize_texts(settings, list(content["actions"]), payload.language),
    )
    _store_advisory(
        settings,
        farmer_id=payload.farmer_id,
        mobile=payload.mobile,
        module="disease",
        summary=f"Disease diagnosis: {response.disease}",
        language=payload.language,
        request_payload=payload.model_dump(mode="json"),
        response_payload=response.model_dump(mode="json"),
    )
    return response


def run_fertilizer_recommendation(payload: FertilizerRequest, settings: AppSettings) -> FertilizerResponse:
    ensure_model_artifacts(settings)
    artifact = _load_fertilizer_artifact(str(settings.fertilizer_model_path))
    pipeline = artifact["pipeline"]

    frame = pd.DataFrame(
        [
            {
                "crop": payload.crop.lower(),
                "soil_type": payload.soil_type.lower(),
                "N": payload.N,
                "P": payload.P,
                "K": payload.K,
                "ph": payload.ph,
            }
        ]
    )
    label = str(pipeline.predict(frame)[0])

    blend = FERTILIZER_LIBRARY.get(label, "Balanced NPK maintenance dose")
    nutrient_gap = []
    if payload.N < 45:
        nutrient_gap.append("Nitrogen")
    if payload.P < 35:
        nutrient_gap.append("Phosphorus")
    if payload.K < 35:
        nutrient_gap.append("Potassium")

    rationale = (
        f"Recommended blend: {blend}. "
        f"Observed nutrient focus: {', '.join(nutrient_gap) if nutrient_gap else 'balanced profile'}"
    )

    schedule = [
        "Day 0: Apply 40% basal dose during field preparation.",
        "Day 20: Apply 30% top dressing with irrigation.",
        "Day 40: Apply remaining dose after field scouting.",
    ]

    response = FertilizerResponse(
        blend=_localize_text(settings, blend, payload.language),
        rationale=_localize_text(settings, rationale, payload.language),
        schedule=_localize_texts(settings, schedule, payload.language),
    )
    _store_advisory(
        settings,
        farmer_id=payload.farmer_id,
        mobile=payload.mobile,
        module="fertilizer",
        summary=f"Fertilizer blend recommended for {payload.crop}",
        language=payload.language,
        request_payload=payload.model_dump(mode="json"),
        response_payload=response.model_dump(mode="json"),
    )
    return response


def run_soil_analysis(payload: SoilAnalysisRequest, settings: AppSettings) -> SoilAnalysisResponse:
    nutrient_alerts: list[str] = []
    soil_actions: list[str] = []
    recommended_focus: list[str] = []

    if payload.N < 45:
        nutrient_alerts.append("Nitrogen is below the recommended operating range.")
        recommended_focus.append("Split nitrogen application")
    if payload.P < 35:
        nutrient_alerts.append("Phosphorus is low and may limit root development.")
        recommended_focus.append("Basal phosphorus support")
    if payload.K < 35:
        nutrient_alerts.append("Potassium is low and may reduce crop resilience.")
        recommended_focus.append("Potash enrichment")

    if payload.ph < 5.8:
        soil_status = "Acidic soil"
        soil_actions.append("Apply lime in calibrated doses before the next sowing window.")
    elif payload.ph > 7.8:
        soil_status = "Alkaline soil"
        soil_actions.append("Add organic matter and gypsum after local agronomy validation.")
    else:
        soil_status = "Balanced soil reaction"
        soil_actions.append("Maintain current pH range with compost and residue management.")

    soil_actions.append(f"Use {payload.soil_type} soil management practices for {payload.crop}.")
    if not nutrient_alerts:
        nutrient_alerts.append("Major NPK values are within a workable range for planning.")
        recommended_focus.append("Balanced NPK maintenance")

    response = SoilAnalysisResponse(
        soil_health_status=_localize_text(settings, soil_status, payload.language),
        nutrient_alerts=_localize_texts(settings, nutrient_alerts, payload.language),
        soil_actions=_localize_texts(settings, soil_actions, payload.language),
        recommended_crop_focus=_localize_texts(settings, recommended_focus, payload.language),
        generated_at=datetime.now(UTC),
    )
    _store_advisory(
        settings,
        farmer_id=payload.farmer_id,
        mobile=payload.mobile,
        module="soil",
        summary=f"Soil analysis generated for {payload.crop}",
        language=payload.language,
        request_payload=payload.model_dump(mode="json"),
        response_payload=response.model_dump(mode="json"),
    )
    return response

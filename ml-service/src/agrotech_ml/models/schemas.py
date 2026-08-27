from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


LanguageCode = Literal[
    "en", "hi", "bn", "te", "ta", "mr", "gu", "kn", "ml", "pa", "or"
]


class LocalEvidence(BaseModel):
    """District-level evidence for a recommended crop, from the APY returns."""

    grown_locally: bool = True
    season: str
    area_ha: float | None = None
    median_yield: float | None = None
    yield_unit: str = "t/ha"
    rank_in_district: int | None = None
    why: str = ""


class SoilWeatherInput(BaseModel):
    N: float = Field(..., ge=0, le=200)
    P: float = Field(..., ge=0, le=200)
    K: float = Field(..., ge=0, le=250)
    temperature: float = Field(..., ge=-5, le=55)
    humidity: float = Field(..., ge=0, le=100)
    ph: float = Field(..., ge=2.5, le=10.5)
    rainfall: float = Field(..., ge=0, le=500)
    farmer_id: str | None = None
    mobile: str | None = None
    language: LanguageCode = "en"
    # Optional: when the farmer's district is known the response carries local
    # evidence for each crop. Absent them the endpoint behaves exactly as before.
    state: str | None = None
    district: str | None = None
    season: str | None = None


class PredictionItem(BaseModel):
    crop: str
    display_crop: str
    probability: float = Field(..., ge=0, le=1)
    confidence: Literal["high", "medium", "low"]
    agronomy_tip: str
    # Populated only when state/district were supplied on the request.
    local: LocalEvidence | None = None


class PredictionResponse(BaseModel):
    recommendations: list[PredictionItem]
    field_actions: list[str]
    best_model: str
    generated_at: datetime
    local_crops: dict | None = None


class ModelScore(BaseModel):
    model_name: str
    accuracy: float
    macro_f1: float
    top3_accuracy: float
    training_seconds: float


class FeatureImportance(BaseModel):
    feature: str
    importance: float


class SkippedModel(BaseModel):
    model_name: str
    reason: str


class ModelMetadata(BaseModel):
    trained_at: datetime
    dataset_rows: int
    best_model: str
    feature_columns: list[str]
    model_scores: list[ModelScore]
    feature_importance: list[FeatureImportance]
    skipped_models: list[SkippedModel] = []
    auxiliary_models: dict[str, str] = {}


class IrrigationRequest(BaseModel):
    farmer_name: str = Field(..., min_length=1)
    location: str = Field(..., min_length=1)
    crop: str = Field(..., min_length=1)
    land_size: float = Field(..., gt=0)
    land_unit: Literal["Katha", "Bigha", "Acres", "Hectares"] = "Acres"
    term_period_months: int = Field(3, ge=1, le=18)
    temperature: float = Field(25, ge=-5, le=55)
    humidity: float = Field(65, ge=0, le=100)
    rainfall: float = Field(100, ge=0, le=500)
    soil_type: str = "loam"
    soil_ph: float = Field(6.7, ge=2.5, le=10.5)
    farmer_id: str | None = None
    mobile: str | None = None
    language: LanguageCode = "en"


class IrrigationEvent(BaseModel):
    date: date
    time: str
    water_mm: float
    message: str


class IrrigationResponse(BaseModel):
    crop: str
    events: list[IrrigationEvent]
    notes: list[str]


class DiseaseRequest(BaseModel):
    crop: str = Field(..., min_length=1)
    symptoms: str = Field(..., min_length=4)
    image_hint: str | None = None
    farmer_id: str | None = None
    mobile: str | None = None
    language: LanguageCode = "en"


class DiseaseResponse(BaseModel):
    disease: str
    confidence: float = Field(..., ge=0, le=1)
    severity: Literal["low", "moderate", "high"]
    advice: str
    preventive_actions: list[str]
    # Additive fields: explicit treatment and prevention guidance sourced from
    # the curated disease dataset (data/disease_symptoms.csv). ``advice`` keeps
    # carrying the treatment text so existing clients see no change.
    treatment: str | None = None
    prevention: list[str] = []
    source: str | None = None


class FertilizerRequest(BaseModel):
    crop: str = Field(..., min_length=1)
    soil_type: str = "loam"
    N: float = Field(..., ge=0, le=250)
    P: float = Field(..., ge=0, le=250)
    K: float = Field(..., ge=0, le=250)
    ph: float = Field(..., ge=2.5, le=10.5)
    farmer_id: str | None = None
    mobile: str | None = None
    language: LanguageCode = "en"


class FertilizerResponse(BaseModel):
    blend: str
    rationale: str
    schedule: list[str]


class WeatherRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    days: int = Field(7, ge=1, le=10)


class WeatherDay(BaseModel):
    date: date
    min_temp: float
    max_temp: float
    rain_mm: float
    humidity: float


class WeatherResponse(BaseModel):
    latitude: float
    longitude: float
    current_temp: float
    current_wind_kph: float
    daily: list[WeatherDay]
    soil_hint: str


class SchemeRecommendationRequest(BaseModel):
    farmer_type: Literal["small", "marginal", "medium", "large"] = "small"
    land_size_acres: float = Field(2.0, ge=0)
    annual_income_lakh: float = Field(2.0, ge=0)
    state: str = "India"
    farmer_id: str | None = None
    mobile: str | None = None
    language: LanguageCode = "en"


class SchemeItem(BaseModel):
    id: str
    title: str
    description: str
    eligibility: str
    link: str
    source: str | None = None
    # Additive: step-by-step application instructions from the committed
    # offline catalogue (data/schemes_catalog.json). Empty for live results.
    how_to_apply: list[str] = []


class SchemeResponse(BaseModel):
    schemes: list[SchemeItem]
    # Additive fields: where the recommendations came from, so the UI can say
    # "from the official catalog" instead of silently rendering an empty list.
    # ``source`` is a machine label ("myscheme_live", "official_catalog",
    # "myscheme_live+official_catalog"); ``note`` is a human sentence.
    source: str | None = None
    note: str | None = None


class MarketPriceItem(BaseModel):
    crop: str
    mandi: str
    state: str
    modal_price_inr_quintal: float
    trend: Literal["up", "down", "stable"]
    arrival_date: date | None = None
    source_url: str | None = None


class RentalTool(BaseModel):
    name: str
    hourly_rate_inr: float | None = None
    provider: str
    location: str
    availability: str
    service_type: str | None = None
    source_url: str | None = None


class InvestorOpportunity(BaseModel):
    title: str
    expected_irr_percent: float | None = None
    minimum_ticket_inr: int | None = None
    tenure_months: int | None = None
    focus_area: str
    provider: str | None = None
    summary: str | None = None
    source_url: str | None = None


class KnowledgeArticle(BaseModel):
    id: str
    category: Literal["production", "treatment", "horticulture", "soil", "market"]
    title: str
    summary: str
    url: str | None = None
    source: str | None = None
    # Additive: step-by-step guidance from the committed local library
    # (data/knowledge_library.json). Empty for live web results.
    body_points: list[str] = []


class UserProfileCreate(BaseModel):
    farmer_id: str | None = None
    name: str
    mobile: str
    state: str | None = None
    district: str | None = None
    language: LanguageCode = "en"


class UserProfile(BaseModel):
    id: str
    farmer_id: str
    name: str
    mobile: str
    state: str | None = None
    district: str | None = None
    language: LanguageCode
    created_at: datetime


class FarmProfileCreate(BaseModel):
    farmer_id: str | None = None
    mobile: str
    farm_name: str
    village: str
    state: str
    acres: float
    primary_crop: str
    district: str | None = None
    soil_type: str | None = None
    irrigation_source: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class FarmProfile(BaseModel):
    id: str
    farmer_id: str | None = None
    mobile: str
    farm_name: str
    village: str
    state: str
    acres: float
    primary_crop: str
    district: str | None = None
    soil_type: str | None = None
    irrigation_source: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    created_at: datetime


class DashboardSummary(BaseModel):
    active_users: int
    total_farms: int
    listed_tools: int
    investor_deals: int
    available_languages: int
    saved_assets: int = 0
    advisory_runs: int = 0
    translation_enabled: bool = False
    live_search_enabled: bool = False
    live_market_enabled: bool = False
    live_scheme_enabled: bool = False
    write_auth_enabled: bool = False
    audit_logging_enabled: bool = False


class UploadAsset(BaseModel):
    id: str
    farmer_id: str | None = None
    mobile: str
    module: str
    filename: str
    content_type: str
    size_bytes: int
    notes: str | None = None
    url: str
    created_at: datetime


class UploadResponse(BaseModel):
    asset: UploadAsset


class AdvisoryRecord(BaseModel):
    id: str
    farmer_id: str | None = None
    mobile: str
    module: str
    summary: str
    language: LanguageCode
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    created_at: datetime


class SearchResultItem(BaseModel):
    title: str
    summary: str
    url: str
    source: str
    published_at: datetime | None = None


class NewsItem(BaseModel):
    title: str
    summary: str
    url: str
    source: str
    published_at: datetime | None = None
    # Additive: True when this row is served from the committed evergreen
    # fallback (official portals) because the live news feed was unavailable.
    is_fallback: bool = False


class LocationSearchItem(BaseModel):
    name: str
    admin1: str | None = None
    admin2: str | None = None
    country: str
    latitude: float
    longitude: float


class FarmerSearchResult(BaseModel):
    farmer_id: str
    name: str
    mobile: str
    state: str | None = None
    district: str | None = None
    village: str | None = None
    primary_crop: str | None = None
    acres: float | None = None


class FarmerWorkspace(BaseModel):
    profile: UserProfile
    farms: list[FarmProfile]
    uploads: list[UploadAsset]
    advisories: list[AdvisoryRecord]


class SoilAnalysisRequest(BaseModel):
    N: float = Field(..., ge=0, le=250)
    P: float = Field(..., ge=0, le=250)
    K: float = Field(..., ge=0, le=250)
    ph: float = Field(..., ge=2.5, le=10.5)
    soil_type: str = "loam"
    crop: str = Field(..., min_length=1)
    farmer_id: str | None = None
    mobile: str | None = None
    language: LanguageCode = "en"


class SoilAnalysisResponse(BaseModel):
    soil_health_status: str
    nutrient_alerts: list[str]
    soil_actions: list[str]
    recommended_crop_focus: list[str]
    generated_at: datetime


class AuthTokenRequest(BaseModel):
    username: str
    password: str


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in_seconds: int
    username: str


RetrainState = Literal["idle", "queued", "running", "succeeded", "failed"]


class RetrainStatus(BaseModel):
    """State of the background model-training job.

    Training regenerates ~173 MB of artifacts and pegs a CPU for ~35 s, so it
    never runs on the request path. ``POST /retrain`` queues it and returns
    immediately; poll ``GET /retrain/status`` for progress.
    """

    status: RetrainState = "idle"
    job_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    detail: str | None = None
    best_model: str | None = None


class AuditLog(BaseModel):
    id: str
    request_id: str
    actor_type: str
    actor_id: str | None = None
    action: str
    path: str
    method: str
    status_code: int
    ip_address: str | None = None
    user_agent: str | None = None
    message: str | None = None
    metadata: dict[str, Any] = {}
    created_at: datetime

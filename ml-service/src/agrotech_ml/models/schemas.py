from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


LanguageCode = Literal[
    "en", "hi", "bn", "te", "ta", "mr", "gu", "kn", "ml", "pa", "or"
]


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


class PredictionItem(BaseModel):
    crop: str
    display_crop: str
    probability: float = Field(..., ge=0, le=1)
    confidence: Literal["high", "medium", "low"]
    agronomy_tip: str


class PredictionResponse(BaseModel):
    recommendations: list[PredictionItem]
    field_actions: list[str]
    best_model: str
    generated_at: datetime


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


class SchemeResponse(BaseModel):
    schemes: list[SchemeItem]


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

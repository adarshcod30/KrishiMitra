from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from agrotech_ml.services.data_service import (
    add_farm,
    fetch_news_feed,
    fetch_weather,
    get_user,
    list_advisories,
    list_farms,
    list_uploads,
    localize_investor_opportunities,
    localize_knowledge_library,
    localize_market_prices,
    localize_rental_tools,
    recommend_schemes,
    search_knowledge,
    search_locations,
    summary,
    upsert_user,
)
from agrotech_ml.core.i18n import LANGUAGE_LABELS
from agrotech_ml.services.inference import (
    clear_artifact_cache,
    ensure_model_artifacts,
    run_disease_diagnosis,
    run_fertilizer_recommendation,
    run_irrigation_schedule,
    run_prediction,
    run_soil_analysis,
)
from agrotech_ml.models.schemas import (
    AdvisoryRecord,
    DashboardSummary,
    DiseaseRequest,
    DiseaseResponse,
    FarmProfile,
    FarmProfileCreate,
    FertilizerRequest,
    FertilizerResponse,
    InvestorOpportunity,
    IrrigationRequest,
    IrrigationResponse,
    KnowledgeArticle,
    LanguageCode,
    LocationSearchItem,
    MarketPriceItem,
    ModelMetadata,
    NewsItem,
    PredictionResponse,
    RentalTool,
    SchemeRecommendationRequest,
    SchemeResponse,
    SearchResultItem,
    SoilAnalysisRequest,
    SoilAnalysisResponse,
    SoilWeatherInput,
    FarmerSearchResult,
    FarmerWorkspace,
    UploadAsset,
    UploadResponse,
    UserProfile,
    UserProfileCreate,
    WeatherResponse,
)
from agrotech_ml.core.settings import get_settings
from agrotech_ml.db.storage import get_farmer_workspace, resolve_mobile, save_upload, search_users
from agrotech_ml.services.training import load_metadata, train_models

settings = get_settings()

app = FastAPI(
    title="AgroTech Unified Farmer API",
    description="Multi-dashboard farmer platform API with crop, weather, schemes, market and advisory services",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static/uploads", StaticFiles(directory=str(settings.uploads_dir)), name="uploads")


@app.on_event("startup")
def warmup_models() -> None:
    ensure_model_artifacts(settings)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "agrotech-unified-api"}


@app.get("/languages")
def languages() -> dict[str, dict[str, str]]:
    return {"languages": LANGUAGE_LABELS}


@app.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard() -> DashboardSummary:
    return summary(settings)


@app.get("/metadata", response_model=ModelMetadata)
def metadata() -> ModelMetadata:
    try:
        ensure_model_artifacts(settings)
        return load_metadata(settings)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/predict", response_model=PredictionResponse)
def predict(payload: SoilWeatherInput) -> PredictionResponse:
    try:
        return run_prediction(payload=payload, settings=settings)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/irrigation/schedule", response_model=IrrigationResponse)
def irrigation_schedule(payload: IrrigationRequest) -> IrrigationResponse:
    try:
        return run_irrigation_schedule(payload=payload, settings=settings)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/disease/diagnose", response_model=DiseaseResponse)
def diagnose(payload: DiseaseRequest) -> DiseaseResponse:
    try:
        return run_disease_diagnosis(payload=payload, settings=settings)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/fertilizer/recommend", response_model=FertilizerResponse)
def fertilizer_recommend(payload: FertilizerRequest) -> FertilizerResponse:
    try:
        return run_fertilizer_recommendation(payload=payload, settings=settings)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/soil/analyze", response_model=SoilAnalysisResponse)
def soil_analyze(payload: SoilAnalysisRequest) -> SoilAnalysisResponse:
    try:
        return run_soil_analysis(payload=payload, settings=settings)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/weather/forecast", response_model=WeatherResponse)
async def weather_forecast(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    language: LanguageCode = Query("en"),
    days: int = Query(7, ge=1, le=10),
) -> WeatherResponse:
    try:
        return await fetch_weather(
            settings,
            latitude=latitude,
            longitude=longitude,
            language=language,
            days=days,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/locations/search", response_model=list[LocationSearchItem])
async def location_search(q: str = Query(..., min_length=2)) -> list[LocationSearchItem]:
    try:
        return await search_locations(q)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/search/knowledge", response_model=list[SearchResultItem])
async def knowledge_search(
    query: str = Query(..., min_length=2),
    language: LanguageCode = Query("en"),
    limit: int = Query(6, ge=1, le=10),
) -> list[SearchResultItem]:
    try:
        return await search_knowledge(settings, query=query, language=language, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/news/feed", response_model=list[NewsItem])
async def news_feed(
    query: str = Query("agriculture India farming"),
    language: LanguageCode = Query("en"),
    limit: int = Query(6, ge=1, le=10),
) -> list[NewsItem]:
    try:
        return await fetch_news_feed(settings, query=query, language=language, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/schemes/recommend", response_model=SchemeResponse)
def schemes(payload: SchemeRecommendationRequest) -> SchemeResponse:
    return SchemeResponse(schemes=recommend_schemes(settings, payload))


@app.get("/market/prices", response_model=list[MarketPriceItem])
def market_prices(
    language: LanguageCode = Query("en"),
    crop: str | None = Query(None),
    state: str | None = Query(None),
) -> list[MarketPriceItem]:
    return localize_market_prices(settings, language, crop=crop, state=state)


@app.get("/rentals/tools", response_model=list[RentalTool])
def rental_tools(
    language: LanguageCode = Query("en"),
    location: str | None = Query(None),
) -> list[RentalTool]:
    return localize_rental_tools(settings, language, location=location)


@app.get("/investor/opportunities", response_model=list[InvestorOpportunity])
def investor_opportunities(language: LanguageCode = Query("en")) -> list[InvestorOpportunity]:
    return localize_investor_opportunities(settings, language)


@app.get("/knowledge/library", response_model=list[KnowledgeArticle])
async def knowledge_library(
    language: LanguageCode = Query("en"),
    query: str | None = Query(None),
) -> list[KnowledgeArticle]:
    return await localize_knowledge_library(settings, language, query=query)


@app.post("/profiles/user", response_model=UserProfile)
def save_user(payload: UserProfileCreate) -> UserProfile:
    try:
        return upsert_user(settings, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/profiles/user/{mobile}", response_model=UserProfile)
def fetch_user(mobile: str) -> UserProfile:
    user = get_user(settings, mobile)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.get("/profiles/search", response_model=list[FarmerSearchResult])
def search_profiles(
    q: str = Query(..., min_length=2),
    limit: int = Query(8, ge=1, le=20),
) -> list[FarmerSearchResult]:
    return search_users(settings, q, limit=limit)


@app.get("/profiles/workspace/{farmer_id}", response_model=FarmerWorkspace)
def fetch_workspace(farmer_id: str) -> FarmerWorkspace:
    workspace = get_farmer_workspace(settings, farmer_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Farmer not found")
    return workspace


@app.post("/profiles/farms", response_model=FarmProfile)
def save_farm(payload: FarmProfileCreate) -> FarmProfile:
    return add_farm(settings, payload)


@app.get("/profiles/farms/{mobile}", response_model=list[FarmProfile])
def fetch_farms(mobile: str) -> list[FarmProfile]:
    return list_farms(settings, mobile)


@app.post("/uploads/assets", response_model=UploadResponse)
async def upload_asset(
    mobile: str | None = Form(None),
    farmer_id: str | None = Form(None),
    module: str = Form(...),
    notes: str | None = Form(None),
    file: UploadFile = File(...),
) -> UploadResponse:
    resolved_mobile = mobile or (resolve_mobile(settings, farmer_id) if farmer_id else None)
    if not resolved_mobile or not get_user(settings, resolved_mobile):
        raise HTTPException(status_code=400, detail="Save the farmer profile before uploading files.")

    original_name = Path(file.filename or "upload.bin").name
    extension = Path(original_name).suffix.lower()
    stored_name = f"{uuid4()}{extension}"
    destination = settings.uploads_dir / stored_name

    content = await file.read()
    destination.write_bytes(content)

    asset = save_upload(
        settings,
        mobile=resolved_mobile,
        farmer_id=farmer_id,
        module=module,
        filename=original_name,
        stored_name=stored_name,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        notes=notes,
    )
    return UploadResponse(asset=asset)


@app.get("/uploads/assets/{mobile}", response_model=list[UploadAsset])
def fetch_assets(mobile: str, module: str | None = Query(None)) -> list[UploadAsset]:
    return list_uploads(settings, mobile, module=module)


@app.get("/advisories/history/{mobile}", response_model=list[AdvisoryRecord])
def advisory_history(
    mobile: str,
    module: str | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
) -> list[AdvisoryRecord]:
    return list_advisories(settings, mobile, module=module, limit=limit)


@app.post("/retrain", response_model=ModelMetadata)
def retrain() -> ModelMetadata:
    try:
        metadata = train_models(settings)
        clear_artifact_cache()
        return metadata
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def main() -> None:
    import uvicorn

    uvicorn.run("agrotech_ml.api:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()

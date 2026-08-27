from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from agrotech_ml.services.data_service import (
    MAX_SEARCH_RESULTS,
    MIN_SEARCH_QUERY_LENGTH,
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
    search_farmers,
    search_knowledge,
    search_locations,
    summary,
    upsert_user,
)
from agrotech_ml.core.auth import AuthContext, login, require_auth
from agrotech_ml.core.i18n import LANGUAGE_LABELS
from agrotech_ml.services.inference import (
    ModelArtifactsMissing,
    artifacts_missing_message,
    ensure_model_artifacts,
    missing_artifacts,
    models_ready,
    run_disease_diagnosis,
    run_fertilizer_recommendation,
    run_irrigation_schedule,
    run_prediction,
    run_soil_analysis,
    warm_models,
)
from agrotech_ml.models.schemas import (
    AdvisoryRecord,
    AuthTokenRequest,
    AuthTokenResponse,
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
    RetrainStatus,
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
from agrotech_ml.db.storage import get_farmer_workspace, resolve_mobile, save_upload
from agrotech_ml.services import crop_suitability, leaf_diagnosis, market_insights, retrain_job, shc_baselines
from agrotech_ml.services.training import load_metadata
from agrotech_ml.services.upload_service import (
    OCTET_STREAM,
    read_within_limit,
    validate_content_type,
    UnsupportedUploadType,
    UploadStorageUnavailable,
    UploadTooLarge,
    content_disposition_for,
    content_type_for_stored_name,
    is_valid_stored_name,
    s3_object_name,
    store_upload,
)

logger = logging.getLogger(__name__)

settings = get_settings()

# Guard every route that mutates state or touches farmer PII. When
# AGROTECH_REQUIRE_WRITE_AUTH is false (the local default) this resolves to an
# anonymous context and changes nothing.
Auth = Depends(require_auth)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Model artifacts are baked into the image under AGROTECH_ARTIFACTS_DIR.
    # Nothing is downloaded and nothing is trained here: training costs ~35 s of
    # CPU and would turn every cold start into a startup-probe failure.
    missing = missing_artifacts(settings)
    if missing:
        logger.error(artifacts_missing_message(settings, missing))
    else:
        logger.info("Model artifacts ready in %s", settings.artifacts_dir)

    yield


app = FastAPI(
    title="AgroTech Unified Farmer API",
    description="Multi-dashboard farmer platform API with crop, weather, schemes, market and advisory services",
    version="3.0.0",
    lifespan=lifespan,
)


def _cors_configuration() -> tuple[list[str], bool]:
    """Resolve allowed origins from settings, never pairing '*' with credentials."""
    origins = settings.cors_origins_list
    if not origins:
        logger.warning("AGROTECH_CORS_ORIGINS is empty; browser cross-origin calls will be blocked.")
        return [], False
    if "*" in origins:
        # A wildcard with allow_credentials is rejected by browsers and would
        # let any site read authenticated responses. Drop credentials instead.
        logger.warning("AGROTECH_CORS_ORIGINS contains '*'; disabling credentialed CORS.")
        return ["*"], False
    return origins, True


_cors_origins, _cors_credentials = _cors_configuration()

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _model_dependency_error(exc: ModelArtifactsMissing) -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


# ---------------------------------------------------------------------------
# Health, metadata and auth
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "agrotech-unified-api",
        "environment": settings.environment,
        "models_ready": models_ready(settings),
        "write_auth_required": settings.require_write_auth,
    }


@app.get("/warmup")
def warmup(background_tasks: BackgroundTasks) -> dict[str, object]:
    """Keep-alive ping for free-tier hosts that spin the instance down.

    No auth and instant response by design: an external pinger (cron, uptime
    monitor) hits this every few minutes so the container stays warm. Model
    artifacts are loaded lazily in a background task, so the first real
    request after a cold start finds them already in memory.
    """
    background_tasks.add_task(warm_models, settings)
    return {
        "status": "ok",
        "service": "agrotech-unified-api",
        "models_ready": models_ready(settings),
        "warming": "scheduled",
    }


@app.get("/languages")
def languages() -> dict[str, dict[str, str]]:
    return {"languages": LANGUAGE_LABELS}


@app.post("/auth/login", response_model=AuthTokenResponse)
def auth_login(payload: AuthTokenRequest) -> AuthTokenResponse:
    token, expires_in = login(settings, payload.username, payload.password)
    return AuthTokenResponse(
        access_token=token,
        expires_in_seconds=expires_in,
        username=payload.username,
    )


@app.get("/auth/me")
def auth_me(auth: AuthContext = Auth) -> dict[str, object]:
    return {
        "authenticated": auth.authenticated,
        "subject": auth.subject,
        "role": auth.role,
        "write_auth_required": auth.enforced,
    }


@app.get("/dashboard/summary", response_model=DashboardSummary)
async def dashboard() -> DashboardSummary:
    return await summary(settings)


@app.get("/metadata", response_model=ModelMetadata)
def metadata() -> ModelMetadata:
    try:
        ensure_model_artifacts(settings)
        return load_metadata(settings)
    except ModelArtifactsMissing as exc:
        raise _model_dependency_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Advisory / inference routes
# ---------------------------------------------------------------------------


def _predict_impl(payload: SoilWeatherInput) -> PredictionResponse:
    try:
        return run_prediction(payload=payload, settings=settings)
    except ModelArtifactsMissing as exc:
        raise _model_dependency_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/predict", response_model=PredictionResponse)
def predict(payload: SoilWeatherInput, auth: AuthContext = Auth) -> PredictionResponse:
    return _predict_impl(payload)


@app.post("/predict/crop", response_model=PredictionResponse)
def predict_crop(payload: SoilWeatherInput, auth: AuthContext = Auth) -> PredictionResponse:
    """Documented alias for :func:`predict` - both paths behave identically."""
    return _predict_impl(payload)


@app.post("/irrigation/schedule", response_model=IrrigationResponse)
def irrigation_schedule(
    payload: IrrigationRequest, auth: AuthContext = Auth
) -> IrrigationResponse:
    try:
        return run_irrigation_schedule(payload=payload, settings=settings)
    except ModelArtifactsMissing as exc:
        raise _model_dependency_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/disease/diagnose", response_model=DiseaseResponse)
def diagnose(payload: DiseaseRequest, auth: AuthContext = Auth) -> DiseaseResponse:
    try:
        return run_disease_diagnosis(payload=payload, settings=settings)
    except ModelArtifactsMissing as exc:
        raise _model_dependency_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/fertilizer/recommend", response_model=FertilizerResponse)
def fertilizer_recommend(
    payload: FertilizerRequest, auth: AuthContext = Auth
) -> FertilizerResponse:
    try:
        return run_fertilizer_recommendation(payload=payload, settings=settings)
    except ModelArtifactsMissing as exc:
        raise _model_dependency_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/soil/analyze", response_model=SoilAnalysisResponse)
def soil_analyze(
    payload: SoilAnalysisRequest, auth: AuthContext = Auth
) -> SoilAnalysisResponse:
    try:
        return run_soil_analysis(payload=payload, settings=settings)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Public reference data
# ---------------------------------------------------------------------------


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
        raise HTTPException(status_code=502, detail=f"Weather provider unavailable: {exc}") from exc


@app.get("/locations/search", response_model=list[LocationSearchItem])
async def location_search(q: str = Query(..., min_length=2)) -> list[LocationSearchItem]:
    try:
        return await search_locations(q)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Geocoding provider unavailable: {exc}") from exc


@app.get("/search/knowledge", response_model=list[SearchResultItem])
async def knowledge_search(
    query: str = Query(..., min_length=2),
    language: LanguageCode = Query("en"),
    limit: int = Query(6, ge=1, le=10),
) -> list[SearchResultItem]:
    try:
        return await search_knowledge(settings, query=query, language=language, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Search provider unavailable: {exc}") from exc


@app.get("/news/feed", response_model=list[NewsItem])
async def news_feed(
    query: str = Query("agriculture India farming"),
    language: LanguageCode = Query("en"),
    limit: int = Query(6, ge=1, le=10),
) -> list[NewsItem]:
    try:
        return await fetch_news_feed(settings, query=query, language=language, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"News provider unavailable: {exc}") from exc


@app.post("/schemes/recommend", response_model=SchemeResponse)
def schemes(
    payload: SchemeRecommendationRequest, auth: AuthContext = Auth
) -> SchemeResponse:
    """Scheme recommendations with a source note.

    Never silently empty: live MyScheme results (when an API key is
    configured) are merged with the committed, verified offline catalogue,
    and the response says which source produced the list.
    """
    return recommend_schemes(settings, payload)


@app.get("/market/prices", response_model=list[MarketPriceItem])
def market_prices(
    language: LanguageCode = Query("en"),
    crop: str | None = Query(None),
    state: str | None = Query(None),
) -> list[MarketPriceItem]:
    """Live mandi prices, falling back to the committed sample snapshot.

    Always 200: the service layer swallows upstream failures and serves
    ``data/market_prices_sample.csv`` instead.
    """
    items = localize_market_prices(settings, language, crop=crop, state=state)
    # Attach "typical for this month" context where two years of Agmarknet
    # history cover the commodity; other rows stay untouched.
    for item in items:
        context = market_insights.context_for(
            item.crop, item.state, item.modal_price_inr_quintal
        )
        if context:
            item.typical_min = context.get("typical_min")
            item.typical_max = context.get("typical_max")
            item.season_note = context.get("season_note")
            item.price_note = context.get("price_note")
    return items


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
    try:
        return await localize_knowledge_library(settings, language, query=query)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Knowledge provider unavailable: {exc}") from exc


# ---------------------------------------------------------------------------
# Farmer profiles (PII - always behind require_auth)
# ---------------------------------------------------------------------------


@app.post("/profiles/user", response_model=UserProfile)
def save_user(payload: UserProfileCreate, auth: AuthContext = Auth) -> UserProfile:
    try:
        return upsert_user(settings, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/profiles/user/{mobile}", response_model=UserProfile)
def fetch_user(mobile: str, auth: AuthContext = Auth) -> UserProfile:
    user = get_user(settings, mobile)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.get("/profiles/search", response_model=list[FarmerSearchResult])
def search_profiles(
    q: str = Query(..., min_length=MIN_SEARCH_QUERY_LENGTH, max_length=64),
    limit: int = Query(8, ge=1, le=MAX_SEARCH_RESULTS),
    auth: AuthContext = Auth,
) -> list[FarmerSearchResult]:
    """Directory lookup, not an export.

    A minimum query length, a hard result cap and prefix-only mobile matching
    keep this from dumping the farmer table for a two-character query.
    """
    try:
        return search_farmers(settings, q, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/profiles/workspace/{farmer_id}", response_model=FarmerWorkspace)
def fetch_workspace(farmer_id: str, auth: AuthContext = Auth) -> FarmerWorkspace:
    workspace = get_farmer_workspace(settings, farmer_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Farmer not found")
    return workspace


@app.post("/profiles/farms", response_model=FarmProfile)
def save_farm(payload: FarmProfileCreate, auth: AuthContext = Auth) -> FarmProfile:
    try:
        return add_farm(settings, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/profiles/farms/{mobile}", response_model=list[FarmProfile])
def fetch_farms(mobile: str, auth: AuthContext = Auth) -> list[FarmProfile]:
    return list_farms(settings, mobile)


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------


@app.get("/soil/baseline")
def soil_baseline(
    state: str = Query(..., min_length=2),
    district: str = Query(..., min_length=2),
    auth: AuthContext = Auth,
) -> dict:
    """Typical soil profile for a district, from Soil Health Card samples.

    Lets the Soil Check form start from the district's real tested profile when
    a farmer has no lab report, and gives their own numbers local context.
    Returns {"matched": false} when the district has no SHC samples.
    """
    baseline = shc_baselines.baseline_for(state, district)
    if baseline is None:
        return {"matched": False, "source": shc_baselines.SOURCE_NOTE}
    return {"matched": True, **baseline}


@app.get("/crops/local")
def local_crops(
    state: str = Query(..., min_length=2),
    district: str = Query(..., min_length=2),
    season: str | None = Query(None),
    limit: int = Query(6, ge=1, le=20),
    auth: AuthContext = Auth,
) -> dict:
    """Crops proven to yield well in this district, from government returns.

    Complements POST /predict: that answers "what suits these soil numbers",
    this answers "what actually grows here". Returns an empty list with
    matched=false when the district is absent, so the UI can say so plainly
    instead of showing nothing.
    """
    return crop_suitability.recommend(state, district, season, limit)


@app.post("/disease/diagnose/photo", response_model=DiseaseResponse)
async def diagnose_disease_photo(
    crop: str = Form(...),
    language: LanguageCode = Form("en"),
    symptoms: str | None = Form(None),
    file: UploadFile = File(...),
    auth: AuthContext = Auth,
) -> DiseaseResponse:
    """Diagnose from a leaf photograph, falling back to the text model.

    The photo classifier only covers the crops it was trained on, so when it is
    unavailable or unsure we defer to the symptom text rather than guessing:
    a confident wrong answer costs a farmer a spray they did not need.
    """
    content_type = validate_content_type(settings, file.content_type)
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Upload a photo of the affected leaf.")

    image_bytes = await read_within_limit(settings, file)
    prediction = leaf_diagnosis.predict(settings, image_bytes)

    if prediction is None or not prediction["confident"]:
        if not symptoms or len(symptoms.strip()) < 4:
            raise HTTPException(
                status_code=422,
                detail=(
                    "The photo was not clear enough to identify a disease. "
                    "Retake it in daylight filling the frame with one leaf, "
                    "or describe what you see."
                ),
            )
        return diagnose(
            DiseaseRequest(crop=crop, symptoms=symptoms, language=language), auth
        )

    # Look the predicted label up directly in the shared disease library so the
    # advice (and its native Hindi/Marathi wording) matches the text path.
    return leaf_diagnosis.response_for(settings, prediction, language)


@app.post("/uploads/assets", response_model=UploadResponse)
async def upload_asset(
    mobile: str | None = Form(None),
    farmer_id: str | None = Form(None),
    module: str = Form(...),
    notes: str | None = Form(None),
    file: UploadFile = File(...),
    auth: AuthContext = Auth,
) -> UploadResponse:
    resolved_mobile = mobile or (resolve_mobile(settings, farmer_id) if farmer_id else None)
    if not resolved_mobile or not get_user(settings, resolved_mobile):
        raise HTTPException(status_code=400, detail="Save the farmer profile before uploading files.")

    try:
        stored = await store_upload(settings, file)
    except UnsupportedUploadType as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc
    except UploadTooLarge as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        ) from exc
    except UploadStorageUnavailable as exc:
        logger.error("Upload storage unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    asset = save_upload(
        settings,
        mobile=resolved_mobile,
        farmer_id=farmer_id,
        module=module,
        filename=stored.original_filename,
        stored_name=stored.stored_name,
        content_type=stored.content_type,
        size_bytes=stored.size_bytes,
        notes=notes,
    )
    return UploadResponse(asset=asset)


@app.get("/uploads/assets/{mobile}", response_model=list[UploadAsset])
def fetch_assets(
    mobile: str,
    module: str | None = Query(None),
    auth: AuthContext = Auth,
) -> list[UploadAsset]:
    return list_uploads(settings, mobile, module=module)


@app.get("/static/uploads/{stored_name}")
def download_upload(stored_name: str, auth: AuthContext = Auth) -> Response:
    """Serve a stored upload as an inert download.

    This replaces ``StaticFiles``, which happily served attacker-supplied HTML
    from the API origin. Files are now returned with ``nosniff`` and an
    ``attachment`` disposition, and only under a content type derived from the
    extension this service assigned at upload time.
    """
    if not is_valid_stored_name(stored_name):
        raise HTTPException(status_code=404, detail="Asset not found")

    media_type = content_type_for_stored_name(stored_name)
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'attachment; filename="{stored_name}"',
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "Cache-Control": "private, no-store",
    }

    if settings.uploads_to_s3:
        from agrotech_ml.cloud.storage_s3 import download_url

        try:
            url = download_url(
                settings,
                s3_object_name(settings, stored_name),
                expires_seconds=settings.s3_url_expiry_seconds,
                content_type=media_type or OCTET_STREAM,
                content_disposition=content_disposition_for(stored_name),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Download URL generation failed for %s: %s", stored_name, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Object storage unavailable: {exc}",
            ) from exc
        return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    path = settings.uploads_dir / stored_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")

    return FileResponse(
        path,
        media_type=media_type or OCTET_STREAM,
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Advisory history and retraining
# ---------------------------------------------------------------------------


@app.get("/advisories/history/{mobile}", response_model=list[AdvisoryRecord])
def advisory_history(
    mobile: str,
    module: str | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
    auth: AuthContext = Auth,
) -> list[AdvisoryRecord]:
    return list_advisories(settings, mobile, module=module, limit=limit)


@app.post("/retrain", response_model=RetrainStatus, status_code=status.HTTP_202_ACCEPTED)
def retrain(background_tasks: BackgroundTasks, auth: AuthContext = Auth) -> RetrainStatus:
    """Queue a retrain and return immediately - poll ``GET /retrain/status``."""
    try:
        job_id = retrain_job.queue_job()
    except retrain_job.RetrainAlreadyRunning as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    background_tasks.add_task(retrain_job.run_job, settings, job_id)
    return retrain_job.current_status()


@app.get("/retrain/status", response_model=RetrainStatus)
def retrain_status(auth: AuthContext = Auth) -> RetrainStatus:
    return retrain_job.current_status()


def main() -> None:
    import uvicorn

    # The host injects $PORT (Hugging Face Spaces uses 7860); default 8080.
    # Bind 0.0.0.0: a container-internal 127.0.0.1 listener is unreachable.
    port = int(os.environ.get("PORT") or settings.port or 8080)
    uvicorn.run("agrotech_ml.api:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()

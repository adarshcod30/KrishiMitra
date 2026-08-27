import {
  ML_API_URL,
  MIN_FARMER_SEARCH_LENGTH,
  MIN_LOCATION_SEARCH_LENGTH
} from "@/lib/constants";
import { fetchWeatherDirect, searchLocationsDirect } from "@/lib/weather-direct";
import { ApiError, NETWORK_ERROR_STATUS, ValidationError, apiErrorFromResponse } from "@/lib/errors";
import type {
  AdvisoryRecord,
  DashboardSummary,
  DiseaseRequest,
  DiseaseResponse,
  FarmProfile,
  FarmProfileCreate,
  FarmerSearchResult,
  FarmerWorkspace,
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
  SoilBaseline,
  SoilAnalysisResponse,
  SoilPayload,
  UploadAsset,
  UploadResponse,
  UserProfile,
  UserProfileCreate,
  WeatherResponse
} from "@/lib/types";

/**
 * `ML_API_URL` is relative (`/api/ml`) whenever `NEXT_PUBLIC_ML_API_URL` was not
 * set at build time. A relative URL only resolves in the browser, so fail loudly
 * rather than silently guessing an origin if a helper is ever called on the
 * server. (Deliberately no localhost literal here — it would end up in the
 * client bundle.)
 */
function resolveRequestUrl(path: string): string {
  if (ML_API_URL.startsWith("/") && typeof window === "undefined") {
    throw new ApiError(
      NETWORK_ERROR_STATUS,
      "The ML API client was called on the server without an absolute base URL. " +
        "Set NEXT_PUBLIC_ML_API_URL at build time, or call this helper from the browser " +
        "so the same-origin /api/ml proxy can be used."
    );
  }
  return `${ML_API_URL}${path}`;
}

/**
 * Hard client-side ceiling on any single request. The same-origin proxy already
 * caps itself at 60s (`maxDuration`), so anything still pending after this is
 * stuck — abort it so a "Loading..." button can never spin forever.
 */
const CLIENT_TIMEOUT_MS = 65_000;

/**
 * Backoff schedule for a sleeping backend.
 *
 * Render answers 502/503 *immediately* while an instance spins up, so a single
 * retry 8s later still lands well inside the ~60-110s wake time and the farmer
 * saw an error after ~10 seconds. These delays keep trying across roughly two
 * minutes, which is what a cold start actually costs.
 */
const COLD_START_BACKOFF_MS = [6_000, 12_000, 20_000, 30_000, 40_000];

/**
 * Message shown when both attempts died on a 502/503/504. The backend runs on
 * a free Render instance that sleeps when idle and needs about a minute to
 * wake, so the honest advice is "wait a moment and press Try again" — not a
 * generic "service error".
 */
const WAKING_MESSAGE =
  "The KrishiMitra server was asleep and is waking up now (free hosting does this). " +
  "It takes about a minute. Please wait a little and press Try again.";

/** 502/503/504 are what the proxy returns while the free backend is waking. */
function isColdStartError(error: unknown): error is ApiError {
  return (
    error instanceof ApiError &&
    (error.status === 502 || error.status === 503 || error.status === 504)
  );
}

/** Cold starts plus outright network failures are worth one automatic retry. */
function isRetryableError(error: unknown): boolean {
  return isColdStartError(error) || (error instanceof ApiError && error.isNetworkError);
}

async function requestJsonOnce<T>(path: string, init?: RequestInit): Promise<T> {
  const url = resolveRequestUrl(path);

  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: {
        ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...(init?.headers ?? {})
      },
      cache: "no-store",
      signal: init?.signal ?? AbortSignal.timeout(CLIENT_TIMEOUT_MS)
    });
  } catch (caught) {
    if (caught instanceof ApiError) {
      throw caught;
    }
    throw new ApiError(
      NETWORK_ERROR_STATUS,
      caught instanceof Error && caught.message
        ? caught.message
        : "The request could not be sent."
    );
  }

  if (!response.ok) {
    throw await apiErrorFromResponse(response);
  }

  return (await response.json()) as T;
}

interface RequestOptions {
  /**
   * When true (the default), a request that fails with a 502/503/504 or a
   * network error is retried ONCE after `COLD_START_RETRY_DELAY_MS`. Combined
   * with the proxy's ~55s upstream window this covers the full ~1 minute a
   * free-tier Render instance needs to wake from sleep, so the first visitor
   * of the day usually gets data instead of an error card.
   *
   * Set to false for non-idempotent writes (profile creation, file uploads,
   * retraining) where a blind replay could duplicate work.
   */
  retryColdStart?: boolean;
}

async function requestJson<T>(
  path: string,
  init?: RequestInit,
  options?: RequestOptions
): Promise<T> {
  const retryColdStart = options?.retryColdStart ?? true;

  let lastError: unknown;
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await requestJsonOnce<T>(path, init);
    } catch (error) {
      lastError = error;
      const canRetry =
        retryColdStart &&
        isRetryableError(error) &&
        attempt < COLD_START_BACKOFF_MS.length;
      if (!canRetry) {
        break;
      }
      await new Promise((resolve) =>
        setTimeout(resolve, COLD_START_BACKOFF_MS[attempt])
      );
    }
  }

  // Every attempt died on a gateway error: the free instance is still waking.
  // Throw a plain Error so `toUserMessage` renders this text verbatim rather
  // than the generic 5xx sentence.
  if (isColdStartError(lastError)) {
    throw new Error(WAKING_MESSAGE);
  }
  throw lastError;
}

/**
 * Nudge the backend awake without blocking anything.
 *
 * Called once when the dashboard mounts. A farmer typically spends 10-30s
 * reading the page and filling a form before their first real request, which
 * is exactly the head start a sleeping instance needs. Fire-and-forget: a
 * failure here must never surface.
 */
export function warmUpBackend(): void {
  void requestJson("/warmup", undefined, { retryColdStart: false }).catch(() => {});
}

export function fetchLanguages(): Promise<{ languages: Record<LanguageCode, string> }> {
  return requestJson("/languages");
}

export function fetchDashboardSummary(): Promise<DashboardSummary> {
  return requestJson("/dashboard/summary");
}

export function fetchModelMetadata(): Promise<ModelMetadata> {
  return requestJson("/metadata");
}

export function predictCrop(payload: SoilPayload): Promise<PredictionResponse> {
  return requestJson("/predict", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function retrainModels(): Promise<ModelMetadata> {
  // A blind replay would kick off a second training run.
  return requestJson("/retrain", { method: "POST" }, { retryColdStart: false });
}

export function getIrrigationSchedule(
  payload: IrrigationRequest
): Promise<IrrigationResponse> {
  return requestJson("/irrigation/schedule", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function diagnoseDisease(payload: DiseaseRequest): Promise<DiseaseResponse> {
  return requestJson("/disease/diagnose", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

/**
 * Diagnose from a leaf photograph. The API classifies the image and falls back
 * to the symptom text when the photo is unclear, so `symptoms` is sent along
 * whenever the farmer typed any.
 */
export function diagnoseDiseasePhoto(payload: {
  crop: string;
  file: File;
  language: LanguageCode;
  symptoms?: string;
}): Promise<DiseaseResponse> {
  const form = new FormData();
  form.append("crop", payload.crop);
  form.append("language", payload.language);
  if (payload.symptoms?.trim()) form.append("symptoms", payload.symptoms.trim());
  form.append("file", payload.file);
  return requestJson("/disease/diagnose/photo", { method: "POST", body: form });
}

export function recommendFertilizer(
  payload: FertilizerRequest
): Promise<FertilizerResponse> {
  return requestJson("/fertilizer/recommend", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

/** Typical soil profile for a district, from Soil Health Card samples. */
export function fetchSoilBaseline(state: string, district: string): Promise<SoilBaseline> {
  const params = new URLSearchParams({ state, district });
  return requestJson(`/soil/baseline?${params.toString()}`);
}

export function analyzeSoil(payload: SoilAnalysisRequest): Promise<SoilAnalysisResponse> {
  return requestJson("/soil/analyze", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

/**
 * Forecast, fetched from the farmer's own browser first.
 *
 * Open-Meteo rate-limits per IP and our backend sits behind a shared free-tier
 * egress IP that is currently exhausted (every server-side call returns 429).
 * Going direct spends the farmer's own allowance instead, and only falls back
 * to the API when their network blocks the request.
 */
export async function fetchWeather(
  latitude: number,
  longitude: number,
  language: LanguageCode,
  days = 7
): Promise<WeatherResponse> {
  try {
    return await fetchWeatherDirect(latitude, longitude, language, days);
  } catch {
    return requestJson(
      `/weather/forecast?latitude=${latitude}&longitude=${longitude}&language=${language}&days=${days}`
    );
  }
}

export async function searchLocations(query: string): Promise<LocationSearchItem[]> {
  const trimmed = query.trim();
  if (trimmed.length < MIN_LOCATION_SEARCH_LENGTH) {
    return Promise.reject(
      new ValidationError(
        `Enter at least ${MIN_LOCATION_SEARCH_LENGTH} characters to search for a location.`
      )
    );
  }
  // Same reasoning as fetchWeather: go direct from the farmer's own IP, and
  // only fall back to our rate-limited backend if that is blocked.
  try {
    return await searchLocationsDirect(trimmed);
  } catch {
    return requestJson(`/locations/search?q=${encodeURIComponent(trimmed)}`);
  }
}

export function fetchSchemes(
  payload: SchemeRecommendationRequest
): Promise<SchemeResponse> {
  return requestJson("/schemes/recommend", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function fetchMarketPrices(
  language: LanguageCode,
  options?: { crop?: string; state?: string }
): Promise<MarketPriceItem[]> {
  const params = new URLSearchParams({ language });
  if (options?.crop) {
    params.set("crop", options.crop);
  }
  if (options?.state) {
    params.set("state", options.state);
  }
  return requestJson(`/market/prices?${params.toString()}`);
}

export function fetchRentalTools(
  language: LanguageCode,
  options?: { location?: string }
): Promise<RentalTool[]> {
  const params = new URLSearchParams({ language });
  if (options?.location) {
    params.set("location", options.location);
  }
  return requestJson(`/rentals/tools?${params.toString()}`);
}

export function fetchInvestorOpportunities(
  language: LanguageCode
): Promise<InvestorOpportunity[]> {
  return requestJson(`/investor/opportunities?language=${language}`);
}

export function fetchKnowledgeLibrary(
  language: LanguageCode,
  query?: string
): Promise<KnowledgeArticle[]> {
  const params = new URLSearchParams({ language });
  if (query) {
    params.set("query", query);
  }
  return requestJson(`/knowledge/library?${params.toString()}`);
}

export function searchKnowledge(
  query: string,
  language: LanguageCode
): Promise<SearchResultItem[]> {
  return requestJson(
    `/search/knowledge?query=${encodeURIComponent(query)}&language=${language}`
  );
}

export function fetchNewsFeed(
  language: LanguageCode,
  query = "agriculture India farming"
): Promise<NewsItem[]> {
  return requestJson(
    `/news/feed?query=${encodeURIComponent(query)}&language=${language}`
  );
}

export function upsertUser(payload: UserProfileCreate): Promise<UserProfile> {
  return requestJson(
    "/profiles/user",
    {
      method: "POST",
      body: JSON.stringify(payload)
    },
    { retryColdStart: false }
  );
}

export function fetchUser(mobile: string): Promise<UserProfile> {
  return requestJson(`/profiles/user/${mobile}`);
}

/**
 * The API rejects short queries with a 422, so the guard lives here as well as
 * in the UI: no request is sent unless the query can possibly succeed.
 */
export function searchFarmers(query: string): Promise<FarmerSearchResult[]> {
  const trimmed = query.trim();
  if (trimmed.length < MIN_FARMER_SEARCH_LENGTH) {
    return Promise.reject(
      new ValidationError(
        `Enter at least ${MIN_FARMER_SEARCH_LENGTH} characters to search for a farmer.`
      )
    );
  }
  return requestJson(`/profiles/search?q=${encodeURIComponent(trimmed)}`);
}

export function fetchFarmerWorkspace(farmerId: string): Promise<FarmerWorkspace> {
  return requestJson(`/profiles/workspace/${encodeURIComponent(farmerId)}`);
}

export function addFarm(payload: FarmProfileCreate): Promise<FarmProfile> {
  return requestJson(
    "/profiles/farms",
    {
      method: "POST",
      body: JSON.stringify(payload)
    },
    { retryColdStart: false }
  );
}

export function fetchFarms(mobile: string): Promise<FarmProfile[]> {
  return requestJson(`/profiles/farms/${mobile}`);
}

export function uploadAsset(payload: {
  mobile?: string;
  farmer_id?: string;
  module: string;
  notes?: string;
  file: File;
}): Promise<UploadResponse> {
  const formData = new FormData();
  if (payload.mobile) {
    formData.append("mobile", payload.mobile);
  }
  if (payload.farmer_id) {
    formData.append("farmer_id", payload.farmer_id);
  }
  formData.append("module", payload.module);
  if (payload.notes) {
    formData.append("notes", payload.notes);
  }
  formData.append("file", payload.file);

  return requestJson(
    "/uploads/assets",
    {
      method: "POST",
      body: formData
    },
    { retryColdStart: false }
  );
}

export function fetchAssets(
  mobile: string,
  options?: { module?: string }
): Promise<UploadAsset[]> {
  const params = new URLSearchParams();
  if (options?.module) {
    params.set("module", options.module);
  }
  const suffix = params.size ? `?${params.toString()}` : "";
  return requestJson(`/uploads/assets/${mobile}${suffix}`);
}

export function fetchAdvisoryHistory(
  mobile: string,
  options?: { module?: string; limit?: number }
): Promise<AdvisoryRecord[]> {
  const params = new URLSearchParams();
  if (options?.module) {
    params.set("module", options.module);
  }
  if (options?.limit) {
    params.set("limit", String(options.limit));
  }
  const suffix = params.size ? `?${params.toString()}` : "";
  return requestJson(`/advisories/history/${mobile}${suffix}`);
}

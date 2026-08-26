import {
  ML_API_URL,
  MIN_FARMER_SEARCH_LENGTH,
  MIN_LOCATION_SEARCH_LENGTH
} from "@/lib/constants";
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

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const url = resolveRequestUrl(path);

  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: {
        ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...(init?.headers ?? {})
      },
      cache: "no-store"
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
  return requestJson("/retrain", { method: "POST" });
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

export function recommendFertilizer(
  payload: FertilizerRequest
): Promise<FertilizerResponse> {
  return requestJson("/fertilizer/recommend", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function analyzeSoil(payload: SoilAnalysisRequest): Promise<SoilAnalysisResponse> {
  return requestJson("/soil/analyze", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function fetchWeather(
  latitude: number,
  longitude: number,
  language: LanguageCode,
  days = 7
): Promise<WeatherResponse> {
  return requestJson(
    `/weather/forecast?latitude=${latitude}&longitude=${longitude}&language=${language}&days=${days}`
  );
}

export function searchLocations(query: string): Promise<LocationSearchItem[]> {
  const trimmed = query.trim();
  if (trimmed.length < MIN_LOCATION_SEARCH_LENGTH) {
    return Promise.reject(
      new ValidationError(
        `Enter at least ${MIN_LOCATION_SEARCH_LENGTH} characters to search for a location.`
      )
    );
  }
  return requestJson(`/locations/search?q=${encodeURIComponent(trimmed)}`);
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
  return requestJson("/profiles/user", {
    method: "POST",
    body: JSON.stringify(payload)
  });
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
  return requestJson("/profiles/farms", {
    method: "POST",
    body: JSON.stringify(payload)
  });
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

  return requestJson("/uploads/assets", {
    method: "POST",
    body: formData
  });
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

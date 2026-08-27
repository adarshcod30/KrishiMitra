export type LanguageCode =
  | "en"
  | "hi"
  | "bn"
  | "te"
  | "ta"
  | "mr"
  | "gu"
  | "kn"
  | "ml"
  | "pa"
  | "or";

export type SoilFeatureKey =
  | "N"
  | "P"
  | "K"
  | "temperature"
  | "humidity"
  | "ph"
  | "rainfall";

export type SoilPayload = Record<SoilFeatureKey, number> & {
  farmer_id?: string | null;
  mobile?: string | null;
  language: LanguageCode;
  /**
   * Optional. When the farmer's district is known the API pairs each soil
   * recommendation with five years of government district returns. Omit them
   * and the response is exactly as before.
   */
  state?: string | null;
  district?: string | null;
  season?: string | null;
};

/** District evidence for a crop, from the DES Area/Production/Yield returns. */
export interface LocalEvidence {
  grown_locally: boolean;
  season: string;
  area_ha?: number | null;
  median_yield?: number | null;
  yield_unit: string;
  rank_in_district?: number | null;
  why: string;
}

export interface LocalCropItem {
  crop: string;
  season: string;
  score: number;
  median_yield?: number | null;
  yield_unit: string;
  area_ha?: number | null;
  why: string;
}

export interface LocalCrops {
  crops: LocalCropItem[];
  season_used?: string | null;
  source: string;
  matched: boolean;
}

export interface PredictionRecommendation {
  crop: string;
  display_crop: string;
  probability: number;
  confidence: "high" | "medium" | "low";
  agronomy_tip: string;
  /** Present only when state/district were sent. */
  local?: LocalEvidence | null;
}

export interface PredictionResponse {
  recommendations: PredictionRecommendation[];
  field_actions: string[];
  best_model: string;
  generated_at: string;
  local_crops?: LocalCrops | null;
}

export interface ModelScore {
  model_name: string;
  accuracy: number;
  macro_f1: number;
  top3_accuracy: number;
  training_seconds: number;
}

export interface FeatureImportance {
  feature: SoilFeatureKey;
  importance: number;
}

export interface SkippedModel {
  model_name: string;
  reason: string;
}

export interface ModelMetadata {
  trained_at: string;
  dataset_rows: number;
  best_model: string;
  feature_columns: SoilFeatureKey[];
  model_scores: ModelScore[];
  feature_importance: FeatureImportance[];
  skipped_models: SkippedModel[];
  auxiliary_models: Record<string, string>;
}

export interface DashboardSummary {
  active_users: number;
  total_farms: number;
  listed_tools: number;
  investor_deals: number;
  available_languages: number;
  saved_assets: number;
  advisory_runs: number;
  translation_enabled: boolean;
  live_search_enabled: boolean;
}

export interface IrrigationRequest {
  farmer_name: string;
  location: string;
  crop: string;
  land_size: number;
  land_unit: "Katha" | "Bigha" | "Acres" | "Hectares";
  term_period_months: number;
  temperature: number;
  humidity: number;
  rainfall: number;
  soil_type: string;
  soil_ph: number;
  farmer_id?: string | null;
  mobile?: string | null;
  language: LanguageCode;
}

export interface IrrigationEvent {
  date: string;
  time: string;
  water_mm: number;
  message: string;
}

export interface IrrigationResponse {
  crop: string;
  events: IrrigationEvent[];
  notes: string[];
}

export interface DiseaseRequest {
  crop: string;
  symptoms: string;
  image_hint?: string;
  farmer_id?: string | null;
  mobile?: string | null;
  language: LanguageCode;
}

export interface DiseaseResponse {
  disease: string;
  confidence: number;
  severity: "low" | "moderate" | "high";
  advice: string;
  preventive_actions: string[];
  /**
   * Additive fields from the API's curated disease dataset. `advice` keeps
   * carrying the treatment text, so these stay optional for older APIs.
   */
  treatment?: string | null;
  prevention?: string[] | null;
  /** Provenance of the advice, e.g. an ICAR/state agri-department page. */
  source?: string | null;
}

export interface FertilizerRequest {
  crop: string;
  soil_type: string;
  N: number;
  P: number;
  K: number;
  ph: number;
  farmer_id?: string | null;
  mobile?: string | null;
  language: LanguageCode;
}

export interface FertilizerResponse {
  blend: string;
  rationale: string;
  schedule: string[];
}

export interface WeatherDay {
  date: string;
  min_temp: number;
  max_temp: number;
  rain_mm: number;
  humidity: number;
}

export interface WeatherResponse {
  latitude: number;
  longitude: number;
  current_temp: number;
  current_wind_kph: number;
  daily: WeatherDay[];
  soil_hint: string;
}

export interface SchemeRecommendationRequest {
  farmer_type: "small" | "marginal" | "medium" | "large";
  land_size_acres: number;
  annual_income_lakh: number;
  state: string;
  farmer_id?: string | null;
  mobile?: string | null;
  language: LanguageCode;
}

export interface SchemeItem {
  id: string;
  title: string;
  description: string;
  eligibility: string;
  link: string;
  /**
   * Optional fields the API may add (curated scheme catalogue). Optional so an
   * older API that omits them keeps working unchanged.
   */
  how_to_apply?: string[] | null;
  /** Provenance note, e.g. "Source: pmkisan.gov.in". */
  source?: string | null;
}

export interface SchemeResponse {
  schemes: SchemeItem[];
  /**
   * Additive fields from the API: where the recommendations came from.
   * `source` is a machine label ("myscheme_live", "official_catalog", ...);
   * `note` is a human sentence safe to render as-is. Optional so an older API
   * that omits them keeps working unchanged.
   */
  source?: string | null;
  note?: string | null;
}

export interface SoilBaselineNutrient {
  dominant_class: "low" | "medium" | "high";
  share_pct: number;
  low_pct?: number | null;
  medium_pct?: number | null;
  high_pct?: number | null;
}

/** District soil profile from Soil Health Card samples. */
export interface SoilBaseline {
  matched: boolean;
  district?: string;
  state?: string;
  samples?: number;
  source: string;
  nutrients?: Record<string, SoilBaselineNutrient>;
  ph?: { dominant_class: string; share_pct: number };
  widespread_deficiencies?: Record<string, number>;
  prefill?: { N?: number; P?: number; K?: number; ph?: number };
}

export interface MarketPriceItem {
  crop: string;
  mandi: string;
  state: string;
  modal_price_inr_quintal: number;
  trend: "up" | "down" | "stable";
  /** Additive: the arrival date the price was reported for (ISO date). */
  arrival_date?: string | null;
  /** Additive: link to the data.gov.in / Agmarknet source row. */
  source_url?: string | null;
  /** Seasonal context from Agmarknet history; absent for uncovered crops. */
  typical_min?: number | null;
  typical_max?: number | null;
  season_note?: string | null;
  price_note?: string | null;
}

export interface RentalTool {
  name: string;
  /**
   * The live API returns null for some entries (e.g. eNAM logistics listings
   * without a published rate), so the type must admit it — the UI shows
   * "Ask provider" instead of a bare rupee sign.
   */
  hourly_rate_inr: number | null;
  provider: string;
  location: string;
  availability: string;
  /** Additive: e.g. "custom hiring centre", "logistics". */
  service_type?: string | null;
  /** Additive: link to the provider / listing source. */
  source_url?: string | null;
}

export interface InvestorOpportunity {
  title: string;
  expected_irr_percent: number;
  minimum_ticket_inr: number;
  tenure_months: number;
  focus_area: string;
}

export interface KnowledgeArticle {
  id: string;
  category: "production" | "treatment" | "horticulture" | "soil" | "market";
  title: string;
  summary: string;
  url?: string;
  source?: string;
  /** Set by the API when serving saved/offline content instead of a live feed. */
  is_fallback?: boolean | null;
  /** Optional provenance/freshness note from the API. */
  source_note?: string | null;
}

export interface UserProfile {
  id: string;
  farmer_id: string;
  name: string;
  mobile: string;
  state?: string | null;
  district?: string | null;
  language: LanguageCode;
  created_at: string;
}

export interface UserProfileCreate {
  farmer_id?: string | null;
  name: string;
  mobile: string;
  state?: string | null;
  district?: string | null;
  language: LanguageCode;
}

export interface FarmProfile {
  id: string;
  mobile: string;
  farmer_id?: string | null;
  farm_name: string;
  village: string;
  state: string;
  acres: number;
  primary_crop: string;
  district?: string | null;
  soil_type?: string | null;
  irrigation_source?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  created_at: string;
}

export interface FarmProfileCreate {
  farmer_id?: string | null;
  mobile: string;
  farm_name: string;
  village: string;
  state: string;
  acres: number;
  primary_crop: string;
  district?: string | null;
  soil_type?: string | null;
  irrigation_source?: string | null;
  latitude?: number | null;
  longitude?: number | null;
}

export interface UploadAsset {
  id: string;
  mobile: string;
  farmer_id?: string | null;
  module: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  notes?: string | null;
  url: string;
  created_at: string;
}

export interface UploadResponse {
  asset: UploadAsset;
}

export interface AdvisoryRecord {
  id: string;
  mobile: string;
  farmer_id?: string | null;
  module: string;
  summary: string;
  language: LanguageCode;
  request_payload: Record<string, unknown>;
  response_payload: Record<string, unknown>;
  created_at: string;
}

export interface SearchResultItem {
  title: string;
  summary: string;
  url: string;
  source: string;
  published_at?: string | null;
}

export interface NewsItem {
  title: string;
  summary: string;
  url: string;
  source: string;
  published_at?: string | null;
  /** Set by the API when serving saved/offline content instead of a live feed. */
  is_fallback?: boolean | null;
  /** Optional provenance/freshness note from the API. */
  source_note?: string | null;
}

export interface LocationSearchItem {
  name: string;
  admin1?: string | null;
  admin2?: string | null;
  country: string;
  latitude: number;
  longitude: number;
}

export interface FarmerSearchResult {
  farmer_id: string;
  name: string;
  mobile: string;
  state?: string | null;
  district?: string | null;
  village?: string | null;
  primary_crop?: string | null;
  acres?: number | null;
}

export interface FarmerWorkspace {
  profile: UserProfile;
  farms: FarmProfile[];
  uploads: UploadAsset[];
  advisories: AdvisoryRecord[];
}

export interface SoilAnalysisRequest {
  N: number;
  P: number;
  K: number;
  ph: number;
  soil_type: string;
  crop: string;
  farmer_id?: string | null;
  mobile?: string | null;
  language: LanguageCode;
}

export interface SoilAnalysisResponse {
  soil_health_status: string;
  nutrient_alerts: string[];
  soil_actions: string[];
  recommended_crop_focus: string[];
  generated_at: string;
}

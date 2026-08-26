import type { TranslationKey } from "@/lib/i18n";
import type { IrrigationRequest, LanguageCode, SoilFeatureKey, SoilPayload } from "@/lib/types";

/**
 * Same-origin proxy route (app/api/ml/[...path]/route.ts).
 *
 * `NEXT_PUBLIC_*` values are inlined into the client bundle at BUILD time, so a
 * baked-in absolute URL cannot be changed on a deployed Cloud Run revision — and
 * a baked-in localhost URL would make every visitor's browser call their own
 * machine. When no public URL is configured we therefore talk to this relative
 * path instead; the route handler forwards to the SERVER-side `ML_API_URL`,
 * which is a plain runtime env var and needs no rebuild to change.
 */
export const ML_API_PROXY_PATH = "/api/ml";

function resolveMlApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_ML_API_URL?.trim();
  if (!configured) {
    return ML_API_PROXY_PATH;
  }
  return configured.replace(/\/+$/, "");
}

/**
 * Base URL every `lib/api.ts` helper prefixes to its path. Either an absolute
 * origin (when `NEXT_PUBLIC_ML_API_URL` was set at build time) or the relative
 * proxy path above.
 */
export const ML_API_URL = resolveMlApiBaseUrl();

/** Minimum farmer-search query length accepted by the API (`min_length=2`). */
export const MIN_FARMER_SEARCH_LENGTH = 3;

/** Minimum location-search query length accepted by the API. */
export const MIN_LOCATION_SEARCH_LENGTH = 2;

export const SUPPORTED_LANGUAGES: Array<{ code: LanguageCode; label: string; native: string }> = [
  { code: "en", label: "English", native: "English" },
  { code: "hi", label: "Hindi", native: "हिन्दी" },
  { code: "bn", label: "Bengali", native: "বাংলা" },
  { code: "te", label: "Telugu", native: "తెలుగు" },
  { code: "ta", label: "Tamil", native: "தமிழ்" },
  { code: "mr", label: "Marathi", native: "मराठी" },
  { code: "gu", label: "Gujarati", native: "ગુજરાતી" },
  { code: "kn", label: "Kannada", native: "ಕನ್ನಡ" },
  { code: "ml", label: "Malayalam", native: "മലയാളം" },
  { code: "pa", label: "Punjabi", native: "ਪੰਜਾਬੀ" },
  { code: "or", label: "Odia", native: "ଓଡ଼ିଆ" },
];

export interface FeatureInputDefinition {
  key: SoilFeatureKey;
  labelKey: TranslationKey;
  unit: string;
  min: number;
  max: number;
  step: number;
}

export const FEATURE_INPUTS: FeatureInputDefinition[] = [
  { key: "N", labelKey: "common.nitrogen", unit: "mg/kg", min: 0, max: 200, step: 1 },
  { key: "P", labelKey: "common.phosphorus", unit: "mg/kg", min: 0, max: 200, step: 1 },
  { key: "K", labelKey: "common.potassium", unit: "mg/kg", min: 0, max: 250, step: 1 },
  { key: "temperature", labelKey: "common.temperature", unit: "°C", min: -5, max: 55, step: 0.1 },
  { key: "humidity", labelKey: "common.humidity", unit: "%", min: 0, max: 100, step: 0.1 },
  { key: "ph", labelKey: "common.soilPh", unit: "pH", min: 2.5, max: 10.5, step: 0.1 },
  { key: "rainfall", labelKey: "common.rainfall", unit: "mm", min: 0, max: 500, step: 0.1 },
];

export const DEFAULT_SOIL_PAYLOAD: SoilPayload = {
  N: 90,
  P: 42,
  K: 43,
  temperature: 23.5,
  humidity: 82,
  ph: 6.5,
  rainfall: 205,
  language: "en",
};

export const DEFAULT_IRRIGATION_PAYLOAD: IrrigationRequest = {
  farmer_name: "Ravi Kumar",
  location: "Lucknow",
  crop: "rice",
  land_size: 2,
  land_unit: "Acres",
  term_period_months: 4,
  temperature: 30,
  humidity: 68,
  rainfall: 120,
  soil_type: "loam",
  soil_ph: 6.6,
  language: "en",
};

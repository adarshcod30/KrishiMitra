import type { TranslationKey } from "@/lib/i18n";
import type { IrrigationRequest, LanguageCode, SoilFeatureKey, SoilPayload } from "@/lib/types";

export const ML_API_URL =
  process.env.NEXT_PUBLIC_ML_API_URL ?? "http://127.0.0.1:8000";

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

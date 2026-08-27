/**
 * Fetch weather straight from Open-Meteo in the browser.
 *
 * Why not always go through our API? Open-Meteo is free and key-less but
 * rate-limits per IP, and the backend runs on a free Render instance whose
 * egress IP is shared with other tenants — in production every server-side
 * forecast came back HTTP 429 while the same request from a laptop succeeded.
 *
 * Open-Meteo sends `access-control-allow-origin: *`, so the browser can call it
 * directly. Each farmer then spends their OWN IP's allowance, which no other
 * tenant can exhaust, and the forecast never touches our server at all. The
 * server call remains as a fallback for anyone whose network blocks the direct
 * request.
 */
import type { LanguageCode, WeatherDay, WeatherResponse } from "@/lib/types";

const FORECAST_URL = "https://api.open-meteo.com/v1/forecast";
const GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search";
const DIRECT_TIMEOUT_MS = 12_000;

async function getJson(url: string): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), DIRECT_TIMEOUT_MS);
  try {
    const response = await fetch(url, { signal: controller.signal, cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Open-Meteo responded ${response.status}`);
    }
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

/**
 * One actionable sentence derived strictly from the forecast.
 *
 * Mirrors `_forecast_advisory` in the API so both paths give identical advice.
 * It replaced a field that guessed a soil TEXTURE from (latitude + longitude)
 * % 2 — arithmetic dressed as soil science. Real soil data lives on the Soil
 * Check page, sourced from Soil Health Card samples.
 */
export function forecastAdvisory(daily: WeatherDay[]): string {
  if (daily.length === 0) return "Forecast unavailable.";
  const window = daily.slice(0, 3);
  const rain = window.reduce((sum, day) => sum + day.rain_mm, 0);
  const hottest = Math.max(...window.map((day) => day.max_temp));
  const coldest = Math.min(...window.map((day) => day.min_temp));

  if (rain >= 50) {
    return `Heavy rain expected (${rain.toFixed(0)} mm over 3 days). Hold back irrigation and do not apply fertiliser or spray before it passes.`;
  }
  if (rain >= 10) {
    return `Rain likely (${rain.toFixed(0)} mm over 3 days). You can delay the next irrigation and should time any spraying around it.`;
  }
  if (hottest >= 38) {
    return `Hot spell ahead (up to ${hottest.toFixed(0)}C). Irrigate early morning or evening to cut evaporation loss, and mulch if you can.`;
  }
  if (coldest <= 5) {
    return `Cold nights ahead (down to ${coldest.toFixed(0)}C). Light evening irrigation reduces frost damage to standing crops.`;
  }
  return "No rain expected in the next 3 days. Plan irrigation normally and check soil moisture before watering.";
}

export async function fetchWeatherDirect(
  latitude: number,
  longitude: number,
  _language: LanguageCode,
  days = 7
): Promise<WeatherResponse> {
  const params = new URLSearchParams({
    latitude: String(latitude),
    longitude: String(longitude),
    daily: "temperature_2m_max,temperature_2m_min,precipitation_sum,relative_humidity_2m_mean",
    current: "temperature_2m,wind_speed_10m",
    timezone: "auto",
    forecast_days: String(days)
  });

  const payload = (await getJson(`${FORECAST_URL}?${params.toString()}`)) as {
    current?: { temperature_2m?: number; wind_speed_10m?: number };
    daily?: {
      time?: string[];
      temperature_2m_min?: number[];
      temperature_2m_max?: number[];
      precipitation_sum?: number[];
      relative_humidity_2m_mean?: number[];
    };
  };

  const block = payload.daily ?? {};
  const daily: WeatherDay[] = (block.time ?? []).map((date, index) => ({
    date,
    min_temp: block.temperature_2m_min?.[index] ?? 0,
    max_temp: block.temperature_2m_max?.[index] ?? 0,
    rain_mm: block.precipitation_sum?.[index] ?? 0,
    humidity: block.relative_humidity_2m_mean?.[index] ?? 0
  }));

  return {
    latitude,
    longitude,
    current_temp: payload.current?.temperature_2m ?? 0,
    current_wind_kph: payload.current?.wind_speed_10m ?? 0,
    daily,
    soil_hint: forecastAdvisory(daily)
  };
}

export async function searchLocationsDirect(query: string) {
  const params = new URLSearchParams({
    name: query,
    count: "6",
    language: "en",
    format: "json"
  });
  const payload = (await getJson(`${GEOCODE_URL}?${params.toString()}`)) as {
    results?: Array<{
      name?: string;
      admin1?: string;
      admin2?: string;
      country?: string;
      latitude?: number;
      longitude?: number;
    }>;
  };
  return (payload.results ?? []).map((item) => ({
    name: item.name ?? "",
    admin1: item.admin1 ?? null,
    admin2: item.admin2 ?? null,
    country: item.country ?? "",
    latitude: item.latitude ?? 0,
    longitude: item.longitude ?? 0
  }));
}

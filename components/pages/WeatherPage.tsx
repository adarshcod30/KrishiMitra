"use client";

import { useState } from "react";

import { ActiveFarmerBanner } from "@/components/farmers/ActiveFarmerBanner";
import { PageHeader } from "@/components/ui/PageHeader";
import { useFarmerSession } from "@/contexts/FarmerSessionContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { fetchWeather, searchLocations } from "@/lib/api";
import type { LocationSearchItem, WeatherResponse } from "@/lib/types";

export function WeatherPage() {
  const { t, language } = useLanguage();
  const { activeFarmer } = useFarmerSession();
  const [query, setQuery] = useState("");
  const [locations, setLocations] = useState<LocationSearchItem[]>([]);
  const [weather, setWeather] = useState<WeatherResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [searching, setSearching] = useState(false);

  async function handleSearch() {
    if (query.length < 2) return;
    setSearching(true);
    try {
      const results = await searchLocations(query);
      setLocations(results);
    } catch {
      setLocations([]);
    } finally {
      setSearching(false);
    }
  }

  async function handleSelectLocation(loc: LocationSearchItem) {
    setBusy(true);
    setLocations([]);
    setQuery(loc.name + (loc.admin1 ? `, ${loc.admin1}` : ""));
    try {
      const result = await fetchWeather(loc.latitude, loc.longitude, language);
      setWeather(result);
    } catch {
      setWeather(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-container">
      <PageHeader
        eyebrow={t("nav.weather")}
        title={t("weather.title")}
        description={t("weather.subtitle")}
      />
      <ActiveFarmerBanner />

      <section className="dashboard-grid mt-4">
        <article className="surface-card">
          <h3>🔍 {t("weather.searchLocation")}</h3>
          <div className="inline-actions">
            <input
              placeholder={t("weather.searchPlaceholder")}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            />
            <button type="button" className="primary-btn small-btn" onClick={handleSearch}>
              {searching ? t("common.loading") : t("common.search")}
            </button>
          </div>

          {locations.length > 0 && (
            <div className="search-result-list" style={{ marginTop: "0.8rem" }}>
              {locations.map((loc, i) => (
                <button
                  key={`${loc.latitude}-${loc.longitude}-${i}`}
                  type="button"
                  className="search-result-card w-full mb-2"
                  onClick={() => handleSelectLocation(loc)}
                >
                  <div className="result-info">
                    <strong>{loc.name}</strong>
                    <span>{[loc.admin1, loc.admin2, loc.country].filter(Boolean).join(", ")}</span>
                  </div>
                  <span className="select-pill">Select →</span>
                </button>
              ))}
            </div>
          )}
        </article>

        <article className="surface-card">
          <div className="flex items-center justify-between mb-6">
            <h3 className="mb-0">🌤️ {t("weather.forecastTitle")}</h3>
            {weather && !busy && (
              <div className="status-badge info">
                📍 {weather.latitude.toFixed(2)}, {weather.longitude.toFixed(2)}
              </div>
            )}
          </div>
          
          {busy && (
             <div className="empty-state-illust">
                <div className="illust-icon animate-pulse">🌤️</div>
                <p className="muted-copy">{t("common.loading")}</p>
             </div>
          )}
          
          {weather && !busy ? (
            <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
              <div className="weather-hero">
                <div className="location-tag">
                  <span>📍</span> {query || "Current Location"}
                </div>
                <div className="temp-display">{weather.current_temp}°C</div>
                <div className="weather-stats-grid">
                  <div className="weather-stat-pill">
                    <span className="label">💨 {t("weather.wind")}</span>
                    <span className="value">{weather.current_wind_kph} <span className="text-xs">km/h</span></span>
                  </div>
                  <div className="weather-stat-pill">
                    <span className="label">💧 Humidity</span>
                    <span className="value">{weather.daily[0]?.humidity || 65}%</span>
                  </div>
                  <div className="weather-stat-pill">
                    <span className="label">☔ Rain</span>
                    <span className="value">{weather.daily[0]?.rain_mm || 0} <span className="text-xs">mm</span></span>
                  </div>
                </div>
              </div>

              <div className="mt-8">
                <div className="flex items-center justify-between mb-4">
                   <h4 className="mb-0 text-ink font-bold">7-Day Forecast</h4>
                   <span className="text-xs text-muted font-bold uppercase tracking-widest">Scroll for more →</span>
                </div>
                <div className="weather-forecast-scroll">
                  {weather.daily.map((day) => {
                    const isRainy = day.rain_mm > 0;
                    return (
                      <div key={day.date} className="forecast-mini-card">
                        <span className="date">{day.date.split('-').slice(1).reverse().join('/')}</span>
                        <span className="icon">{isRainy ? '🌧️' : '☀️'}</span>
                        <div className="temp-range">{day.max_temp}°</div>
                        <div className="text-xs text-muted font-medium">{day.min_temp}° Low</div>
                        <div className="rain-stats">💧 {day.rain_mm}mm</div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {weather.soil_hint && (
                <div className="tips-section mt-6">
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-xl">🌿</span>
                    <span className="tips-title mb-0">{t("weather.soilHint")}</span>
                  </div>
                  <p className="tips-content italic">"{weather.soil_hint}"</p>
                </div>
              )}
            </div>
          ) : (
            !busy && (
              <div className="empty-state-illust">
                <div className="illust-icon">🌍</div>
                <p className="muted-copy">{t("weather.empty")}</p>
              </div>
            )
          )}
        </article>
      </section>
    </div>
  );
}

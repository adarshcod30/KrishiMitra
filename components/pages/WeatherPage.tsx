"use client";

import { useState } from "react";

import { ActiveFarmerBanner } from "@/components/farmers/ActiveFarmerBanner";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/ui/AsyncState";
import { Icon } from "@/components/ui/Icons";
import { PageHeader } from "@/components/ui/PageHeader";
import { useLanguage } from "@/contexts/LanguageContext";
import { fetchWeather, searchLocations } from "@/lib/api";
import { MIN_LOCATION_SEARCH_LENGTH } from "@/lib/constants";
import { toUserMessage } from "@/lib/errors";
import type { LocationSearchItem, WeatherResponse } from "@/lib/types";

const iconTitleStyle = {
  display: "flex",
  alignItems: "center",
  gap: "0.5rem",
} as const;

export function WeatherPage() {
  const { t, language } = useLanguage();
  const [query, setQuery] = useState("");
  const [locations, setLocations] = useState<LocationSearchItem[]>([]);
  const [weather, setWeather] = useState<WeatherResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  const isQueryTooShort = query.trim().length < MIN_LOCATION_SEARCH_LENGTH;

  async function handleSearch() {
    if (isQueryTooShort) {
      setError(`Type at least ${MIN_LOCATION_SEARCH_LENGTH} letters of your village or town name.`);
      return;
    }
    setSearching(true);
    setError(null);
    try {
      const results = await searchLocations(query);
      setLocations(results);
      setHasSearched(true);
    } catch (caught) {
      setLocations([]);
      setHasSearched(true);
      setError(toUserMessage(caught, t("feedback.searchFailed")));
    } finally {
      setSearching(false);
    }
  }

  async function handleSelectLocation(loc: LocationSearchItem) {
    setBusy(true);
    setError(null);
    setLocations([]);
    setQuery(loc.name + (loc.admin1 ? `, ${loc.admin1}` : ""));
    try {
      const result = await fetchWeather(loc.latitude, loc.longitude, language);
      setWeather(result);
    } catch (caught) {
      setWeather(null);
      setError(toUserMessage(caught, t("feedback.loadFailed")));
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

      <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem", marginTop: "2rem" }}>
        <article className="surface-card">
          <label className="field-label" htmlFor="weather-place" style={iconTitleStyle}>
            <Icon name="search" size={20} />
            {t("weather.searchLocation")}
          </label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem" }}>
            <input
              id="weather-place"
              className="field-input"
              style={{ flex: "1 1 240px", width: "auto" }}
              placeholder={t("weather.searchPlaceholder")}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            />
            <button
              type="button"
              className="btn-primary"
              onClick={handleSearch}
              disabled={searching || isQueryTooShort}
            >
              {searching ? t("common.loading") : t("common.search")}
            </button>
          </div>
          <p className="field-help">Type your village or town name, then choose it from the list.</p>

          {error && <ErrorNotice message={error} onDismiss={() => setError(null)} />}

          {!error && hasSearched && !searching && locations.length === 0 && (
            <p className="no-results-text" style={{ marginTop: "0.8rem" }}>
              No places found with that name. Check the spelling and try again.
            </p>
          )}

          {locations.length > 0 && (
            <div className="search-results-list" style={{ marginTop: "0.8rem" }}>
              {locations.map((loc, i) => (
                <button
                  key={`${loc.latitude}-${loc.longitude}-${i}`}
                  type="button"
                  className="search-result-card w-full"
                  onClick={() => handleSelectLocation(loc)}
                >
                  <div className="result-info">
                    <strong>{loc.name}</strong>
                    <span>{[loc.admin1, loc.admin2, loc.country].filter(Boolean).join(", ")}</span>
                  </div>
                  <span className="select-pill">{t("common.select")}</span>
                </button>
              ))}
            </div>
          )}
        </article>

        <article className="surface-card">
          <h3 className="section-title" style={iconTitleStyle}>
            <Icon name="weather" size={22} />
            {t("weather.forecastTitle")}
          </h3>

          {busy && <LoadingState icon="weather" />}

          {weather && !busy ? (
            <div>
              {weather.soil_hint && (
                <div className="result-card result-card-success" style={{ marginBottom: "1.25rem" }}>
                  <span className="stat-label">{t("weather.soilHint")}</span>
                  <p
                    style={{
                      fontSize: "1.15rem",
                      fontWeight: 600,
                      color: "var(--ink)",
                      lineHeight: 1.5,
                    }}
                  >
                    {weather.soil_hint}
                  </p>
                </div>
              )}

              <div className="weather-hero">
                <div className="location-tag">
                  <Icon name="location" size={20} />
                  {query}
                </div>
                <div className="temp-display">{weather.current_temp}°C</div>
                <div className="weather-stats-grid">
                  <div className="weather-stat-pill">
                    <span className="label">{t("weather.wind")}</span>
                    <span className="value">{weather.current_wind_kph} km/h</span>
                  </div>
                  <div className="weather-stat-pill">
                    <span className="label">{t("common.humidity")}</span>
                    <span className="value">{weather.daily[0]?.humidity || 65}%</span>
                  </div>
                  <div className="weather-stat-pill">
                    <span className="label">{t("common.rainfall")}</span>
                    <span className="value">{weather.daily[0]?.rain_mm || 0}</span>
                  </div>
                </div>
              </div>

              <div style={{ marginTop: "1.5rem" }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "baseline",
                    justifyContent: "space-between",
                    gap: "0.75rem",
                    flexWrap: "wrap",
                  }}
                >
                  <h4 className="section-title" style={{ marginBottom: "0.75rem" }}>
                    Next 7 days
                  </h4>
                  <span style={{ fontSize: "0.9rem", color: "var(--ink-secondary)", fontWeight: 600 }}>
                    Slide to see more days
                  </span>
                </div>
                <div className="weather-forecast-scroll">
                  {weather.daily.map((day) => {
                    const isRainy = day.rain_mm > 0;
                    return (
                      <div key={day.date} className="forecast-mini-card">
                        <span className="date">{day.date.split("-").slice(1).reverse().join("/")}</span>
                        <span style={{ color: isRainy ? "var(--info)" : "var(--accent)" }}>
                          <Icon name={isRainy ? "water" : "weather"} size={28} />
                        </span>
                        <div className="temp-range" style={{ fontSize: "1.35rem" }}>
                          {day.max_temp}°
                        </div>
                        <div style={{ fontSize: "0.9rem", fontWeight: 600, color: "var(--ink-secondary)" }}>
                          {day.min_temp}° at night
                        </div>
                        <div className="rain-stats">{day.rain_mm} mm rain</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          ) : (
            !busy && <EmptyState icon="weather" message={t("weather.empty")} />
          )}
        </article>
      </div>
    </div>
  );
}

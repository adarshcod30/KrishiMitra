"use client";

import { useState, useEffect } from "react";

import { searchFarmers } from "@/lib/api";
import type { FarmerSearchResult } from "@/lib/types";
import { useLanguage } from "@/contexts/LanguageContext";
import { useFarmerSession } from "@/contexts/FarmerSessionContext";

export function FarmerSearchPanel({ compact = false }: { compact?: boolean }) {
  const { t } = useLanguage();
  const { activeFarmer, setActiveFarmer, clearActiveFarmer } = useFarmerSession();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<FarmerSearchResult[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  async function handleSearch() {
    if (!query.trim()) {
      setResults([]);
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const response = await searchFarmers(query);
      setResults(response);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : t("feedback.searchFailed"));
    } finally {
      setBusy(false);
    }
  }

  if (!mounted) return null;

  return (
    <section className={`search-panel-airy ${compact ? "compact" : ""}`}>
      <div className="search-header">
        <h3 className="section-title mb-0">{t("shell.searchFarmers")}</h3>
        {activeFarmer && (
          <button type="button" className="ghost-btn small" onClick={clearActiveFarmer}>
            {t("shell.clearFarmer")}
          </button>
        )}
      </div>

      <div className="search-input-group">
        <input
          className="airy-input"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t("shell.searchPlaceholder")}
        />
        <button type="button" className="primary-btn" onClick={handleSearch}>
          {busy ? t("common.loading") : t("common.search")}
        </button>
      </div>

      {activeFarmer ? (
        <div className="active-farmer-banner">
          <div className="farmer-status-pill">{t("common.activeFarmer")}</div>
          <div className="farmer-details">
            <strong className="farmer-name">{activeFarmer.name}</strong>
            <span className="farmer-meta">
              {activeFarmer.farmer_id} • {activeFarmer.mobile}
            </span>
          </div>
        </div>
      ) : (
        <div className="active-farmer-banner muted">
          <div className="farmer-status-pill">{t("common.activeFarmer")}</div>
          <div className="farmer-details">
            <strong className="farmer-name text-muted">{t("common.noFarmer")}</strong>
          </div>
        </div>
      )}

      {error && <p className="error-text">{error}</p>}

      {results.length > 0 ? (
        <div className="search-results-list">
          {results.map((farmer) => (
            <button
              key={farmer.farmer_id}
              type="button"
              className="search-result-card"
              onClick={() => setActiveFarmer(farmer)}
            >
              <div className="result-info">
                <strong>{farmer.name}</strong>
                <span>{farmer.farmer_id} • {farmer.mobile}</span>
              </div>
              <div className="select-pill">{t("common.select")}</div>
            </button>
          ))}
        </div>
      ) : query && !busy ? (
        <p className="no-results-text">{t("shell.noSearchResults")}</p>
      ) : null}
    </section>
  );
}

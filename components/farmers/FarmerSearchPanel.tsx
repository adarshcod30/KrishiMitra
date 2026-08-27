"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { ActiveFarmerBanner } from "@/components/farmers/ActiveFarmerBanner";
import { ErrorNotice } from "@/components/ui/AsyncState";
import { Icon } from "@/components/ui/Icons";
import { searchFarmers } from "@/lib/api";
import { MIN_FARMER_SEARCH_LENGTH } from "@/lib/constants";
import { toUserMessage } from "@/lib/errors";
import { useDebouncedValue } from "@/lib/hooks";
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
  const [hasSearched, setHasSearched] = useState(false);

  const debouncedQuery = useDebouncedValue(query, 400);
  const trimmedQuery = useMemo(() => debouncedQuery.trim(), [debouncedQuery]);
  const isQueryTooShort = trimmedQuery.length > 0 && trimmedQuery.length < MIN_FARMER_SEARCH_LENGTH;

  const runSearch = useCallback(
    async (term: string, signal?: { cancelled: boolean }) => {
      // The API rejects anything shorter with a 422, so never send it.
      if (term.length < MIN_FARMER_SEARCH_LENGTH) {
        setResults([]);
        setError(null);
        setHasSearched(false);
        return;
      }

      setBusy(true);
      setError(null);
      try {
        const response = await searchFarmers(term);
        if (!signal?.cancelled) {
          setResults(response);
          setHasSearched(true);
        }
      } catch (caught) {
        if (!signal?.cancelled) {
          // Never surface the raw FastAPI JSON body to a farmer.
          setError(toUserMessage(caught, t("feedback.searchFailed")));
          setResults([]);
          setHasSearched(true);
        }
      } finally {
        if (!signal?.cancelled) {
          setBusy(false);
        }
      }
    },
    [t]
  );

  // Debounced auto-search: typing "R" or "Ra" never reaches the network.
  useEffect(() => {
    const signal = { cancelled: false };
    void runSearch(trimmedQuery, signal);
    return () => {
      signal.cancelled = true;
    };
  }, [trimmedQuery, runSearch]);

  return (
    <section className={`search-panel-airy ${compact ? "compact" : ""}`}>
      <div className="search-header">
        <h3
          className="section-title"
          style={{ marginBottom: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}
        >
          <Icon name="farmer" size={22} />
          {t("shell.searchFarmers")}
        </h3>
        {activeFarmer && (
          <button type="button" className="btn-secondary" onClick={clearActiveFarmer}>
            {t("shell.clearFarmer")}
          </button>
        )}
      </div>

      <p className="field-help" style={{ marginTop: 0 }}>
        Find your name or register once — your soil reports and advice history are saved.
      </p>

      <div>
        <label className="field-label" htmlFor="farmer-search-input">
          {t("shell.searchPlaceholder")}
        </label>
        <div className="search-input-group">
          <input
            id="farmer-search-input"
            className="field-input"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("shell.searchPlaceholder")}
            aria-describedby="farmer-search-hint"
          />
          <button
            type="button"
            className="btn-primary"
            onClick={() => void runSearch(query.trim())}
            disabled={busy || query.trim().length < MIN_FARMER_SEARCH_LENGTH}
          >
            <Icon name="search" size={20} />
            {busy ? t("common.loading") : t("common.search")}
          </button>
        </div>
        {isQueryTooShort && (
          <p id="farmer-search-hint" className="hint-text">
            {t("feedback.minSearchLength")}
          </p>
        )}
      </div>

      <ActiveFarmerBanner />

      {error && <ErrorNotice message={error} onDismiss={() => setError(null)} />}

      {results.length > 0 ? (
        <div className="search-results-list">
          {results.map((farmer) => {
            const placeLine = [farmer.village, farmer.district].filter(Boolean).join(", ");
            return (
              <button
                key={farmer.farmer_id}
                type="button"
                className="search-result-card"
                onClick={() => setActiveFarmer(farmer)}
              >
                <div className="result-info">
                  <strong>{farmer.name}</strong>
                  {placeLine && <span style={{ fontWeight: 600 }}>{placeLine}</span>}
                  <span>
                    {farmer.farmer_id} · {farmer.mobile}
                  </span>
                </div>
                <span className="select-pill">This is me</span>
              </button>
            );
          })}
        </div>
      ) : hasSearched && !busy && !error ? (
        <p className="no-results-text">{t("shell.noSearchResults")}</p>
      ) : null}
    </section>
  );
}

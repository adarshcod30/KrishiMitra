"use client";

import { useCallback, useRef, useState } from "react";

import { AsyncSection } from "@/components/ui/AsyncState";
import { Icon } from "@/components/ui/Icons";
import { PageHeader } from "@/components/ui/PageHeader";
import { useLanguage } from "@/contexts/LanguageContext";
import { fetchMarketPrices } from "@/lib/api";
import { useAsyncResource } from "@/lib/hooks";

const iconTitleStyle = {
  display: "flex",
  alignItems: "center",
  gap: "0.5rem",
} as const;

const POPULAR_CROPS = ["Wheat", "Rice", "Potato", "Tomato", "Onion", "Chilli", "Cotton", "Maize"];

const STATES = [
  "Andhra Pradesh", "Assam", "Bihar", "Chhattisgarh", "Gujarat", "Haryana",
  "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka", "Kerala",
  "Madhya Pradesh", "Maharashtra", "Odisha", "Punjab", "Rajasthan", "Tamil Nadu",
  "Telangana", "Uttar Pradesh", "Uttarakhand", "West Bengal"
];

export function MarketPricesPage() {
  const { t, language } = useLanguage();
  const [cropFilter, setCropFilter] = useState("");
  const [stateFilter, setStateFilter] = useState("");

  // Filters are applied on demand (Search button), not on every keystroke, so
  // they are read through a ref instead of being loader dependencies.
  const filtersRef = useRef({ crop: "", state: "" });

  const loadPrices = useCallback(
    () =>
      fetchMarketPrices(language, {
        crop: filtersRef.current.crop || undefined,
        state: filtersRef.current.state || undefined,
      }),
    [language]
  );

  const pricesResource = useAsyncResource(loadPrices, t("feedback.loadFailed"));
  const priceCount = pricesResource.data?.length ?? 0;

  function applyFilters() {
    filtersRef.current = { crop: cropFilter, state: stateFilter };
    pricesResource.reload();
  }

  function resetFilters() {
    setCropFilter("");
    setStateFilter("");
    filtersRef.current = { crop: "", state: "" };
    pricesResource.reload();
  }

  const trendBadgeClass = (trend: string) => {
    if (trend === "up") return "badge-success";
    if (trend === "down") return "badge-danger";
    return "badge-info";
  };

  const trendLabel = (trend: string) => {
    if (trend === "up") return "Going up";
    if (trend === "down") return "Going down";
    return "Steady";
  };

  return (
    <div className="page-container">
      <PageHeader
        eyebrow={t("nav.market")}
        title={t("market.title")}
        description={t("market.subtitle")}
      />

      <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
        <section className="surface-card">
          <h3 className="section-title" style={iconTitleStyle}>
            <Icon name="search" size={22} />
            {t("market.filterTitle")}
          </h3>

          <div className="grid-2-cols">
            <div>
              <label className="field-label" htmlFor="market-crop">
                {t("farmer.crop")}
              </label>
              <select
                id="market-crop"
                className="field-select"
                value={cropFilter}
                onChange={(e) => setCropFilter(e.target.value)}
              >
                <option value="">All crops</option>
                {POPULAR_CROPS.map((crop) => (
                  <option key={crop} value={crop}>
                    {crop}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="field-label" htmlFor="market-state">
                {t("farmer.state")}
              </label>
              <select
                id="market-state"
                className="field-select"
                value={stateFilter}
                onChange={(e) => setStateFilter(e.target.value)}
              >
                <option value="">All states</option>
                {STATES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", marginTop: "1rem" }}>
            <button
              type="button"
              className="btn-primary"
              onClick={applyFilters}
              disabled={pricesResource.isLoading}
            >
              {pricesResource.isLoading ? t("common.loading") : t("common.search")}
            </button>
            <button type="button" className="btn-secondary" onClick={resetFilters}>
              {t("common.reset")}
            </button>
          </div>
        </section>

        <section className="surface-card">
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "0.75rem",
              flexWrap: "wrap",
            }}
          >
            <h3 className="section-title" style={iconTitleStyle}>
              <Icon name="market" size={22} />
              {t("market.priceTable")}
            </h3>
            {priceCount > 0 && (
              <span className="badge badge-info" style={{ marginBottom: "1rem" }}>
                {priceCount} {t("common.results")}
              </span>
            )}
          </div>

          <AsyncSection
            resource={pricesResource}
            icon="market"
            emptyMessage={t("market.empty")}
            isEmpty={(items) => items.length === 0}
          >
            {(prices) => (
              <div>
                {prices.map((item, i) => (
                  <div key={`${item.crop}-${item.mandi}-${i}`} className="list-row">
                    <div>
                      <div style={{ fontSize: "1.15rem", fontWeight: 700, color: "var(--ink)" }}>
                        {item.crop}
                      </div>
                      <div style={{ fontSize: "0.95rem", color: "var(--ink-secondary)" }}>
                        {item.mandi}, {item.state}
                      </div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "flex-end",
                          gap: "0.1rem",
                          fontSize: "1.5rem",
                          fontWeight: 700,
                          color: "var(--ink)",
                          lineHeight: 1.2,
                        }}
                      >
                        <Icon name="rupee" size={22} />
                        {item.modal_price_inr_quintal}
                      </div>
                      <div style={{ fontSize: "0.9rem", color: "var(--ink-secondary)", fontWeight: 600 }}>
                        per quintal
                      </div>
                      <span className={`badge ${trendBadgeClass(item.trend)}`} style={{ marginTop: "0.3rem" }}>
                        {trendLabel(item.trend)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </AsyncSection>
        </section>
      </div>
    </div>
  );
}

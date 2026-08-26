"use client";

import { useCallback, useRef, useState } from "react";

import { AsyncSection } from "@/components/ui/AsyncState";
import { PageHeader } from "@/components/ui/PageHeader";
import { useLanguage } from "@/contexts/LanguageContext";
import { fetchMarketPrices } from "@/lib/api";
import { useAsyncResource } from "@/lib/hooks";

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

  const trendIcon = (trend: string) => {
    if (trend === "up") return "📈";
    if (trend === "down") return "📉";
    return "➡️";
  };

  return (
    <div className="page-container">
      <PageHeader
        eyebrow={t("nav.market")}
        title={t("market.title")}
        description={t("market.subtitle")}
      />

      <section className="surface-card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="mb-0">🔍 {t("market.filterTitle")}</h3>
        </div>
        
        <div className="flex flex-col gap-4">
          <div className="inline-actions">
            <input
              placeholder={t("market.cropPlaceholder")}
              value={cropFilter}
              onChange={(e) => setCropFilter(e.target.value)}
            />
            <input
              placeholder={t("market.statePlaceholder")}
              value={stateFilter}
              onChange={(e) => setStateFilter(e.target.value)}
            />
            <button
              type="button"
              className="primary-btn small-btn"
              onClick={applyFilters}
              disabled={pricesResource.isLoading}
            >
              {pricesResource.isLoading ? t("common.loading") : t("common.search")}
            </button>
          </div>

          <div className="flex flex-wrap gap-2 pt-2 border-t border-line">
            <span className="text-xs font-bold text-muted uppercase tracking-widest mr-2 self-center">Popular Crops:</span>
            {["Wheat", "Rice", "Potato", "Tomato", "Onion", "Chilli", "Cotton", "Maize"].map(crop => (
              <button
                key={crop}
                type="button"
                className={`badge ${cropFilter.toLowerCase() === crop.toLowerCase() ? 'badge-brand' : 'bg-subtle text-ink-secondary'} cursor-pointer hover:bg-brand-subtle transition-colors`}
                onClick={() => {
                  setCropFilter(crop);
                  // We could auto-trigger search here too if desired
                }}
              >
                {crop}
              </button>
            ))}
            <button 
              type="button" 
              className="text-xs text-brand font-bold underline ml-auto"
              onClick={() => {
                setCropFilter("");
                setStateFilter("");
                filtersRef.current = { crop: "", state: "" };
                pricesResource.reload();
              }}
            >
              {t("common.reset")}
            </button>
          </div>
        </div>
      </section>

      <section className="surface-card">
        <div className="flex items-center justify-between mb-6">
          <h3 className="mb-0">📊 {t("market.priceTable")}</h3>
          {priceCount > 0 && (
            <div className="text-xs font-bold text-muted bg-subtle px-3 py-1 rounded-full uppercase tracking-widest">
              {priceCount} {t("common.results")}
            </div>
          )}
        </div>

        <AsyncSection
          resource={pricesResource}
          icon="📊"
          emptyMessage={t("market.empty")}
          isEmpty={(items) => items.length === 0}
        >
          {(prices) => (
          <div className="recommendation-grid animate-in fade-in duration-500">
            {prices.map((item, i) => (
              <div key={`${item.crop}-${item.mandi}-${i}`} className="premium-card">
                <div className="flex items-start justify-between">
                  <div className="recommendation-header">
                    <div className="crop-icon-wrapper" style={{ width: '48px', height: '48px', fontSize: '1.5rem' }}>🌾</div>
                    <div className="recommendation-title-group">
                      <h4 className="crop-name" style={{ fontSize: '1.25rem' }}>{item.crop}</h4>
                      <p className="text-xs text-muted font-bold tracking-tight">{item.mandi}</p>
                    </div>
                  </div>
                  <div className={`status-badge ${item.trend === 'up' ? 'danger' : item.trend === 'down' ? 'success' : 'info'}`}>
                    {trendIcon(item.trend)} {item.trend.toUpperCase()}
                  </div>
                </div>

                <div className="mt-4 pt-4 border-t border-line flex items-center justify-between">
                   <div className="flex flex-col">
                      <span className="text-xs font-bold text-muted uppercase tracking-tighter">Current Price</span>
                      <span className="text-xl font-black text-ink">₹{item.modal_price_inr_quintal}<span className="text-xs font-normal">/q</span></span>
                   </div>
                   <div className="text-right">
                      <span className="text-xs font-bold text-muted uppercase tracking-tighter">Location</span>
                      <p className="text-sm font-semibold">{item.state}</p>
                   </div>
                </div>
              </div>
            ))}
          </div>
          )}
        </AsyncSection>
      </section>
    </div>
  );
}

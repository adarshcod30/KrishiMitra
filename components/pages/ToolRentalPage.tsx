"use client";

import { useCallback, useRef, useState } from "react";

import { AsyncSection } from "@/components/ui/AsyncState";
import { Icon } from "@/components/ui/Icons";
import { useLanguage } from "@/contexts/LanguageContext";
import { fetchRentalTools } from "@/lib/api";
import { useAsyncResource } from "@/lib/hooks";

export function ToolRentalPage() {
  const { t, language } = useLanguage();
  const [location, setLocation] = useState("");

  // Applied on demand (Search / Enter), not on every keystroke.
  const submittedLocationRef = useRef("");

  const loadTools = useCallback(
    () => fetchRentalTools(language, { location: submittedLocationRef.current || undefined }),
    [language]
  );

  const toolsResource = useAsyncResource(loadTools, t("feedback.loadFailed"));

  function submitLocation() {
    submittedLocationRef.current = location.trim();
    toolsResource.reload();
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">{t("nav.rental")}</h1>
        <p className="page-subtitle">{t("rental.subtitle")}</p>
      </div>

      <section className="surface-card" style={{ marginBottom: "1.25rem" }}>
        <label className="field-label" htmlFor="rental-location">
          {t("rental.searchTitle")}
        </label>
        <div className="search-input-group">
          <input
            id="rental-location"
            className="field-input"
            placeholder={t("rental.locationPlaceholder")}
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                submitLocation();
              }
            }}
          />
          <button
            type="button"
            className="btn-primary"
            onClick={submitLocation}
            disabled={toolsResource.isLoading}
          >
            <Icon name="search" size={20} />
            {toolsResource.isLoading ? t("common.loading") : t("common.search")}
          </button>
        </div>
      </section>

      <section className="surface-card">
        <h3 className="section-title">{t("rental.availableTools")}</h3>
        <AsyncSection
          resource={toolsResource}
          icon="tools"
          emptyMessage={t("rental.empty")}
          isEmpty={(items) => items.length === 0}
        >
          {(tools) => (
            <div className="recommendation-grid">
              {tools.map((tool, i) => (
                <article key={`${tool.name}-${i}`} className="recommendation-card">
                  <div className="recommendation-header">
                    <div className="crop-icon-wrapper">
                      <Icon name="tools" size={28} />
                    </div>
                    <div className="recommendation-title-group">
                      <h4 className="crop-name" style={{ fontSize: "1.15rem", lineHeight: 1.35 }}>
                        {tool.name}
                      </h4>
                    </div>
                  </div>

                  <div className="stat-item">
                    <span className="stat-label">Rent per hour</span>
                    {/* Some listings (e.g. eNAM logistics) have no published
                        rate — say so instead of rendering a bare rupee sign. */}
                    {typeof tool.hourly_rate_inr === "number" ? (
                      <span className="stat-value">₹{tool.hourly_rate_inr}</span>
                    ) : (
                      <span className="stat-value" style={{ color: "var(--ink-secondary)" }}>
                        Ask provider
                      </span>
                    )}
                  </div>

                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.45rem",
                      color: "var(--ink-secondary)",
                      fontSize: "0.98rem"
                    }}
                  >
                    <Icon name="location" size={18} />
                    <span>
                      {tool.location} · {tool.provider}
                    </span>
                  </div>

                  {/* `availability` is a full sentence for catalogue entries
                      ("Offline catalogue entry. Confirm live availability..."),
                      so it is laid out as text. A pill badge cannot hold a
                      100-character sentence without overflowing its radius. */}
                  <div style={{ marginTop: "0.15rem" }}>
                    <span className="stat-label">{t("rental.availability")}</span>
                    <p className="field-help" style={{ margin: "0.2rem 0 0" }}>
                      {tool.availability}
                    </p>
                  </div>
                </article>
              ))}
            </div>
          )}
        </AsyncSection>
      </section>
    </div>
  );
}

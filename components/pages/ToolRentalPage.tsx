"use client";

import { useCallback, useRef, useState } from "react";

import { AsyncSection } from "@/components/ui/AsyncState";
import { PageHeader } from "@/components/ui/PageHeader";
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
      <PageHeader
        eyebrow={t("nav.rental")}
        title={t("rental.title")}
        description={t("rental.subtitle")}
      />

      <section className="surface-card">
        <h3>🔍 {t("rental.searchTitle")}</h3>
        <div className="inline-actions">
          <input
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
            className="primary-btn small-btn"
            onClick={submitLocation}
            disabled={toolsResource.isLoading}
          >
            {toolsResource.isLoading ? t("common.loading") : t("common.search")}
          </button>
        </div>
      </section>

      <section className="surface-card">
        <h3>🚜 {t("rental.availableTools")}</h3>
        <AsyncSection
          resource={toolsResource}
          icon="🚜"
          emptyMessage={t("rental.empty")}
          isEmpty={(items) => items.length === 0}
        >
          {(tools) => (
            <div className="feature-grid">
              {tools.map((tool, i) => (
                <div key={`${tool.name}-${i}`} className="tool-card">
                  <h4>{tool.name}</h4>
                  <div className="tool-rate">₹{tool.hourly_rate_inr}/hr</div>
                  <div className="tool-meta">
                    📍 {tool.location} · {tool.provider}
                  </div>
                  <div className="tool-meta">
                    {t("rental.availability")}: <span className="badge badge-success">{tool.availability}</span>
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

"use client";

import { useEffect, useState } from "react";

import { PageHeader } from "@/components/ui/PageHeader";
import { useLanguage } from "@/contexts/LanguageContext";
import { fetchRentalTools } from "@/lib/api";
import type { RentalTool } from "@/lib/types";

export function ToolRentalPage() {
  const { t, language } = useLanguage();
  const [tools, setTools] = useState<RentalTool[]>([]);
  const [location, setLocation] = useState("");
  const [busy, setBusy] = useState(false);

  async function loadTools() {
    setBusy(true);
    try {
      const result = await fetchRentalTools(language, {
        location: location || undefined,
      });
      setTools(result);
    } catch {
      setTools([]);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    loadTools();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [language]);

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
          />
          <button type="button" className="primary-btn small-btn" onClick={loadTools}>
            {busy ? t("common.loading") : t("common.search")}
          </button>
        </div>
      </section>

      <section className="surface-card">
        <h3>🚜 {t("rental.availableTools")}</h3>
        {tools.length > 0 ? (
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
        ) : (
          <p className="muted-copy">{busy ? t("common.loading") : t("rental.empty")}</p>
        )}
      </section>
    </div>
  );
}

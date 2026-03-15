"use client";

import { useState } from "react";

import { ActiveFarmerBanner } from "@/components/farmers/ActiveFarmerBanner";
import { PageHeader } from "@/components/ui/PageHeader";
import { useFarmerSession } from "@/contexts/FarmerSessionContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { fetchSchemes } from "@/lib/api";
import type { SchemeItem } from "@/lib/types";

const FARMER_TYPES = ["small", "marginal", "medium", "large"] as const;
const STATES = [
  "Andhra Pradesh", "Assam", "Bihar", "Chhattisgarh", "Gujarat", "Haryana", 
  "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka", "Kerala", 
  "Madhya Pradesh", "Maharashtra", "Odisha", "Punjab", "Rajasthan", "Tamil Nadu", 
  "Telangana", "Uttar Pradesh", "Uttarakhand", "West Bengal"
];

export function SchemesPage() {
  const { t, language } = useLanguage();
  const { activeFarmer } = useFarmerSession();
  const [input, setInput] = useState({
    farmer_type: "small" as (typeof FARMER_TYPES)[number],
    land_size_acres: 2,
    annual_income_lakh: 3,
    state: activeFarmer?.state || "Uttar Pradesh",
  });
  const [schemes, setSchemes] = useState<SchemeItem[]>([]);
  const [busy, setBusy] = useState(false);

  async function handleFind() {
    setBusy(true);
    try {
      const response = await fetchSchemes({
        ...input,
        language,
        farmer_id: activeFarmer?.farmer_id,
        mobile: activeFarmer?.mobile,
      });
      setSchemes(response.schemes);
    } catch {
      setSchemes([]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-container">
      <PageHeader
        eyebrow={t("nav.schemes")}
        title={t("schemes.title")}
        description={t("schemes.subtitle")}
      />
      <ActiveFarmerBanner />

      <section className="dashboard-grid mt-4">
        <article className="surface-card">
          <h3>🏛️ {t("schemes.inputTitle")}</h3>
          <div className="form-grid">
            <label className="field">
              <span>{t("schemes.farmerType")}</span>
              <select
                value={input.farmer_type}
                onChange={(e) => setInput((p) => ({ ...p, farmer_type: e.target.value as typeof input.farmer_type }))}
              >
                {FARMER_TYPES.map((ft) => (
                  <option key={ft} value={ft}>{t(`schemes.type_${ft}`)}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>{t("farmer.farmSize")}</span>
              <input type="number" value={input.land_size_acres}
                onChange={(e) => setInput((p) => ({ ...p, land_size_acres: Number(e.target.value) }))}
              />
            </label>
            <label className="field">
              <span>{t("schemes.income")}</span>
              <input type="number" step="0.5" value={input.annual_income_lakh}
                onChange={(e) => setInput((p) => ({ ...p, annual_income_lakh: Number(e.target.value) }))}
              />
            </label>
            <label className="field">
              <span>{t("farmer.state")}</span>
              <select
                value={input.state}
                onChange={(e) => setInput((p) => ({ ...p, state: e.target.value }))}
              >
                {STATES.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </label>
          </div>
          <button type="button" className="primary-btn" onClick={handleFind}>
            {busy ? t("common.loading") : t("schemes.findSchemes")}
          </button>
        </article>

        <article className="surface-card">
          <div className="flex items-center justify-between mb-6">
            <h3 className="mb-0">📋 {t("schemes.results")}</h3>
            {schemes.length > 0 && (
              <div className="status-badge info">
                🏛️ {schemes.length} {t("nav.schemes")}
              </div>
            )}
          </div>

          {schemes.length > 0 ? (
            <div className="result-layout animate-in slide-in-from-bottom-4 duration-500">
              {schemes.map((scheme) => (
                <div key={scheme.id} className="recommendation-card">
                  <div className="recommendation-header">
                    <div className="crop-icon-wrapper" style={{ width: '48px', height: '48px', fontSize: '1.5rem' }}>🏛️</div>
                    <div className="recommendation-title-group">
                      <h4 className="crop-name" style={{ fontSize: '1.25rem' }}>{scheme.title}</h4>
                    </div>
                  </div>

                  <p className="tips-content">{scheme.description}</p>

                  <div className="tips-section mt-4">
                    <div className="flex items-center gap-2 mb-2">
                       <span className="text-xl">👤</span>
                       <span className="tips-title mb-0">{t("schemes.eligibility")}</span>
                    </div>
                    <p className="text-sm text-ink-secondary">{scheme.eligibility}</p>
                  </div>

                  {scheme.link && (
                    <div className="mt-4 pt-4 border-t border-dashed border-line">
                      <a 
                        href={scheme.link} 
                        target="_blank" 
                        rel="noopener noreferrer"
                        className="badge badge-brand flex items-center justify-center py-2 text-sm no-underline"
                      >
                        {t("schemes.applyNow")} →
                      </a>
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state-illust">
              <div className="illust-icon">🏛️</div>
              <p className="muted-copy">
                {busy ? t("common.loading") : (schemes.length === 0 && input.state ? "No specific schemes found for this criteria. Try adjusting filters." : t("schemes.empty"))}
              </p>
            </div>
          )}
        </article>
      </section>
    </div>
  );
}

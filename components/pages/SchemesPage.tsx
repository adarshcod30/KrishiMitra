"use client";

import { useState } from "react";

import { ActiveFarmerBanner } from "@/components/farmers/ActiveFarmerBanner";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/ui/AsyncState";
import { Icon } from "@/components/ui/Icons";
import { PageHeader } from "@/components/ui/PageHeader";
import { useFarmerSession } from "@/contexts/FarmerSessionContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { fetchSchemes } from "@/lib/api";
import { toUserMessage } from "@/lib/errors";
import type { SchemeItem } from "@/lib/types";

const iconTitleStyle = {
  display: "flex",
  alignItems: "center",
  gap: "0.5rem",
} as const;

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
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  async function handleFind() {
    setBusy(true);
    setError(null);
    try {
      const response = await fetchSchemes({
        ...input,
        language,
        farmer_id: activeFarmer?.farmer_id,
        mobile: activeFarmer?.mobile,
      });
      setSchemes(response.schemes);
      setHasSearched(true);
    } catch (caught) {
      setSchemes([]);
      setHasSearched(true);
      setError(toUserMessage(caught, t("feedback.error")));
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

      <section className="grid-2-cols mt-4">
        <article className="surface-card">
          <h3 className="section-title" style={iconTitleStyle}>
            <Icon name="scheme" size={22} />
            {t("schemes.inputTitle")}
          </h3>
          <div className="form-stack">
            <div>
              <label className="field-label" htmlFor="scheme-type">
                {t("schemes.farmerType")}
              </label>
              <select
                id="scheme-type"
                className="field-select"
                value={input.farmer_type}
                onChange={(e) => setInput((p) => ({ ...p, farmer_type: e.target.value as typeof input.farmer_type }))}
              >
                {FARMER_TYPES.map((ft) => (
                  <option key={ft} value={ft}>{t(`schemes.type_${ft}`)}</option>
                ))}
              </select>
              <p className="field-help">Based on how much land you own. Not sure? Pick Small.</p>
            </div>
            <div>
              <label className="field-label" htmlFor="scheme-land">
                {t("farmer.farmSize")}
              </label>
              <input
                id="scheme-land"
                className="field-input"
                type="number"
                inputMode="decimal"
                value={input.land_size_acres}
                onChange={(e) => setInput((p) => ({ ...p, land_size_acres: Number(e.target.value) }))}
              />
              <p className="field-help">How much land you farm, in acres.</p>
            </div>
            <div>
              <label className="field-label" htmlFor="scheme-income">
                {t("schemes.income")}
              </label>
              <input
                id="scheme-income"
                className="field-input"
                type="number"
                step="0.5"
                inputMode="decimal"
                value={input.annual_income_lakh}
                onChange={(e) => setInput((p) => ({ ...p, annual_income_lakh: Number(e.target.value) }))}
              />
              <p className="field-help">Your family&apos;s income for one full year. 1 lakh = 1,00,000 rupees.</p>
            </div>
            <div>
              <label className="field-label" htmlFor="scheme-state">
                {t("farmer.state")}
              </label>
              <select
                id="scheme-state"
                className="field-select"
                value={input.state}
                onChange={(e) => setInput((p) => ({ ...p, state: e.target.value }))}
              >
                {STATES.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
          </div>
          {error && <ErrorNotice message={error} onDismiss={() => setError(null)} />}
          <div style={{ marginTop: "1rem" }}>
            <button type="button" className="btn-primary" onClick={handleFind} disabled={busy}>
              {busy ? t("common.loading") : t("schemes.findSchemes")}
            </button>
          </div>
        </article>

        <article className="surface-card">
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
              <Icon name="scheme" size={22} />
              {t("schemes.results")}
            </h3>
            {schemes.length > 0 && (
              <span className="badge badge-info" style={{ marginBottom: "1rem" }}>
                {schemes.length} {t("common.results")}
              </span>
            )}
          </div>

          {busy ? (
            <LoadingState icon="scheme" />
          ) : schemes.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              {schemes.map((scheme) => (
                <div key={scheme.id} className="result-card">
                  <h4
                    style={{
                      fontSize: "1.25rem",
                      fontWeight: 700,
                      color: "var(--ink)",
                      marginBottom: "0.4rem",
                      lineHeight: 1.3,
                    }}
                  >
                    {scheme.title}
                  </h4>

                  <p style={{ fontSize: "1rem", color: "var(--ink)", lineHeight: 1.55 }}>
                    {scheme.description}
                  </p>

                  <p style={{ fontSize: "1rem", color: "var(--ink)", lineHeight: 1.55, marginTop: "0.6rem" }}>
                    <strong>{t("schemes.eligibility")}:</strong> {scheme.eligibility}
                  </p>

                  <hr className="divider" />

                  <p style={{ fontSize: "1rem", fontWeight: 700, color: "var(--ink)", marginBottom: "0.5rem" }}>
                    How to apply
                  </p>
                  {scheme.link ? (
                    <a
                      className="btn-secondary"
                      href={scheme.link}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {t("schemes.applyNow")}
                      <Icon name="arrow-right" size={18} />
                    </a>
                  ) : (
                    <p style={{ fontSize: "1rem", color: "var(--ink-secondary)", lineHeight: 1.55 }}>
                      Ask at your nearest agriculture office or Common Service Centre (CSC).
                    </p>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              icon="scheme"
              message={
                hasSearched
                  ? "No schemes matched your details. Try a different farmer type or income."
                  : t("schemes.empty")
              }
            />
          )}
        </article>
      </section>
    </div>
  );
}

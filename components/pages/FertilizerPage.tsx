"use client";

import { useState } from "react";

import { ActiveFarmerBanner } from "@/components/farmers/ActiveFarmerBanner";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/ui/AsyncState";
import { Icon } from "@/components/ui/Icons";
import { PageHeader } from "@/components/ui/PageHeader";
import { useFarmerSession } from "@/contexts/FarmerSessionContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { recommendFertilizer } from "@/lib/api";
import { toUserMessage } from "@/lib/errors";
import type { FertilizerResponse } from "@/lib/types";

const iconTitleStyle = {
  display: "flex",
  alignItems: "center",
  gap: "0.5rem",
} as const;

export function FertilizerPage() {
  const { t, language } = useLanguage();
  const { activeFarmer } = useFarmerSession();
  const [input, setInput] = useState({
    crop: "wheat",
    soil_type: "loam",
    N: 40,
    P: 30,
    K: 25,
    ph: 6.5,
  });
  const [result, setResult] = useState<FertilizerResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRecommend() {
    setBusy(true);
    setError(null);
    try {
      const response = await recommendFertilizer({
        ...input,
        language,
        farmer_id: activeFarmer?.farmer_id,
        mobile: activeFarmer?.mobile,
      });
      setResult(response);
    } catch (caught) {
      // Without this the rejection is unhandled and the spinner just stops.
      setError(toUserMessage(caught, t("feedback.error")));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-container">
      <PageHeader
        eyebrow={t("nav.fertilizer")}
        title={t("fertilizer.title")}
        description={t("fertilizer.subtitle")}
      />
      <ActiveFarmerBanner />

      <section className="grid-2-cols mt-4">
        <article className="surface-card">
          <h3 className="section-title" style={iconTitleStyle}>
            <Icon name="fertilizer" size={22} />
            {t("fertilizer.inputTitle")}
          </h3>
          <div className="form-stack">
            <div>
              <label className="field-label" htmlFor="fert-crop">
                {t("farmer.crop")}
              </label>
              <input
                id="fert-crop"
                className="field-input"
                value={input.crop}
                onChange={(e) => setInput((p) => ({ ...p, crop: e.target.value }))}
              />
              <p className="field-help">The crop you are growing now, e.g. wheat.</p>
            </div>
            <div>
              <label className="field-label" htmlFor="fert-soil">
                {t("farmer.soilType")}
              </label>
              <input
                id="fert-soil"
                className="field-input"
                value={input.soil_type}
                onChange={(e) => setInput((p) => ({ ...p, soil_type: e.target.value }))}
              />
              <p className="field-help">Loam, clay, sandy or black soil.</p>
            </div>
            <div>
              <label className="field-label" htmlFor="fert-n">
                {t("common.nitrogen")} (mg/kg)
              </label>
              <input
                id="fert-n"
                className="field-input"
                type="number"
                inputMode="numeric"
                value={input.N}
                onChange={(e) => setInput((p) => ({ ...p, N: Number(e.target.value) }))}
              />
              <p className="field-help">From your soil test report. Normal range 0-140.</p>
            </div>
            <div>
              <label className="field-label" htmlFor="fert-p">
                {t("common.phosphorus")} (mg/kg)
              </label>
              <input
                id="fert-p"
                className="field-input"
                type="number"
                inputMode="numeric"
                value={input.P}
                onChange={(e) => setInput((p) => ({ ...p, P: Number(e.target.value) }))}
              />
              <p className="field-help">From your soil test report. Normal range 5-145.</p>
            </div>
            <div>
              <label className="field-label" htmlFor="fert-k">
                {t("common.potassium")} (mg/kg)
              </label>
              <input
                id="fert-k"
                className="field-input"
                type="number"
                inputMode="numeric"
                value={input.K}
                onChange={(e) => setInput((p) => ({ ...p, K: Number(e.target.value) }))}
              />
              <p className="field-help">From your soil test report. Normal range 5-205.</p>
            </div>
            <div>
              <label className="field-label" htmlFor="fert-ph">
                {t("common.soilPh")}
              </label>
              <input
                id="fert-ph"
                className="field-input"
                type="number"
                step="0.1"
                inputMode="decimal"
                value={input.ph}
                onChange={(e) => setInput((p) => ({ ...p, ph: Number(e.target.value) }))}
              />
              <p className="field-help">7 is neutral. Most crops grow well between 6 and 7.5.</p>
            </div>
          </div>
          {error && <ErrorNotice message={error} onDismiss={() => setError(null)} />}
          <div style={{ marginTop: "1rem" }}>
            <button type="button" className="btn-primary" onClick={handleRecommend} disabled={busy}>
              {busy ? t("common.loading") : t("common.predict")}
            </button>
          </div>
        </article>

        <article className="surface-card">
          <h3 className="section-title" style={iconTitleStyle}>
            <Icon name="check" size={22} />
            {t("fertilizer.outputTitle")}
          </h3>

          {busy && !result ? (
            <LoadingState icon="fertilizer" />
          ) : result ? (
            <div className="result-card result-card-success">
              <span className="stat-label">{t("common.bestMatch")}</span>
              <p className="stat-value" style={{ marginBottom: "0.5rem" }}>
                {result.blend}
              </p>
              <p style={{ fontSize: "1rem", color: "var(--ink)", lineHeight: 1.55 }}>
                {result.rationale}
              </p>
              <hr className="divider" />
              <h4 className="section-title" style={iconTitleStyle}>
                <Icon name="calendar" size={20} />
                {t("fertilizer.scheduleTitle")}
              </h4>
              <ol
                style={{
                  paddingLeft: "1.4rem",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.6rem",
                }}
              >
                {result.schedule.map((step, idx) => (
                  <li key={idx} style={{ fontSize: "1rem", color: "var(--ink)", lineHeight: 1.55 }}>
                    {step}
                  </li>
                ))}
              </ol>
            </div>
          ) : (
            <EmptyState icon="fertilizer" message={t("fertilizer.empty")} />
          )}
        </article>
      </section>
    </div>
  );
}

"use client";

import { useState } from "react";

import { ActiveFarmerBanner } from "@/components/farmers/ActiveFarmerBanner";
import { ErrorNotice, LoadingState } from "@/components/ui/AsyncState";
import { PageHeader } from "@/components/ui/PageHeader";
import { useFarmerSession } from "@/contexts/FarmerSessionContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { recommendFertilizer } from "@/lib/api";
import { toUserMessage } from "@/lib/errors";
import type { FertilizerResponse } from "@/lib/types";

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

      <section className="dashboard-grid mt-4">
        <article className="surface-card">
          <h3>🧬 {t("fertilizer.inputTitle")}</h3>
          <div className="form-grid">
            <label className="field">
              <span>{t("farmer.crop")}</span>
              <input value={input.crop} onChange={(e) => setInput((p) => ({ ...p, crop: e.target.value }))} />
            </label>
            <label className="field">
              <span>{t("farmer.soilType")}</span>
              <input value={input.soil_type} onChange={(e) => setInput((p) => ({ ...p, soil_type: e.target.value }))} />
            </label>
            <label className="field">
              <span>{t("common.nitrogen")} (mg/kg)</span>
              <input type="number" value={input.N} onChange={(e) => setInput((p) => ({ ...p, N: Number(e.target.value) }))} />
            </label>
            <label className="field">
              <span>{t("common.phosphorus")} (mg/kg)</span>
              <input type="number" value={input.P} onChange={(e) => setInput((p) => ({ ...p, P: Number(e.target.value) }))} />
            </label>
            <label className="field">
              <span>{t("common.potassium")} (mg/kg)</span>
              <input type="number" value={input.K} onChange={(e) => setInput((p) => ({ ...p, K: Number(e.target.value) }))} />
            </label>
            <label className="field">
              <span>{t("common.soilPh")}</span>
              <input type="number" step="0.1" value={input.ph} onChange={(e) => setInput((p) => ({ ...p, ph: Number(e.target.value) }))} />
            </label>
          </div>
          {error && <ErrorNotice message={error} onDismiss={() => setError(null)} />}
          <button type="button" className="primary-btn" onClick={handleRecommend} disabled={busy}>
            {busy ? t("common.loading") : t("common.predict")}
          </button>
        </article>

        <article className="surface-card">
          <div className="flex items-center justify-between mb-6">
            <h3 className="mb-0">📋 {t("fertilizer.outputTitle")}</h3>
            {result && (
              <div className="status-badge success">
                🧬 {t("nav.fertilizer")}
              </div>
            )}
          </div>

          {busy && !result ? (
            <LoadingState icon="🧬" />
          ) : result ? (
            <div className="recommendation-card top-choice animate-in slide-in-from-bottom-4 duration-500">
              <div className="recommendation-header">
                <div className="crop-icon-wrapper">🧬</div>
                <div className="recommendation-title-group">
                  <h4 className="crop-name">{result.blend}</h4>
                  <p className="text-sm text-ink-secondary mt-1">{result.rationale}</p>
                </div>
              </div>

              <div className="tips-section mt-6">
                <div className="flex items-center gap-2 mb-4">
                  <span className="text-xl">📅</span>
                  <span className="tips-title mb-0">{t("fertilizer.scheduleTitle")}</span>
                </div>
                <div className="premium-list">
                  {result.schedule.map((step, idx) => (
                    <div key={idx} className="premium-list-item">
                      <span className="icon">◈</span>
                      <span className="text">{step}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="empty-state-illust">
              <div className="illust-icon">🧬</div>
              <p className="muted-copy">{t("fertilizer.empty")}</p>
            </div>
          )}
        </article>
      </section>
    </div>
  );
}

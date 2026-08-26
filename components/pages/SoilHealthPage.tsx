"use client";

import { useState } from "react";

import { ActiveFarmerBanner } from "@/components/farmers/ActiveFarmerBanner";
import { ErrorNotice, LoadingState } from "@/components/ui/AsyncState";
import { PageHeader } from "@/components/ui/PageHeader";
import { useFarmerSession } from "@/contexts/FarmerSessionContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { analyzeSoil } from "@/lib/api";
import { toUserMessage } from "@/lib/errors";
import type { SoilAnalysisResponse } from "@/lib/types";

export function SoilHealthPage() {
  const { t, language } = useLanguage();
  const { activeFarmer } = useFarmerSession();
  const [input, setInput] = useState({
    N: 42,
    P: 28,
    K: 24,
    ph: 6.4,
    soil_type: "loam",
    crop: "wheat"
  });
  const [result, setResult] = useState<SoilAnalysisResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleAnalyze() {
    setBusy(true);
    setError(null);
    try {
      const response = await analyzeSoil({
        ...input,
        language,
        farmer_id: activeFarmer?.farmer_id,
        mobile: activeFarmer?.mobile
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
        eyebrow={t("nav.soil")}
        title={t("soil.title")}
        description={t("soil.subtitle")}
      />
      <ActiveFarmerBanner />

      <section className="dashboard-grid mt-4">
        <article className="surface-card">
          <h3>{t("soil.inputTitle")}</h3>
          <div className="form-grid">
            <label className="field">
              <span>{t("common.nitrogen")}</span>
              <input
                type="number"
                value={input.N}
                onChange={(event) => setInput((prev) => ({ ...prev, N: Number(event.target.value) }))}
              />
            </label>
            <label className="field">
              <span>{t("common.phosphorus")}</span>
              <input
                type="number"
                value={input.P}
                onChange={(event) => setInput((prev) => ({ ...prev, P: Number(event.target.value) }))}
              />
            </label>
            <label className="field">
              <span>{t("common.potassium")}</span>
              <input
                type="number"
                value={input.K}
                onChange={(event) => setInput((prev) => ({ ...prev, K: Number(event.target.value) }))}
              />
            </label>
            <label className="field">
              <span>{t("common.soilPh")}</span>
              <input
                type="number"
                step="0.1"
                value={input.ph}
                onChange={(event) =>
                  setInput((prev) => ({ ...prev, ph: Number(event.target.value) }))
                }
              />
            </label>
            <label className="field">
              <span>{t("farmer.soilType")}</span>
              <input
                value={input.soil_type}
                onChange={(event) =>
                  setInput((prev) => ({ ...prev, soil_type: event.target.value }))
                }
              />
            </label>
            <label className="field">
              <span>{t("farmer.crop")}</span>
              <input
                value={input.crop}
                onChange={(event) => setInput((prev) => ({ ...prev, crop: event.target.value }))}
              />
            </label>
          </div>
          {error && <ErrorNotice message={error} onDismiss={() => setError(null)} />}
          <button type="button" className="primary-btn" onClick={handleAnalyze} disabled={busy}>
            {busy ? t("common.loading") : t("common.predict")}
          </button>
        </article>

        <article className="surface-card">
          <div className="flex items-center justify-between mb-6">
            <h3 className="mb-0">{t("soil.outputTitle")}</h3>
            {result && (
              <div className="status-badge info">
                🧪 {t("nav.soil")}
              </div>
            )}
          </div>

          {busy && !result ? (
            <LoadingState icon="🧪" />
          ) : result ? (
            <div className="recommendation-card top-choice animate-in slide-in-from-bottom-4 duration-500">
              <div className="recommendation-header">
                <div className="crop-icon-wrapper">🧪</div>
                <div className="recommendation-title-group">
                  <h4 className="crop-name">{result.soil_health_status}</h4>
                  <div className="text-sm text-ink-secondary mt-1">
                    {t("soil.subtitle")}
                  </div>
                </div>
              </div>

              <div className="grid-2-cols mt-6">
                <div className="tips-section">
                  <div className="flex items-center gap-2 mb-4">
                    <span className="text-xl">⚠️</span>
                    <span className="tips-title mb-0">{t("common.nutrientAlerts")}</span>
                  </div>
                  <div className="premium-list">
                    {result.nutrient_alerts.map((alert) => (
                      <div key={alert} className="premium-list-item">
                        <span className="icon">◈</span>
                        <span className="text">{alert}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="tips-section">
                  <div className="flex items-center gap-2 mb-4">
                    <span className="text-xl">🛠️</span>
                    <span className="tips-title mb-0">{t("common.actions")}</span>
                  </div>
                  <div className="premium-list">
                    {result.soil_actions.map((action) => (
                      <div key={action} className="premium-list-item">
                        <span className="icon">✓</span>
                        <span className="text">{action}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {result.recommended_crop_focus && result.recommended_crop_focus.length > 0 && (
                <div className="actions-panel mt-6 pt-6 border-t border-dashed border-gray-200">
                   <div className="flex items-center gap-2 mb-3">
                    <span className="text-xl">🌱</span>
                    <span className="tips-title mb-0">Recommended Focus</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {result.recommended_crop_focus.map(crop => (
                      <span key={crop} className="badge badge-brand">{crop}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="empty-state-illust">
              <div className="illust-icon">🧪</div>
              <p className="muted-copy">{t("soil.empty")}</p>
            </div>
          )}
        </article>
      </section>
    </div>
  );
}

"use client";

import { useState } from "react";

import { ActiveFarmerBanner } from "@/components/farmers/ActiveFarmerBanner";
import { ErrorNotice } from "@/components/ui/AsyncState";
import { PageHeader } from "@/components/ui/PageHeader";
import { useFarmerSession } from "@/contexts/FarmerSessionContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { predictCrop } from "@/lib/api";
import { DEFAULT_SOIL_PAYLOAD, FEATURE_INPUTS } from "@/lib/constants";
import { toUserMessage } from "@/lib/errors";
import type { PredictionResponse, SoilPayload } from "@/lib/types";

const CROP_ICONS: Record<string, string> = {
  wheat: "🌾",
  rice: "🍚",
  maize: "🌽",
  chickpea: "🥘",
  kidneybeans: "🫘",
  pigeonpeas: "🍲",
  mothbeans: "🍛",
  mungbean: "🥣",
  blackgram: "🥣",
  lentil: "🥣",
  pomegranate: "🍎",
  banana: "🍌",
  mango: "🥭",
  grapes: "🍇",
  watermelon: "🍉",
  muskmelon: "🍈",
  apple: "🍎",
  orange: "🍊",
  papaya: "🥭",
  coconut: "🥥",
  cotton: "☁️",
  jute: "🧵",
  coffee: "☕"
};

export function CropIntelligencePage() {
  const { t, language } = useLanguage();
  const { activeFarmer } = useFarmerSession();
  const [input, setInput] = useState<SoilPayload>(DEFAULT_SOIL_PAYLOAD);
  const [result, setResult] = useState<PredictionResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
    setBusy(true);
    setError(null);
    try {
      const response = await predictCrop({
        ...input,
        language,
        farmer_id: activeFarmer?.farmer_id,
        mobile: activeFarmer?.mobile
      });
      setResult(response);
    } catch (caught: unknown) {
      console.error("Prediction failed:", caught);
      setError(toUserMessage(caught, t("feedback.error")));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-container">
      <PageHeader
        eyebrow={t("nav.crop")}
        title={t("crop.title")}
        description={t("crop.subtitle")}
      />
      <ActiveFarmerBanner />

      <section className="dashboard-grid mt-4">
        <article className="surface-card">
          <h3>{t("crop.inputTitle")}</h3>
          <div className="form-grid">
            {FEATURE_INPUTS.map((field) => (
              <label key={field.key} className="field">
                <span>
                  {t(field.labelKey)} ({field.unit})
                </span>
                <input
                  type="number"
                  min={field.min}
                  max={field.max}
                  step={field.step}
                  value={input[field.key]}
                  onChange={(event) =>
                    setInput((prev) => ({
                      ...prev,
                      [field.key]: Number(event.target.value)
                    }))
                  }
                />
              </label>
            ))}
          </div>
          {error && <ErrorNotice message={error} onDismiss={() => setError(null)} />}

          <div className="flex justify-end gap-3 mt-8">
            <button 
              type="button" 
              className="ghost-btn" 
              onClick={() => {
                setInput(DEFAULT_SOIL_PAYLOAD);
                setResult(null);
                setError(null);
              }}
            >
              {t("common.reset")}
            </button>
            <button type="button" className="primary-btn" onClick={handleRun} disabled={busy}>
              {busy ? t("common.loading") : t("common.predict")}
            </button>
          </div>
        </article>

        <article className="surface-card">
          <div className="flex items-center justify-between mb-6">
            <h3 className="mb-0">{t("crop.outputTitle")}</h3>
            {result && (
              <div className="text-xs font-bold text-muted bg-subtle px-3 py-1 rounded-full uppercase tracking-widest">
                {result.recommendations.length} {t("common.results")}
              </div>
            )}
          </div>
          
          {result ? (
            <div className="result-layout animate-in fade-in duration-500">
              <div className="recommendation-grid">
                {result.recommendations.map((item, idx) => {
                  const prob = item.probability * 100;
                  const confidenceClass = prob >= 80 ? 'high' : prob >= 60 ? 'medium' : 'low';
                  const cropKey = item.crop.toLowerCase();
                  const icon = CROP_ICONS[cropKey] || "🌱";

                  return (
                    <div 
                      key={item.crop} 
                      className={`recommendation-card ${idx === 0 ? 'top-choice' : ''}`}
                      style={{ animationDelay: `${idx * 100}ms` }}
                    >
                      {idx === 0 && (
                        <div className="absolute top-0 right-0 p-3">
                          <span className="badge badge-brand shadow-sm">{t("common.bestMatch")}</span>
                        </div>
                      )}
                      
                      <div className="recommendation-header">
                        <div className="crop-icon-wrapper">
                          {icon}
                        </div>
                        <div className="recommendation-title-group">
                          <h4 className="crop-name">{item.display_crop}</h4>
                          <div className={`confidence-badge ${confidenceClass}`}>
                            {Math.round(prob)}% {t("models.accuracy")}
                          </div>
                        </div>
                      </div>

                      <div className="tips-section mt-4">
                        <div className="flex items-center gap-2 mb-2">
                          <span className="text-xl">💡</span>
                          <span className="tips-title mb-0">{t("common.agronomyTip")}</span>
                        </div>
                        <p className="tips-content italic">&ldquo;{item.agronomy_tip}&rdquo;</p>
                      </div>

                      <div className="actions-panel mt-4 pt-4 border-t border-dashed border-gray-200">
                        <div className="flex items-center gap-2 mb-3">
                          <span className="text-xl">📋</span>
                          <span className="tips-title mb-0">{t("common.actions")}</span>
                        </div>
                        <div className="actions-list">
                          {result.field_actions.slice(0, 3).map((action) => (
                            <div key={action} className="action-item">
                              <span className="action-check">✓</span>
                              <span>{action}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="empty-state-illust">
              <div className="illust-icon">🌾</div>
              <p className="muted-copy">{t("crop.empty")}</p>
            </div>
          )}
        </article>
      </section>
    </div>
  );
}

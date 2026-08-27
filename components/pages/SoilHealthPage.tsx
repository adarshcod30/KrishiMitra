"use client";

import { useState } from "react";

import { ActiveFarmerBanner } from "@/components/farmers/ActiveFarmerBanner";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/ui/AsyncState";
import { Icon } from "@/components/ui/Icons";
import { useFarmerSession } from "@/contexts/FarmerSessionContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { analyzeSoil } from "@/lib/api";
import { FEATURE_INPUTS } from "@/lib/constants";
import { toUserMessage } from "@/lib/errors";
import type { TranslationKey } from "@/lib/i18n";
import type { SoilAnalysisResponse } from "@/lib/types";

/**
 * Numeric ranges come from the shared feature definitions so the help line
 * under each soil-test field always matches what the API accepts.
 */
const RANGES = new Map(FEATURE_INPUTS.map((field) => [field.key as string, field]));

type NumericKey = "N" | "P" | "K" | "ph";

const NUMERIC_FIELDS: ReadonlyArray<{ key: NumericKey; labelKey: TranslationKey }> = [
  { key: "N", labelKey: "common.nitrogen" },
  { key: "P", labelKey: "common.phosphorus" },
  { key: "K", labelKey: "common.potassium" },
  { key: "ph", labelKey: "common.soilPh" }
];

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
      // Without this the rejection is unhandled and the busy state just stops.
      setError(toUserMessage(caught, t("feedback.error")));
    } finally {
      setBusy(false);
    }
  }

  function renderNumberField(key: NumericKey, labelKey: TranslationKey) {
    const range = RANGES.get(key);
    const id = `soil-${key}`;
    return (
      <div key={key} className="field">
        <label className="field-label" htmlFor={id}>
          {t(labelKey)}
        </label>
        <input
          id={id}
          className="field-input"
          type="number"
          inputMode="decimal"
          min={range?.min}
          max={range?.max}
          step={range?.step}
          value={input[key]}
          onChange={(event) =>
            setInput((prev) => ({ ...prev, [key]: Number(event.target.value) }))
          }
        />
        {range ? (
          <p className="field-help">
            {range.min} &ndash; {range.max} {range.unit}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">{t("nav.soil")}</h1>
        <p className="page-subtitle">{t("soil.subtitle")}</p>
      </div>
      <ActiveFarmerBanner />

      <section className="grid-2-cols mt-4">
        <article className="surface-card">
          <h3 className="section-title">{t("soil.inputTitle")}</h3>

          <div className="grid-2-cols">
            {NUMERIC_FIELDS.map((field) => renderNumberField(field.key, field.labelKey))}
          </div>

          <div className="grid-2-cols">
            <div className="field">
              <label className="field-label" htmlFor="soil-type">
                {t("farmer.soilType")}
              </label>
              <input
                id="soil-type"
                className="field-input"
                value={input.soil_type}
                onChange={(event) =>
                  setInput((prev) => ({ ...prev, soil_type: event.target.value }))
                }
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="soil-crop">
                {t("farmer.crop")}
              </label>
              <input
                id="soil-crop"
                className="field-input"
                value={input.crop}
                onChange={(event) => setInput((prev) => ({ ...prev, crop: event.target.value }))}
              />
            </div>
          </div>

          {error && <ErrorNotice message={error} onDismiss={() => setError(null)} />}

          <button type="button" className="btn-primary" onClick={handleAnalyze} disabled={busy}>
            {busy ? t("common.loading") : t("common.predict")}
          </button>
        </article>

        <article className="surface-card">
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "0.75rem",
              marginBottom: "1rem"
            }}
          >
            <h3 className="section-title mb-0">{t("soil.outputTitle")}</h3>
            {result && <span className="badge badge-success">{t("nav.soil")}</span>}
          </div>

          {busy && !result ? (
            <LoadingState icon="soil" />
          ) : result ? (
            <div>
              {/* The answer the farmer came for: soil status, big. */}
              <div className="result-card result-card-success">
                <span className="badge badge-success">{t("common.status")}</span>
                <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginTop: "0.75rem" }}>
                  <div className="crop-icon-wrapper">
                    <Icon name="soil" size={30} />
                  </div>
                  <div style={{ fontSize: "2.1rem", fontWeight: 700, lineHeight: 1.2, color: "var(--ink)" }}>
                    {result.soil_health_status}
                  </div>
                </div>

                {result.nutrient_alerts.length > 0 && (
                  <div className="tips-section" style={{ marginTop: "1rem" }}>
                    <div className="tips-title">{t("common.nutrientAlerts")}</div>
                    <div className="premium-list">
                      {result.nutrient_alerts.map((alert) => (
                        <div key={alert} className="premium-list-item">
                          <span className="icon" aria-hidden="true">
                            <Icon name="alert" size={18} />
                          </span>
                          <span className="text">{alert}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* The concrete next steps. */}
                <div style={{ marginTop: "1rem" }}>
                  <div className="tips-title">{t("common.actions")}</div>
                  <div className="actions-list">
                    {result.soil_actions.map((action) => (
                      <div key={action} className="action-item">
                        <span className="action-check" aria-hidden="true">
                          <Icon name="check" size={18} />
                        </span>
                        <span>{action}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {result.recommended_crop_focus && result.recommended_crop_focus.length > 0 && (
                <div style={{ marginTop: "1rem" }}>
                  {/* The API currently fills this field with nutrient-management
                      practices ("Split nitrogen application"), not crop names, so
                      labelling it "What to Grow" (nav.crop) misled farmers. A
                      neutral heading stays correct if the API later returns crops. */}
                  <div className="tips-title">Recommended focus</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.4rem" }}>
                    {result.recommended_crop_focus.map((crop) => (
                      <span key={crop} className="badge badge-success">
                        {crop}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <EmptyState icon="soil" message={t("soil.empty")} />
          )}
        </article>
      </section>
    </div>
  );
}

"use client";

import { useState } from "react";

import { ActiveFarmerBanner } from "@/components/farmers/ActiveFarmerBanner";
import { EmptyState, ErrorNotice } from "@/components/ui/AsyncState";
import { Icon } from "@/components/ui/Icons";
import { useFarmerSession } from "@/contexts/FarmerSessionContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { predictCrop } from "@/lib/api";
import { DEFAULT_SOIL_PAYLOAD, FEATURE_INPUTS } from "@/lib/constants";
import { toUserMessage } from "@/lib/errors";
import type { PredictionResponse, SoilPayload } from "@/lib/types";

// The form is grouped the way a farmer meets these numbers: the first four
// come from a soil test report, the rest describe the local weather.
const SOIL_KEYS: readonly string[] = ["N", "P", "K", "ph"];
const SOIL_FIELDS = FEATURE_INPUTS.filter((field) => SOIL_KEYS.includes(field.key));
const WEATHER_FIELDS = FEATURE_INPUTS.filter((field) => !SOIL_KEYS.includes(field.key));

const SEASONS = ["Kharif", "Rabi", "Summer", "Whole Year"] as const;

/** Default to the season India is actually in: Kharif Jun-Oct, Rabi Nov-Mar. */
function currentSeason(): string {
  const month = new Date().getMonth() + 1;
  if (month >= 6 && month <= 10) return "Kharif";
  if (month >= 11 || month <= 3) return "Rabi";
  return "Summer";
}

export function CropIntelligencePage() {
  const { t, language } = useLanguage();
  const { activeFarmer } = useFarmerSession();
  const [input, setInput] = useState<SoilPayload>(DEFAULT_SOIL_PAYLOAD);
  const [result, setResult] = useState<PredictionResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Which sowing season the farmer is planning for. Drives the district
  // returns lookup; the soil model itself is season-agnostic.
  const [season, setSeason] = useState<string>(currentSeason());

  async function handleRun() {
    setBusy(true);
    setError(null);
    try {
      // The farmer's district unlocks the government district returns, so each
      // recommendation can say whether the crop is actually proven locally.
      const response = await predictCrop({
        ...input,
        language,
        farmer_id: activeFarmer?.farmer_id,
        mobile: activeFarmer?.mobile,
        state: activeFarmer?.state,
        district: activeFarmer?.district,
        season
      });
      setResult(response);
    } catch (caught: unknown) {
      console.error("Prediction failed:", caught);
      setError(toUserMessage(caught, t("feedback.error")));
    } finally {
      setBusy(false);
    }
  }

  function renderField(field: (typeof FEATURE_INPUTS)[number]) {
    const id = `crop-${field.key}`;
    return (
      <div key={field.key} className="field">
        <label className="field-label" htmlFor={id}>
          {t(field.labelKey)}
        </label>
        <input
          id={id}
          className="field-input"
          type="number"
          inputMode="decimal"
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
        <p className="field-help">
          {field.min} &ndash; {field.max} {field.unit}
        </p>
      </div>
    );
  }

  // The model always returns 3 rows and pads with probability-0 crops, so a
  // farmer could see "Best match: 0%" on a crop the model does NOT recommend.
  // Only rows with a real, non-zero probability are worth showing.
  const recommendations = (result?.recommendations ?? []).filter(
    (item) => item.probability >= 0.01
  );
  const topPick = recommendations[0];
  const alternates = recommendations.slice(1);

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">{t("nav.crop")}</h1>
        <p className="page-subtitle">{t("welcome.benefit1")}</p>
      </div>
      <ActiveFarmerBanner />

      <section className="grid-2-cols mt-4">
        <article className="surface-card">
          <h3 className="section-title">{t("crop.inputTitle")}</h3>

          <span className="page-eyebrow">{t("nav.soil")}</span>
          <div className="grid-2-cols" style={{ marginTop: "0.5rem" }}>
            {SOIL_FIELDS.map(renderField)}
          </div>

          <span className="page-eyebrow" style={{ marginTop: "0.75rem" }}>
            {t("nav.weather")}
          </span>
          <div className="grid-2-cols" style={{ marginTop: "0.5rem" }}>
            {WEATHER_FIELDS.map(renderField)}
          </div>

          <span className="page-eyebrow" style={{ marginTop: "0.75rem" }}>
            Sowing season
          </span>
          <div style={{ marginTop: "0.5rem" }}>
            <label className="field-label" htmlFor="season-select">
              Which season are you planting for?
            </label>
            <select
              id="season-select"
              className="field-select"
              value={season}
              onChange={(event) => setSeason(event.target.value)}
            >
              {SEASONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            <p className="field-help">
              Used to look up what your district actually grows in this season.
            </p>
          </div>

          {error && <ErrorNotice message={error} onDismiss={() => setError(null)} />}

          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", marginTop: "0.75rem" }}>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                setInput(DEFAULT_SOIL_PAYLOAD);
                setResult(null);
                setError(null);
              }}
            >
              {t("common.reset")}
            </button>
            <button type="button" className="btn-primary" onClick={handleRun} disabled={busy}>
              {busy ? t("common.loading") : t("common.predict")}
            </button>
          </div>
        </article>

        <article className="surface-card">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem", marginBottom: "1rem" }}>
            <h3 className="section-title mb-0">{t("crop.outputTitle")}</h3>
            {result && (
              <span className="badge badge-success">
                {recommendations.length} {t("common.results")}
              </span>
            )}
          </div>

          {result && topPick ? (
            <div>
              <div className="result-card result-card-success">
                <span className="badge badge-success">{t("common.bestMatch")}</span>
                <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginTop: "0.75rem" }}>
                  <div className="crop-icon-wrapper">
                    <Icon name="plant" size={30} />
                  </div>
                  <div>
                    <div style={{ fontSize: "2.1rem", fontWeight: 700, lineHeight: 1.2, color: "var(--ink)" }}>
                      {topPick.display_crop}
                    </div>
                    <div className={`confidence-badge ${topPick.confidence}`}>
                      {t("common.bestMatch")}: {Math.round(topPick.probability * 100)}%
                    </div>
                  </div>
                </div>

                <div className="tips-section" style={{ marginTop: "1rem" }}>
                  <div className="tips-title">{t("common.agronomyTip")}</div>
                  <p className="tips-content">{topPick.agronomy_tip}</p>
                </div>

                {topPick.local && (
                  <div className="tips-section" style={{ marginTop: "1rem" }}>
                    <div className="tips-title">{t("label.inYourDistrict")}</div>
                    <p className="tips-content">
                      Rank {topPick.local.rank_in_district} of the crops grown here in{" "}
                      {topPick.local.season}
                      {topPick.local.area_ha
                        ? `, on about ${Math.round(topPick.local.area_ha).toLocaleString()} hectares`
                        : ""}
                      {topPick.local.median_yield
                        ? `, yielding around ${topPick.local.median_yield} ${topPick.local.yield_unit}`
                        : ""}
                      .
                    </p>
                  </div>
                )}

                <div style={{ marginTop: "1rem" }}>
                  <div className="tips-title">{t("common.actions")}</div>
                  <div className="actions-list">
                    {result.field_actions.slice(0, 3).map((action) => (
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

              {alternates.length > 0 && (
                <div style={{ marginTop: "1rem" }}>
                  {alternates.map((item) => (
                    <div key={item.crop} className="list-row">
                      <span style={{ fontWeight: 600 }}>{item.display_crop}</span>
                      <span className="badge">
                        {t("common.bestMatch")}: {Math.round(item.probability * 100)}%
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {result.local_crops?.matched && result.local_crops.crops.length > 0 && (
                <div className="surface-card" style={{ marginTop: "1.25rem" }}>
                  <h3 className="section-title">
                    Grown well in {activeFarmer?.district}
                  </h3>
                  <p className="field-help" style={{ marginTop: "-0.25rem" }}>
                    From five years of government district records
                    {result.local_crops.season_used
                      ? ` for ${result.local_crops.season_used}`
                      : " across all seasons"}
                    . The soil match above and this list are strongest where they agree.
                  </p>
                  <div style={{ marginTop: "0.75rem" }}>
                    {result.local_crops.crops.map((item) => (
                      <div key={`${item.crop}-${item.season}`} className="list-row">
                        <div>
                          <div style={{ fontWeight: 600 }}>{item.crop}</div>
                          <div className="field-help" style={{ margin: 0 }}>
                            {item.why}
                          </div>
                        </div>
                        {item.median_yield ? (
                          <span className="badge badge-success">
                            {item.median_yield} {item.yield_unit}
                          </span>
                        ) : null}
                      </div>
                    ))}
                  </div>
                  <p className="field-help" style={{ marginTop: "0.75rem" }}>
                    Source: {result.local_crops.source}
                  </p>
                </div>
              )}
            </div>
          ) : (
            <EmptyState icon="plant" message={t("crop.empty")} />
          )}
        </article>
      </section>
    </div>
  );
}

"use client";

import { useState } from "react";

import { ActiveFarmerBanner } from "@/components/farmers/ActiveFarmerBanner";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/ui/AsyncState";
import { Icon } from "@/components/ui/Icons";
import { useFarmerSession } from "@/contexts/FarmerSessionContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { getIrrigationSchedule } from "@/lib/api";
import { DEFAULT_IRRIGATION_PAYLOAD, FEATURE_INPUTS } from "@/lib/constants";
import { toUserMessage } from "@/lib/errors";
import type { IrrigationResponse } from "@/lib/types";

const RAINFALL_RANGE = FEATURE_INPUTS.find((field) => field.key === "rainfall");

export function IrrigationPlannerPage() {
  const { t, language } = useLanguage();
  const { activeFarmer } = useFarmerSession();
  const [input, setInput] = useState(DEFAULT_IRRIGATION_PAYLOAD);
  const [result, setResult] = useState<IrrigationResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate() {
    setBusy(true);
    setError(null);
    try {
      const response = await getIrrigationSchedule({
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

  const nextEvent = result?.events[0];
  const laterEvents = result?.events.slice(1, 5) ?? [];

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">{t("nav.irrigation")}</h1>
        <p className="page-subtitle">{t("irrigation.subtitle")}</p>
      </div>
      <ActiveFarmerBanner />

      <section className="grid-2-cols mt-4">
        <article className="surface-card">
          <h3 className="section-title">{t("irrigation.inputTitle")}</h3>

          <div className="grid-2-cols">
            <div className="field">
              <label className="field-label" htmlFor="irrigation-name">
                {t("farmer.name")}
              </label>
              <input
                id="irrigation-name"
                className="field-input"
                value={input.farmer_name}
                onChange={(event) =>
                  setInput((prev) => ({ ...prev, farmer_name: event.target.value }))
                }
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="irrigation-location">
                {t("farmer.village")}
              </label>
              <input
                id="irrigation-location"
                className="field-input"
                value={input.location}
                onChange={(event) =>
                  setInput((prev) => ({ ...prev, location: event.target.value }))
                }
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="irrigation-crop">
                {t("farmer.crop")}
              </label>
              <input
                id="irrigation-crop"
                className="field-input"
                value={input.crop}
                onChange={(event) => setInput((prev) => ({ ...prev, crop: event.target.value }))}
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="irrigation-size">
                {t("farmer.farmSize")}
              </label>
              <input
                id="irrigation-size"
                className="field-input"
                type="number"
                inputMode="decimal"
                min={0}
                value={input.land_size}
                onChange={(event) =>
                  setInput((prev) => ({ ...prev, land_size: Number(event.target.value) }))
                }
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="irrigation-soil">
                {t("farmer.soilType")}
              </label>
              <input
                id="irrigation-soil"
                className="field-input"
                value={input.soil_type}
                onChange={(event) =>
                  setInput((prev) => ({ ...prev, soil_type: event.target.value }))
                }
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="irrigation-rainfall">
                {t("common.rainfall")}
              </label>
              <input
                id="irrigation-rainfall"
                className="field-input"
                type="number"
                inputMode="decimal"
                min={RAINFALL_RANGE?.min}
                max={RAINFALL_RANGE?.max}
                step={RAINFALL_RANGE?.step}
                value={input.rainfall}
                onChange={(event) =>
                  setInput((prev) => ({ ...prev, rainfall: Number(event.target.value) }))
                }
              />
              {RAINFALL_RANGE ? (
                <p className="field-help">
                  {RAINFALL_RANGE.min} &ndash; {RAINFALL_RANGE.max} {RAINFALL_RANGE.unit}
                </p>
              ) : null}
            </div>
          </div>

          {error && <ErrorNotice message={error} onDismiss={() => setError(null)} />}

          <button type="button" className="btn-primary" onClick={handleGenerate} disabled={busy}>
            {busy ? t("common.loading") : t("common.generate")}
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
            <h3 className="section-title mb-0">{t("irrigation.outputTitle")}</h3>
            {result && <span className="badge badge-info">{result.crop}</span>}
          </div>

          {busy && !result ? (
            <LoadingState icon="water" />
          ) : result && nextEvent ? (
            <div>
              {/* The answer the farmer came for: the next watering, big. */}
              <div className="result-card result-card-success">
                <span className="badge badge-success">{t("nav.irrigation")}</span>
                <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginTop: "0.75rem" }}>
                  <div className="crop-icon-wrapper">
                    <Icon name="water" size={30} />
                  </div>
                  <div>
                    <div style={{ fontSize: "1.9rem", fontWeight: 700, lineHeight: 1.25, color: "var(--ink)" }}>
                      {nextEvent.date}, {nextEvent.time}
                    </div>
                    <div className="stat-item" style={{ marginTop: "0.35rem" }}>
                      <span className="stat-label">{t("common.water")}</span>
                      <span className="stat-value">{nextEvent.water_mm} mm</span>
                    </div>
                  </div>
                </div>
                {nextEvent.message ? (
                  <div className="tips-section" style={{ marginTop: "1rem" }}>
                    <p className="tips-content">{nextEvent.message}</p>
                  </div>
                ) : null}
              </div>

              {laterEvents.length > 0 && (
                <div style={{ marginTop: "1rem" }}>
                  <div className="tips-title">{t("irrigation.outputTitle")}</div>
                  {laterEvents.map((event, idx) => (
                    <div key={`${event.date}-${event.time}-${idx}`} className="list-row">
                      <span style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                        <span style={{ display: "flex", color: "var(--brand-dark)" }} aria-hidden="true">
                          <Icon name="calendar" size={20} />
                        </span>
                        <span>
                          <span style={{ display: "block", fontWeight: 600 }}>{event.date}</span>
                          <span style={{ display: "block", fontSize: "0.9rem", color: "var(--ink-secondary)" }}>
                            {event.time}
                          </span>
                        </span>
                      </span>
                      <span className="badge badge-info">{event.water_mm} mm</span>
                    </div>
                  ))}
                </div>
              )}

              {result.notes.length > 0 && (
                <div style={{ marginTop: "1rem" }}>
                  <div className="tips-title">{t("common.agronomyTip")}</div>
                  <div className="actions-list">
                    {result.notes.map((note) => (
                      <div key={note} className="action-item">
                        <span className="action-check" aria-hidden="true">
                          <Icon name="check" size={18} />
                        </span>
                        <span>{note}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <EmptyState icon="water" message={t("irrigation.empty")} />
          )}
        </article>
      </section>
    </div>
  );
}

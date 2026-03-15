"use client";

import { useState } from "react";

import { ActiveFarmerBanner } from "@/components/farmers/ActiveFarmerBanner";
import { PageHeader } from "@/components/ui/PageHeader";
import { useFarmerSession } from "@/contexts/FarmerSessionContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { getIrrigationSchedule } from "@/lib/api";
import { DEFAULT_IRRIGATION_PAYLOAD } from "@/lib/constants";
import type { IrrigationResponse } from "@/lib/types";

export function IrrigationPlannerPage() {
  const { t, language } = useLanguage();
  const { activeFarmer } = useFarmerSession();
  const [input, setInput] = useState(DEFAULT_IRRIGATION_PAYLOAD);
  const [result, setResult] = useState<IrrigationResponse | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleGenerate() {
    setBusy(true);
    try {
      const response = await getIrrigationSchedule({
        ...input,
        language,
        farmer_id: activeFarmer?.farmer_id,
        mobile: activeFarmer?.mobile
      });
      setResult(response);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-container">
      <PageHeader
        eyebrow={t("nav.irrigation")}
        title={t("irrigation.title")}
        description={t("irrigation.subtitle")}
      />
      <ActiveFarmerBanner />

      <section className="dashboard-grid mt-4">
        <article className="surface-card">
          <h3>{t("irrigation.inputTitle")}</h3>
          <div className="form-grid">
            <label className="field">
              <span>{t("farmer.name")}</span>
              <input
                value={input.farmer_name}
                onChange={(event) =>
                  setInput((prev) => ({ ...prev, farmer_name: event.target.value }))
                }
              />
            </label>
            <label className="field">
              <span>{t("farmer.village")}</span>
              <input
                value={input.location}
                onChange={(event) =>
                  setInput((prev) => ({ ...prev, location: event.target.value }))
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
            <label className="field">
              <span>{t("farmer.farmSize")}</span>
              <input
                type="number"
                value={input.land_size}
                onChange={(event) =>
                  setInput((prev) => ({ ...prev, land_size: Number(event.target.value) }))
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
              <span>{t("common.rainfall")}</span>
              <input
                type="number"
                value={input.rainfall}
                onChange={(event) =>
                  setInput((prev) => ({ ...prev, rainfall: Number(event.target.value) }))
                }
              />
            </label>
          </div>
          <button type="button" className="primary-btn" onClick={handleGenerate}>
            {busy ? t("common.loading") : t("common.generate")}
          </button>
        </article>

        <article className="surface-card">
          <div className="flex items-center justify-between mb-6">
            <h3 className="mb-0">{t("irrigation.outputTitle")}</h3>
            {result && (
              <div className="status-badge info">
                💧 {t("nav.irrigation")}
              </div>
            )}
          </div>

          {result ? (
            <div className="recommendation-card top-choice animate-in slide-in-from-bottom-4 duration-500">
              <div className="recommendation-header">
                <div className="crop-icon-wrapper">💧</div>
                <div className="recommendation-title-group">
                  <h4 className="crop-name">{result.crop}</h4>
                  <p className="text-sm text-ink-secondary mt-1">{t("irrigation.subtitle")}</p>
                </div>
              </div>

              <div className="mt-6">
                <div className="flex items-center gap-2 mb-4">
                  <span className="text-xl">📅</span>
                  <span className="tips-title mb-0">Upcoming Schedule</span>
                </div>
                <div className="premium-list">
                  {result.events.slice(0, 5).map((event, idx) => (
                    <div key={idx} className="premium-list-item">
                      <div className="flex items-center justify-between w-full">
                        <div className="flex items-center gap-3">
                          <span className="icon">⌚</span>
                          <div className="flex flex-col">
                            <span className="text-sm font-bold">{event.time}</span>
                            <span className="text-xs text-muted">{event.date}</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                           <span className="badge badge-accent">{event.water_mm} mm</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="tips-section mt-6">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xl">💡</span>
                  <span className="tips-title mb-0">{t("common.agronomyTip")}</span>
                </div>
                <div className="premium-list">
                  {result.notes.map((note, idx) => (
                    <div key={idx} className="premium-list-item">
                      <span className="icon">✓</span>
                      <span className="text italic">{note}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="empty-state-illust">
              <div className="illust-icon">💧</div>
              <p className="muted-copy">{t("irrigation.empty")}</p>
            </div>
          )}
        </article>
      </section>
    </div>
  );
}

"use client";

import { useState } from "react";

import { ActiveFarmerBanner } from "@/components/farmers/ActiveFarmerBanner";
import { ErrorNotice, LoadingState } from "@/components/ui/AsyncState";
import { PageHeader } from "@/components/ui/PageHeader";
import { useFarmerSession } from "@/contexts/FarmerSessionContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { diagnoseDisease, uploadAsset } from "@/lib/api";
import { toUserMessage } from "@/lib/errors";
import type { DiseaseResponse, UploadAsset } from "@/lib/types";

export function PestDetectionPage() {
  const { t, language } = useLanguage();
  const { activeFarmer } = useFarmerSession();
  const [crop, setCrop] = useState("rice");
  const [symptoms, setSymptoms] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [asset, setAsset] = useState<UploadAsset | null>(null);
  const [result, setResult] = useState<DiseaseResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleUpload() {
    if (!activeFarmer) {
      setError(t("feedback.selectFarmerFirst"));
      return;
    }
    if (!file) {
      setError(t("feedback.selectFileFirst"));
      return;
    }

    setUploading(true);
    setError(null);
    try {
      const response = await uploadAsset({
        farmer_id: activeFarmer.farmer_id,
        mobile: activeFarmer.mobile,
        module: "pest",
        file
      });
      setAsset(response.asset);
    } catch (caught) {
      // Without this the rejection is unhandled and the spinner just stops.
      setError(toUserMessage(caught, t("feedback.uploadFailed")));
    } finally {
      setUploading(false);
    }
  }

  async function handleAnalyze() {
    setBusy(true);
    setError(null);
    try {
      const response = await diagnoseDisease({
        crop,
        symptoms,
        image_hint: asset?.url,
        farmer_id: activeFarmer?.farmer_id,
        mobile: activeFarmer?.mobile,
        language
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
        eyebrow={t("nav.pest")}
        title={t("pest.title")}
        description={t("pest.subtitle")}
      />
      <ActiveFarmerBanner />

      <section className="dashboard-grid mt-4">
        <article className="surface-card">
          <h3>{t("pest.inputTitle")}</h3>
          <div className="form-grid">
            <label className="field">
              <span>{t("farmer.crop")}</span>
              <input value={crop} onChange={(event) => setCrop(event.target.value)} />
            </label>
            <label className="field field-full">
              <span>{t("common.symptoms")}</span>
              <textarea
                rows={6}
                value={symptoms}
                onChange={(event) => setSymptoms(event.target.value)}
              />
            </label>
            <label className="field field-full">
              <span>{t("common.evidence")}</span>
              <input
                type="file"
                accept="image/*,.pdf"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
            </label>
          </div>
          {error && <ErrorNotice message={error} onDismiss={() => setError(null)} />}
          <div className="action-row">
            <button type="button" className="ghost-btn" onClick={handleUpload} disabled={uploading}>
              {uploading ? t("common.loading") : t("common.upload")}
            </button>
            <button type="button" className="primary-btn" onClick={handleAnalyze} disabled={busy}>
              {busy ? t("common.loading") : t("common.predict")}
            </button>
          </div>
          {asset ? <p className="muted-copy">{asset.filename}</p> : null}
        </article>

        <article className="surface-card">
          <div className="flex items-center justify-between mb-6">
            <h3 className="mb-0">{t("pest.outputTitle")}</h3>
            {result && (
              <div className={`status-badge ${result.severity === 'high' ? 'danger' : result.severity === 'moderate' ? 'warning' : 'success'}`}>
                🐛 {result.severity.toUpperCase()}
              </div>
            )}
          </div>

          {busy && !result ? (
            <LoadingState icon="🐛" />
          ) : result ? (
            <div className="recommendation-card top-choice animate-in slide-in-from-bottom-4 duration-500">
              <div className="recommendation-header">
                <div className="crop-icon-wrapper">🐛</div>
                <div className="recommendation-title-group">
                  <h4 className="crop-name">{result.disease}</h4>
                  <div className="confidence-badge high mt-1">
                    {Math.round(result.confidence * 100)}% {t("models.accuracy")}
                  </div>
                </div>
              </div>

              <div className="tips-section mt-6">
                 <div className="flex items-center gap-2 mb-2">
                  <span className="text-xl">🩺</span>
                  <span className="tips-title mb-0">Diagnosis & Advice</span>
                </div>
                <p className="tips-content">{result.advice}</p>
              </div>

              <div className="mt-6">
                <div className="flex items-center gap-2 mb-4">
                  <span className="text-xl">🛡️</span>
                  <span className="tips-title mb-0">Preventive Actions</span>
                </div>
                <div className="premium-list">
                  {result.preventive_actions.map((action, idx) => (
                    <div key={idx} className="premium-list-item">
                      <span className="icon">✓</span>
                      <span className="text">{action}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="empty-state-illust">
              <div className="illust-icon">🐛</div>
              <p className="muted-copy">{t("pest.empty")}</p>
            </div>
          )}
        </article>
      </section>
    </div>
  );
}

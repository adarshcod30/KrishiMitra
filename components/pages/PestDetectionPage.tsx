"use client";

import { useState } from "react";

import { ActiveFarmerBanner } from "@/components/farmers/ActiveFarmerBanner";
import { EmptyState, ErrorNotice, LoadingState } from "@/components/ui/AsyncState";
import { Icon } from "@/components/ui/Icons";
import { useFarmerSession } from "@/contexts/FarmerSessionContext";
import { useLanguage } from "@/contexts/LanguageContext";
import { diagnoseDisease, uploadAsset } from "@/lib/api";
import { toUserMessage } from "@/lib/errors";
import type { DiseaseResponse, UploadAsset } from "@/lib/types";

const iconTitleStyle = {
  display: "flex",
  alignItems: "center",
  gap: "0.5rem",
} as const;

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

  const severityCardClass =
    result?.severity === "high"
      ? "result-card-danger"
      : result?.severity === "moderate"
        ? "result-card-warning"
        : "result-card-success";
  const severityBadgeClass =
    result?.severity === "high"
      ? "badge-danger"
      : result?.severity === "moderate"
        ? "badge-warning"
        : "badge-success";
  const severityLabel =
    result?.severity === "high"
      ? "Serious - act now"
      : result?.severity === "moderate"
        ? "Needs attention"
        : "Mild";

  // The raw model confidence is often low (the text classifier is small), and
  // showing "Accuracy: 14%" destroys trust while explaining nothing. Translate
  // it into plain words, and be honest when the model is essentially guessing.
  const isUncertain = (result?.confidence ?? 0) < 0.35;
  const matchLabel =
    result == null
      ? ""
      : result.confidence >= 0.6
        ? "Strong match"
        : result.confidence >= 0.35
          ? "Possible match"
          : "Best guess - not confirmed";

  return (
    <div className="page-container">
      <header className="page-header">
        <h2 className="page-title">{t("nav.pest")}</h2>
        <p className="page-subtitle">{t("pest.subtitle")}</p>
      </header>
      <ActiveFarmerBanner />

      <section className="grid-2-cols mt-4">
        <article className="surface-card">
          <h3 className="section-title" style={iconTitleStyle}>
            <Icon name="pest" size={22} />
            {t("pest.inputTitle")}
          </h3>
          <div className="form-stack">
            <div>
              <label className="field-label" htmlFor="pest-crop">
                {t("farmer.crop")}
              </label>
              <input
                id="pest-crop"
                className="field-input"
                value={crop}
                onChange={(event) => setCrop(event.target.value)}
              />
              <p className="field-help">Which crop has the problem, e.g. rice.</p>
            </div>
            <div>
              <label className="field-label" htmlFor="pest-symptoms">
                {t("common.symptoms")}
              </label>
              <textarea
                id="pest-symptoms"
                className="field-input"
                rows={5}
                value={symptoms}
                onChange={(event) => setSymptoms(event.target.value)}
              />
              <p className="field-help">Describe what you see - yellow leaves, spots, insects...</p>
            </div>
            <div>
              <label className="field-label" htmlFor="pest-photo">
                {t("common.evidence")}
              </label>
              <input
                id="pest-photo"
                className="field-input"
                type="file"
                accept="image/*,.pdf"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
              <p className="field-help">A clear photo of the sick leaf or plant helps.</p>
            </div>
          </div>
          {error && <ErrorNotice message={error} onDismiss={() => setError(null)} />}
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "0.75rem",
              marginTop: "1rem",
            }}
          >
            <button type="button" className="btn-secondary" onClick={handleUpload} disabled={uploading}>
              <Icon name="upload" size={20} />
              {uploading ? t("common.loading") : t("common.upload")}
            </button>
            <button type="button" className="btn-primary" onClick={handleAnalyze} disabled={busy}>
              {busy ? t("common.loading") : t("common.predict")}
            </button>
          </div>
          {asset ? (
            <p
              className="field-help"
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.4rem",
                marginTop: "0.75rem",
                color: "var(--brand-dark)",
                fontWeight: 600,
              }}
            >
              <Icon name="check" size={18} />
              {asset.filename}
            </p>
          ) : null}
        </article>

        <article className="surface-card">
          <h3 className="section-title" style={iconTitleStyle}>
            <Icon name="leaf" size={22} />
            {t("pest.outputTitle")}
          </h3>

          {busy && !result ? (
            <LoadingState icon="pest" />
          ) : result ? (
            <div className={`result-card ${severityCardClass}`}>
              <span className="stat-label">Likely problem</span>
              <p className="stat-value" style={{ color: "var(--ink)", marginBottom: "0.5rem" }}>
                {result.disease}
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginBottom: "0.75rem" }}>
                <span className={`badge ${severityBadgeClass}`}>{severityLabel}</span>
                <span className="badge">{matchLabel}</span>
              </div>

              {isUncertain && (
                <p
                  style={{
                    fontSize: "0.95rem",
                    color: "var(--ink-secondary)",
                    lineHeight: 1.5,
                    marginBottom: "0.75rem",
                  }}
                >
                  This is a best guess from your description. Before buying any spray,
                  confirm with your local Krishi Vigyan Kendra or agriculture officer.
                </p>
              )}

              <h4 className="section-title" style={{ marginBottom: "0.4rem" }}>
                What to do now
              </h4>
              <p style={{ fontSize: "1rem", color: "var(--ink)", lineHeight: 1.55 }}>
                {result.advice}
              </p>

              <hr className="divider" />

              <h4 className="section-title" style={{ marginBottom: "0.5rem" }}>
                Treatment and prevention steps
              </h4>
              <ol
                style={{
                  paddingLeft: "1.4rem",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.6rem",
                }}
              >
                {result.preventive_actions.map((action, idx) => (
                  <li key={idx} style={{ fontSize: "1rem", color: "var(--ink)", lineHeight: 1.55 }}>
                    {action}
                  </li>
                ))}
              </ol>

              {/* Additive field: where the advice comes from (e.g. an ICAR or
                  state agriculture department page). Older APIs omit it. */}
              {result.source && (
                <p
                  style={{
                    fontSize: "0.9rem",
                    color: "var(--ink-secondary)",
                    marginTop: "0.75rem",
                  }}
                >
                  Source: {result.source}
                </p>
              )}
            </div>
          ) : (
            <EmptyState icon="pest" message={t("pest.empty")} />
          )}
        </article>
      </section>
    </div>
  );
}

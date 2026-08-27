"use client";

import { useCallback, useState, type CSSProperties } from "react";

import { AsyncSection, ErrorNotice } from "@/components/ui/AsyncState";
import { Icon } from "@/components/ui/Icons";
import { useLanguage } from "@/contexts/LanguageContext";
import { fetchModelMetadata, retrainModels } from "@/lib/api";
import { toUserMessage } from "@/lib/errors";
import { useAsyncResource } from "@/lib/hooks";
import type { TranslationKey } from "@/lib/i18n";
import type { SoilFeatureKey } from "@/lib/types";

/** Plain-words labels for the raw feature columns (N, P, K, ph, ...). */
const FEATURE_LABEL_KEYS: Record<SoilFeatureKey, TranslationKey> = {
  N: "common.nitrogen",
  P: "common.phosphorus",
  K: "common.potassium",
  temperature: "common.temperature",
  humidity: "common.humidity",
  ph: "common.soilPh",
  rainfall: "common.rainfall"
};

const cellStyle: CSSProperties = {
  padding: "0.65rem 0.75rem",
  borderBottom: "1px solid var(--line)",
  textAlign: "left",
  fontSize: "0.98rem",
  whiteSpace: "nowrap"
};

const headCellStyle: CSSProperties = {
  ...cellStyle,
  fontWeight: 700,
  color: "var(--ink-secondary)",
  borderBottom: "2px solid var(--line-strong)"
};

function ScoreBar({ percent }: { percent: number }) {
  return (
    <div
      aria-hidden="true"
      style={{
        height: 8,
        background: "var(--bg-subtle)",
        borderRadius: 999,
        overflow: "hidden",
        marginTop: "0.35rem"
      }}
    >
      <div
        style={{
          width: `${Math.max(0, Math.min(100, percent))}%`,
          height: "100%",
          background: "var(--brand)"
        }}
      />
    </div>
  );
}

export function ModelInsightsPage() {
  const { t } = useLanguage();
  const loadMetadata = useCallback(() => fetchModelMetadata(), []);
  const metadataResource = useAsyncResource(loadMetadata, t("feedback.loadFailed"));
  const [retraining, setRetraining] = useState(false);
  const [retrainError, setRetrainError] = useState<string | null>(null);

  async function handleRetrain() {
    setRetraining(true);
    setRetrainError(null);
    try {
      const result = await retrainModels();
      metadataResource.setData(result);
    } catch (caught) {
      setRetrainError(toUserMessage(caught, t("feedback.error")));
    } finally {
      setRetraining(false);
    }
  }

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">{t("nav.models")}</h1>
        <p className="page-subtitle">
          See how the crop suggestion is made, and how often it is right.
        </p>
      </div>

      {retrainError && (
        <ErrorNotice message={retrainError} onDismiss={() => setRetrainError(null)} />
      )}

      <AsyncSection resource={metadataResource} icon="chart" emptyMessage={t("feedback.loadFailed")}>
        {(metadata) => {
          const best =
            metadata.model_scores.find((score) => score.model_name === metadata.best_model) ??
            metadata.model_scores[0];
          const matchedOf100 = best ? Math.round(best.accuracy * 100) : null;

          return (
            <>
              {/* The plain-language answer first. */}
              <section className="result-card result-card-success" style={{ marginBottom: "1.25rem" }}>
                {matchedOf100 !== null && (
                  <p
                    style={{
                      fontSize: "1.6rem",
                      fontWeight: 700,
                      lineHeight: 1.3,
                      color: "var(--ink)",
                      marginBottom: "0.6rem"
                    }}
                  >
                    In our tests, {matchedOf100} out of 100 crop suggestions matched the crop that
                    really grew best.
                  </p>
                )}
                <p style={{ fontSize: "1.05rem", lineHeight: 1.55, color: "var(--ink)" }}>
                  We compared {metadata.dataset_rows.toLocaleString()} real field records — soil
                  readings, rain, and temperature, together with the crop that actually did well on
                  that field. The app uses those records to suggest a crop for numbers like yours.
                  It is a guide, not a guarantee: your local mandi and seed supply matter too.
                </p>
                <div className="stats-row">
                  <div className="stat-item">
                    <span className="stat-label">{t("models.datasetRows")}</span>
                    <span className="stat-value">{metadata.dataset_rows.toLocaleString()}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">{t("models.trainedAt")}</span>
                    <span className="stat-value" style={{ fontSize: "1.25rem" }}>
                      {new Date(metadata.trained_at).toLocaleDateString()}
                    </span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">{t("models.totalModels")}</span>
                    <span className="stat-value">{metadata.model_scores.length}</span>
                  </div>
                </div>
              </section>

              {/* What the suggestion looks at, in plain words. */}
              <section className="surface-card" style={{ marginBottom: "1.25rem" }}>
                <h3 className="section-title">{t("models.featureImportance")}</h3>
                <p className="page-subtitle" style={{ marginBottom: "1rem" }}>
                  Which of your numbers count the most when the app picks a crop.
                </p>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
                  {metadata.feature_importance.map((fi) => (
                    <div key={fi.feature}>
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          gap: "0.75rem"
                        }}
                      >
                        <strong style={{ fontSize: "1rem" }}>
                          {t(FEATURE_LABEL_KEYS[fi.feature] ?? "common.status")}
                        </strong>
                        <span className="badge badge-info">{(fi.importance * 100).toFixed(1)}%</span>
                      </div>
                      <ScoreBar percent={fi.importance * 100} />
                    </div>
                  ))}
                </div>
              </section>

              {/* The detailed numbers, below the plain summary. */}
              <section className="surface-card">
                <h3 className="section-title">{t("models.comparison")}</h3>
                <p className="page-subtitle" style={{ marginBottom: "1rem" }}>
                  We test several methods on the same records and use the one that is right most
                  often. Accuracy means: out of 100 test fields, how many suggestions matched.
                </p>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <thead>
                      <tr>
                        <th style={headCellStyle}>{t("models.modelName")}</th>
                        <th style={headCellStyle}>{t("models.accuracy")}</th>
                        <th style={headCellStyle}>{t("models.f1Score")}</th>
                        <th style={headCellStyle}>{t("models.top3")}</th>
                        <th style={headCellStyle}>{t("models.time")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {metadata.model_scores.map((score) => (
                        <tr key={score.model_name}>
                          <td style={cellStyle}>
                            <strong>{score.model_name}</strong>
                            {score.model_name === metadata.best_model && (
                              <span className="badge badge-success" style={{ marginLeft: "0.5rem" }}>
                                <Icon name="check" size={14} />
                                {t("common.bestMatch")}
                              </span>
                            )}
                          </td>
                          <td style={cellStyle}>
                            <div style={{ fontWeight: 700 }}>{(score.accuracy * 100).toFixed(1)}%</div>
                            <ScoreBar percent={score.accuracy * 100} />
                          </td>
                          <td style={cellStyle}>{(score.macro_f1 * 100).toFixed(1)}%</td>
                          <td style={cellStyle}>{(score.top3_accuracy * 100).toFixed(1)}%</td>
                          <td style={cellStyle}>{score.training_seconds.toFixed(1)}s</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {metadata.skipped_models.length > 0 && (
                  <div style={{ marginTop: "1.25rem" }}>
                    <h4
                      style={{
                        marginBottom: "0.5rem",
                        fontSize: "1rem",
                        color: "var(--ink-secondary)"
                      }}
                    >
                      {t("models.skipped")}
                    </h4>
                    <ul style={{ paddingLeft: "1.25rem", color: "var(--ink-secondary)" }}>
                      {metadata.skipped_models.map((sm) => (
                        <li key={sm.model_name} style={{ marginBottom: "0.25rem" }}>
                          {sm.model_name}: {sm.reason}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <div style={{ marginTop: "1.25rem" }}>
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={handleRetrain}
                    disabled={retraining}
                  >
                    {retraining ? t("common.loading") : t("models.retrain")}
                  </button>
                  <p className="field-help">
                    Rebuilds the suggestions from the latest records. This can take a minute.
                  </p>
                </div>
              </section>
            </>
          );
        }}
      </AsyncSection>
    </div>
  );
}

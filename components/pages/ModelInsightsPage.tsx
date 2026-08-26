"use client";

import { useCallback, useState } from "react";

import { AsyncSection, ErrorNotice } from "@/components/ui/AsyncState";
import { PageHeader } from "@/components/ui/PageHeader";
import { useLanguage } from "@/contexts/LanguageContext";
import { fetchModelMetadata, retrainModels } from "@/lib/api";
import { toUserMessage } from "@/lib/errors";
import { useAsyncResource } from "@/lib/hooks";

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
      <PageHeader
        eyebrow={t("nav.models")}
        title={t("models.title")}
        description={t("models.subtitle")}
      />

      {retrainError && (
        <ErrorNotice message={retrainError} onDismiss={() => setRetrainError(null)} />
      )}

      <AsyncSection
        resource={metadataResource}
        icon="🤖"
        emptyMessage={t("models.subtitle")}
      >
        {(metadata) => (
          <>
            <section className="surface-card">
              <h3>📊 {t("models.overview")}</h3>
              <div className="stats-grid">
                <div className="stat-card">
                  <span>{t("models.bestModel")}</span>
                  <strong>{metadata.best_model}</strong>
                </div>
                <div className="stat-card">
                  <span>{t("models.datasetRows")}</span>
                  <strong>{metadata.dataset_rows.toLocaleString()}</strong>
                </div>
                <div className="stat-card">
                  <span>{t("models.trainedAt")}</span>
                  <strong>{new Date(metadata.trained_at).toLocaleDateString()}</strong>
                </div>
                <div className="stat-card">
                  <span>{t("models.totalModels")}</span>
                  <strong>{metadata.model_scores.length}</strong>
                </div>
              </div>
            </section>

            <section className="dashboard-grid mt-4">
              <article className="surface-card">
                <h3>🏆 {t("models.comparison")}</h3>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>{t("models.modelName")}</th>
                      <th>{t("models.accuracy")}</th>
                      <th>{t("models.f1Score")}</th>
                      <th>{t("models.top3")}</th>
                      <th>{t("models.time")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {metadata.model_scores.map((score) => (
                      <tr key={score.model_name}>
                        <td>
                          <strong>{score.model_name}</strong>
                          {score.model_name === metadata.best_model && (
                            <span className="badge badge-success" style={{ marginLeft: "0.5rem" }}>Best</span>
                          )}
                        </td>
                        <td>
                          <div>{(score.accuracy * 100).toFixed(1)}%</div>
                          <div className="model-score-bar">
                            <div className="model-score-fill" style={{ width: `${score.accuracy * 100}%` }} />
                          </div>
                        </td>
                        <td>{(score.macro_f1 * 100).toFixed(1)}%</td>
                        <td>{(score.top3_accuracy * 100).toFixed(1)}%</td>
                        <td>{score.training_seconds.toFixed(1)}s</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </article>

              <article className="surface-card">
                <h3>📈 {t("models.featureImportance")}</h3>
                <div className="result-stack">
                  {metadata.feature_importance.map((fi) => (
                    <div key={fi.feature} className="result-card">
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <strong>{fi.feature}</strong>
                        <span className="badge badge-info">{(fi.importance * 100).toFixed(1)}%</span>
                      </div>
                      <div className="model-score-bar" style={{ marginTop: "0.4rem" }}>
                        <div className="model-score-fill" style={{ width: `${fi.importance * 100}%` }} />
                      </div>
                    </div>
                  ))}
                </div>

                {metadata.skipped_models.length > 0 && (
                  <div style={{ marginTop: "1rem" }}>
                    <h4 style={{ marginBottom: "0.5rem", color: "var(--muted)" }}>{t("models.skipped")}</h4>
                    <ul className="bullet-list">
                      {metadata.skipped_models.map((sm) => (
                        <li key={sm.model_name}>{sm.model_name}: {sm.reason}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <div style={{ marginTop: "1rem" }}>
                  <button
                    type="button"
                    className="primary-btn"
                    onClick={handleRetrain}
                    disabled={retraining}
                  >
                    {retraining ? t("common.loading") : t("models.retrain")}
                  </button>
                </div>
              </article>
            </section>
          </>
        )}
      </AsyncSection>
    </div>
  );
}

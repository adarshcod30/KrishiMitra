"use client";

import { useCallback, useRef, useState } from "react";

import { AsyncSection } from "@/components/ui/AsyncState";
import { Icon, type IconName } from "@/components/ui/Icons";
import { useLanguage } from "@/contexts/LanguageContext";
import { fetchKnowledgeLibrary } from "@/lib/api";
import { useAsyncResource } from "@/lib/hooks";

const CATEGORIES = ["all", "production", "treatment", "horticulture", "soil", "market"] as const;

const CATEGORY_ICONS: Record<string, IconName> = {
  all: "book",
  production: "plant",
  treatment: "pest",
  horticulture: "leaf",
  soil: "soil",
  market: "market"
};

function categoryIcon(cat: string): IconName {
  return CATEGORY_ICONS[cat] ?? "book";
}

export function KnowledgePage() {
  const { t, language } = useLanguage();
  const [category, setCategory] = useState<string>("all");
  const [query, setQuery] = useState("");

  // The query is applied on demand (Search / Enter), not on every keystroke.
  const submittedQueryRef = useRef("");

  const loadArticles = useCallback(
    () => fetchKnowledgeLibrary(language, submittedQueryRef.current || undefined),
    [language]
  );

  const articlesResource = useAsyncResource(loadArticles, t("feedback.loadFailed"));

  function submitQuery() {
    submittedQueryRef.current = query.trim();
    articlesResource.reload();
  }

  const filtered = (articlesResource.data ?? []).filter(
    (article) => category === "all" || article.category === category
  );

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">{t("nav.knowledge")}</h1>
        <p className="page-subtitle">{t("knowledge.subtitle")}</p>
      </div>

      <section className="surface-card" style={{ marginBottom: "1.25rem" }}>
        <label className="field-label" htmlFor="knowledge-search">
          {t("common.search")}
        </label>
        <div className="search-input-group">
          <input
            id="knowledge-search"
            className="field-input"
            placeholder={t("knowledge.searchPlaceholder")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                submitQuery();
              }
            }}
          />
          <button
            type="button"
            className="btn-primary"
            onClick={submitQuery}
            disabled={articlesResource.isLoading}
          >
            <Icon name="search" size={20} />
            {articlesResource.isLoading ? t("common.loading") : t("common.search")}
          </button>
        </div>

        <div className="portal-tabs" style={{ marginTop: "1rem", marginBottom: 0 }}>
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              type="button"
              className={`portal-tab-btn ${category === cat ? "active" : ""}`}
              onClick={() => setCategory(cat)}
            >
              {t(`knowledge.cat_${cat}`)}
            </button>
          ))}
        </div>
      </section>

      <section className="surface-card">
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "0.75rem",
            marginBottom: "1rem"
          }}
        >
          <h3 className="section-title" style={{ marginBottom: 0 }}>
            {t("knowledge.articles")}
          </h3>
          {filtered.length > 0 && (
            <span className="badge badge-info">
              {filtered.length} {t("knowledge.articles")}
            </span>
          )}
        </div>

        <AsyncSection
          resource={articlesResource}
          icon="book"
          emptyMessage={t("knowledge.empty")}
          isEmpty={() => filtered.length === 0}
        >
          {() => (
            <div className="recommendation-grid">
              {filtered.map((article) => (
                <article key={article.id} className="recommendation-card">
                  <div className="recommendation-header">
                    <div className="crop-icon-wrapper">
                      <Icon name={categoryIcon(article.category || "production")} size={26} />
                    </div>
                    <div className="recommendation-title-group">
                      <h4 className="crop-name" style={{ fontSize: "1.1rem", lineHeight: 1.4 }}>
                        {article.title}
                      </h4>
                      <span
                        className="badge badge-success"
                        style={{ marginTop: "0.35rem", textTransform: "capitalize" }}
                      >
                        {t(`knowledge.cat_${article.category || "production"}`)}
                      </span>
                    </div>
                  </div>

                  <p className="tips-content">{article.summary}</p>

                  {article.url && (
                    <a
                      href={article.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn-secondary"
                    >
                      {t("news.readMore")}
                      <Icon name="arrow-right" size={18} />
                    </a>
                  )}
                </article>
              ))}
            </div>
          )}
        </AsyncSection>
      </section>
    </div>
  );
}

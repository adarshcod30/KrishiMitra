"use client";

import { useCallback, useRef, useState } from "react";

import { AsyncSection } from "@/components/ui/AsyncState";
import { PageHeader } from "@/components/ui/PageHeader";
import { useLanguage } from "@/contexts/LanguageContext";
import { fetchKnowledgeLibrary } from "@/lib/api";
import { useAsyncResource } from "@/lib/hooks";

const CATEGORIES = ["all", "production", "treatment", "horticulture", "soil", "market"] as const;

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

  const categoryIcon = (cat: string) => {
    const icons: Record<string, string> = {
      production: "🌾", treatment: "💊", horticulture: "🌺", soil: "🧪", market: "📈", all: "📚",
    };
    return icons[cat] || "📄";
  };

  return (
    <div className="page-container">
      <PageHeader
        eyebrow={t("nav.knowledge")}
        title={t("knowledge.title")}
        description={t("knowledge.subtitle")}
      />

      <section className="surface-card">
        <div className="inline-actions" style={{ marginBottom: "0.8rem" }}>
          <input
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
            className="primary-btn small-btn"
            onClick={submitQuery}
            disabled={articlesResource.isLoading}
          >
            {articlesResource.isLoading ? t("common.loading") : t("common.search")}
          </button>
        </div>

        <div className="category-tabs">
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              type="button"
              className={`category-tab ${category === cat ? "active" : ""}`}
              onClick={() => setCategory(cat)}
            >
              {categoryIcon(cat)} {t(`knowledge.cat_${cat}`)}
            </button>
          ))}
        </div>
      </section>

      <section className="surface-card">
        <div className="flex items-center justify-between mb-6">
          <h3 className="mb-0">{categoryIcon(category)} {t("knowledge.articles")}</h3>
          {filtered.length > 0 && (
            <div className="status-badge info">
               📚 {filtered.length} {t("knowledge.articles")}
            </div>
          )}
        </div>

        <AsyncSection
          resource={articlesResource}
          icon="📚"
          emptyMessage={t("knowledge.empty")}
          isEmpty={() => filtered.length === 0}
        >
          {() => (
          <div className="result-layout animate-in fade-in slide-in-from-bottom-4 duration-500">
            {filtered.map((article) => (
              <div key={article.id} className="recommendation-card">
                <div className="recommendation-header">
                  <div className="crop-icon-wrapper" style={{ width: '48px', height: '48px', fontSize: '1.5rem', background: 'var(--brand-subtle)' }}>
                    {categoryIcon(article.category || 'production')}
                  </div>
                  <div className="recommendation-title-group">
                    <h4 className="crop-name" style={{ fontSize: '1.1rem', lineHeight: '1.4' }}>{article.title}</h4>
                    <span className="badge badge-brand mt-1" style={{ fontSize: '0.7rem', textTransform: 'capitalize' }}>
                      {article.category || 'general'}
                    </span>
                  </div>
                </div>

                <p className="tips-content mt-3" style={{ fontSize: '0.9rem', color: 'var(--ink-secondary)' }}>
                  {article.summary}
                </p>

                {article.url && (
                  <div className="mt-4 pt-4 border-t border-dashed border-line">
                    <a 
                      href={article.url} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="badge badge-brand flex items-center justify-center py-2 text-sm no-underline hover-lift"
                      style={{ background: 'transparent', border: '1px solid var(--brand)', color: 'var(--brand)' }}
                    >
                      {t("news.readMore")} →
                    </a>
                  </div>
                )}
              </div>
            ))}
          </div>
          )}
        </AsyncSection>
      </section>
    </div>
  );
}

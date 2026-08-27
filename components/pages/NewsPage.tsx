"use client";

import { useCallback } from "react";

import { AsyncSection } from "@/components/ui/AsyncState";
import { Icon } from "@/components/ui/Icons";
import { useLanguage } from "@/contexts/LanguageContext";
import { fetchNewsFeed } from "@/lib/api";
import { useAsyncResource } from "@/lib/hooks";

export function NewsPage() {
  const { t, language } = useLanguage();
  const loadNews = useCallback(() => fetchNewsFeed(language), [language]);
  const newsResource = useAsyncResource(loadNews, t("feedback.loadFailed"));
  const newsCount = newsResource.data?.length ?? 0;

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">{t("nav.news")}</h1>
        <p className="page-subtitle">{t("news.subtitle")}</p>
      </div>

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
            {t("news.latestTitle")}
          </h3>
          {newsCount > 0 && (
            <span className="badge badge-info">
              {newsCount} {t("nav.news")}
            </span>
          )}
        </div>

        <AsyncSection
          resource={newsResource}
          icon="news"
          emptyMessage={t("news.empty")}
          isEmpty={(items) => items.length === 0}
        >
          {(news) => (
            <div className="recommendation-grid">
              {news.map((item, i) => (
                <article key={`${item.url}-${i}`} className="recommendation-card">
                  <div className="recommendation-header">
                    <div className="crop-icon-wrapper">
                      <Icon name="news" size={26} />
                    </div>
                    <div className="recommendation-title-group">
                      <h4 className="crop-name" style={{ fontSize: "1.1rem", lineHeight: 1.4 }}>
                        {item.title}
                      </h4>
                      <div
                        style={{
                          display: "flex",
                          flexWrap: "wrap",
                          alignItems: "center",
                          gap: "0.5rem",
                          marginTop: "0.35rem"
                        }}
                      >
                        <span className="badge badge-success">{item.source}</span>
                        {item.published_at && (
                          <span
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "0.3rem",
                              fontSize: "0.9rem",
                              color: "var(--ink-secondary)"
                            }}
                          >
                            <Icon name="calendar" size={16} />
                            {new Date(item.published_at).toLocaleDateString()}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <p className="tips-content">{item.summary}</p>

                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-secondary"
                  >
                    {t("news.readMore")}
                    <Icon name="arrow-right" size={18} />
                  </a>
                </article>
              ))}
            </div>
          )}
        </AsyncSection>
      </section>
    </div>
  );
}

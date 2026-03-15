"use client";

import { useEffect, useState } from "react";

import { PageHeader } from "@/components/ui/PageHeader";
import { useLanguage } from "@/contexts/LanguageContext";
import { fetchNewsFeed } from "@/lib/api";
import type { NewsItem } from "@/lib/types";

export function NewsPage() {
  const { t, language } = useLanguage();
  const [news, setNews] = useState<NewsItem[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setBusy(true);
    fetchNewsFeed(language)
      .then(setNews)
      .catch(() => setNews([]))
      .finally(() => setBusy(false));
  }, [language]);

  return (
    <div className="page-container">
      <PageHeader
        eyebrow={t("nav.news")}
        title={t("news.title")}
        description={t("news.subtitle")}
      />

      <section className="surface-card">
        <div className="flex items-center justify-between mb-6">
          <h3 className="mb-0">📰 {t("news.latestTitle")}</h3>
          {news.length > 0 && (
            <div className="status-badge info">
              🌍 {news.length} {t("nav.news")}
            </div>
          )}
        </div>

        {busy && <p className="muted-copy">{t("common.loading")}</p>}
        {news.length > 0 ? (
          <div className="result-layout animate-in fade-in slide-in-from-bottom-4 duration-500">
            {news.map((item, i) => (
              <div key={`${item.url}-${i}`} className="recommendation-card">
                <div className="recommendation-header">
                  <div className="crop-icon-wrapper" style={{ width: '48px', height: '48px', fontSize: '1.5rem', background: 'var(--brand-subtle)' }}>🌍</div>
                  <div className="recommendation-title-group">
                    <h4 className="crop-name" style={{ fontSize: '1.1rem', lineHeight: '1.4' }}>{item.title}</h4>
                    <div className="flex flex-wrap gap-2 mt-1">
                      <span className="badge badge-brand" style={{ fontSize: '0.7rem' }}>📰 {item.source}</span>
                      {item.published_at && (
                        <span className="text-xs muted-copy" style={{ fontSize: '0.7rem', display: 'flex', alignItems: 'center' }}>
                          📅 {new Date(item.published_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                <p className="tips-content mt-3" style={{ fontSize: '0.9rem', color: 'var(--ink-secondary)' }}>
                  {item.summary}
                </p>

                <div className="mt-4 pt-4 border-t border-dashed border-line">
                  <a 
                    href={item.url} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="badge badge-brand flex items-center justify-center py-2 text-sm no-underline hover-lift"
                    style={{ background: 'transparent', border: '1px solid var(--brand)', color: 'var(--brand)' }}
                  >
                    {t("news.readMore")} →
                  </a>
                </div>
              </div>
            ))}
          </div>
        ) : (
          !busy && (
            <div className="empty-state-illust py-8">
              <div className="illust-icon opacity-20">📰</div>
              <p className="muted-copy">{t("news.empty")}</p>
            </div>
          )
        )}
      </section>
    </div>
  );
}

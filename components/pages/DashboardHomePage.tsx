"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ActiveFarmerBanner } from "@/components/farmers/ActiveFarmerBanner";
import { FarmerSearchPanel } from "@/components/farmers/FarmerSearchPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { useLanguage } from "@/contexts/LanguageContext";
import { fetchDashboardSummary } from "@/lib/api";
import type { DashboardSummary } from "@/lib/types";

const FEATURE_CARDS = [
  { href: "/dashboard/crop-intelligence", titleKey: "nav.crop", descKey: "dashboard.cropDesc", icon: "🌾", bg: "rgba(16, 185, 129, 0.05)" },
  { href: "/dashboard/soil-health", titleKey: "nav.soil", descKey: "dashboard.soilDesc", icon: "🧪", bg: "rgba(234, 88, 12, 0.05)" },
  { href: "/dashboard/irrigation-planner", titleKey: "nav.irrigation", descKey: "dashboard.irrigationDesc", icon: "💧", bg: "rgba(2, 132, 199, 0.05)" },
  { href: "/dashboard/fertilizer", titleKey: "nav.fertilizer", descKey: "dashboard.fertilizerDesc", icon: "🧬", bg: "rgba(217, 119, 6, 0.05)" },
  { href: "/dashboard/pest-detection", titleKey: "nav.pest", descKey: "dashboard.pestDesc", icon: "🐛", bg: "rgba(225, 29, 72, 0.05)" },
  { href: "/dashboard/weather", titleKey: "nav.weather", descKey: "dashboard.weatherDesc", icon: "🌤️", bg: "rgba(2, 132, 199, 0.05)" },
  { href: "/dashboard/market-prices", titleKey: "nav.market", descKey: "dashboard.marketDesc", icon: "📈", bg: "rgba(16, 185, 129, 0.05)" },
  { href: "/dashboard/schemes", titleKey: "nav.schemes", descKey: "dashboard.schemesDesc", icon: "🏛️", bg: "rgba(6, 95, 70, 0.05)" },
  { href: "/dashboard/tool-rental", titleKey: "nav.rental", descKey: "dashboard.rentalDesc", icon: "🚜", bg: "rgba(217, 119, 6, 0.05)" },
] as const;

export function DashboardHomePage() {
  const { t } = useLanguage();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);

  useEffect(() => {
    void fetchDashboardSummary().then(setSummary).catch(() => null);
  }, []);

  return (
    <div className="page-container">
      <div className="page-header">
        <div className="badge badge-brand">{t("nav.dashboard")}</div>
        <h1 className="page-title">{t("dashboard.title")}</h1>
        <p className="page-subtitle">{t("dashboard.subtitle")}</p>
      </div>
      <ActiveFarmerBanner />

      <div className="surface-card summary-card">
        <h3 className="section-title">📊 {t("dashboard.quickInsights")}</h3>
        <div className="stats-row">
          <div className="stat-item">
            <span className="stat-label">{t("dashboard.totalFarmers")}</span>
            <strong className="stat-value">{summary?.active_users ?? 0}</strong>
          </div>
          <div className="divider" />
          <div className="stat-item">
            <span className="stat-label">{t("dashboard.totalFarms")}</span>
            <strong className="stat-value">{summary?.total_farms ?? 0}</strong>
          </div>
          <div className="divider" />
          <div className="stat-item">
            <span className="stat-label">{t("dashboard.savedRecords")}</span>
            <strong className="stat-value">{summary?.advisory_runs ?? 0}</strong>
          </div>
        </div>
      </div>

      <div className="dashboard-grid mt-4">
        <div className="surface-card features-container">
          <h3 className="section-title">🚀 {t("dashboard.featureCards")}</h3>
          <div className="features-grid-airy">
            {FEATURE_CARDS.map((card) => (
              <Link 
                key={card.href} 
                href={card.href as never} 
                className="surface-card-interactive feature-card-airy"
                style={{ backgroundColor: card.bg }}
              >
                <div className="feature-icon-wrapper">{card.icon}</div>
                <div className="feature-content">
                  <h4>{t(card.titleKey)}</h4>
                  <p>{t(card.descKey)}</p>
                </div>
              </Link>
            ))}
          </div>
        </div>

        <div className="surface-card">
          <FarmerSearchPanel />
        </div>
      </div>
    </div>
  );
}

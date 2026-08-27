"use client";

import Link from "next/link";

import { FarmerSearchPanel } from "@/components/farmers/FarmerSearchPanel";
import { Icon } from "@/components/ui/Icons";
import { useLanguage } from "@/contexts/LanguageContext";

/**
 * Task-first home: each card is one thing a farmer wants to do today,
 * in priority order. The whole card is the tap target.
 */
const PRIMARY_TASKS = [
  { href: "/dashboard/crop-intelligence", titleKey: "nav.crop", descKey: "welcome.benefit1", icon: "plant" },
  { href: "/dashboard/soil-health", titleKey: "nav.soil", descKey: "dashboard.soilDesc", icon: "soil" },
  { href: "/dashboard/irrigation-planner", titleKey: "nav.irrigation", descKey: "dashboard.irrigationDesc", icon: "water" },
  { href: "/dashboard/fertilizer", titleKey: "nav.fertilizer", descKey: "dashboard.fertilizerDesc", icon: "fertilizer" },
  { href: "/dashboard/pest-detection", titleKey: "nav.pest", descKey: "dashboard.pestDesc", icon: "pest" },
  { href: "/dashboard/weather", titleKey: "nav.weather", descKey: "dashboard.weatherDesc", icon: "weather" },
  { href: "/dashboard/market-prices", titleKey: "nav.market", descKey: "dashboard.marketDesc", icon: "market" },
  { href: "/dashboard/schemes", titleKey: "nav.schemes", descKey: "dashboard.schemesDesc", icon: "scheme" },
] as const;

const SECONDARY_TASKS = [
  { href: "/dashboard/tool-rental", titleKey: "nav.rental", descKey: "dashboard.rentalDesc", icon: "tools" },
  { href: "/dashboard/knowledge", titleKey: "nav.knowledge", descKey: "dashboard.knowledgeDesc", icon: "book" },
  { href: "/dashboard/news", titleKey: "nav.news", descKey: "dashboard.newsDesc", icon: "news" },
  { href: "/dashboard/farmer-history", titleKey: "nav.history", descKey: "dashboard.historyDesc", icon: "history" },
] as const;

export function DashboardHomePage() {
  const { t } = useLanguage();

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">{t("app.tagline")}</h1>
        <p className="page-subtitle">{t("welcome.ctaBody")}</p>
      </div>

      {/* Active-farmer strip: shows the selected farmer, or asks the farmer
          to pick their name so results get saved to their record. */}
      <div className="surface-card mb-4">
        <FarmerSearchPanel compact />
      </div>

      <div className="action-grid">
        {PRIMARY_TASKS.map((task) => (
          <Link key={task.href} href={task.href as never} className="action-card">
            <span className="action-card-icon">
              <Icon name={task.icon} size={26} />
            </span>
            <span>
              <span className="action-card-label">{t(task.titleKey)}</span>
              <span className="action-card-outcome">{t(task.descKey)}</span>
            </span>
          </Link>
        ))}
      </div>

      <hr className="divider mt-4" />

      <div className="action-grid">
        {SECONDARY_TASKS.map((task) => (
          <Link key={task.href} href={task.href as never} className="action-card">
            <span className="action-card-icon">
              <Icon name={task.icon} size={26} />
            </span>
            <span>
              <span className="action-card-label">{t(task.titleKey)}</span>
              <span className="action-card-outcome">{t(task.descKey)}</span>
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}

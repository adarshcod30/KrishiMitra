"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { LanguageSwitcher } from "@/components/ui/LanguageSwitcher";
import { useLanguage } from "@/contexts/LanguageContext";

const NAV_SECTIONS = [
  {
    label: "nav.coreTools",
    items: [
      { href: "/dashboard", key: "nav.dashboard", icon: "📊" },
      { href: "/dashboard/crop-intelligence", key: "nav.crop", icon: "🌾" },
      { href: "/dashboard/soil-health", key: "nav.soil", icon: "🧪" },
      { href: "/dashboard/irrigation-planner", key: "nav.irrigation", icon: "💧" },
      { href: "/dashboard/fertilizer", key: "nav.fertilizer", icon: "🧬" },
      { href: "/dashboard/pest-detection", key: "nav.pest", icon: "🐛" },
      { href: "/dashboard/weather", key: "nav.weather", icon: "🌤️" },
    ],
  },
  {
    label: "nav.marketServices",
    items: [
      { href: "/dashboard/market-prices", key: "nav.market", icon: "📈" },
      { href: "/dashboard/schemes", key: "nav.schemes", icon: "🏛️" },
      { href: "/dashboard/tool-rental", key: "nav.rental", icon: "🚜" },
    ],
  },
  {
    label: "nav.knowledgeHub",
    items: [
      { href: "/dashboard/knowledge", key: "nav.knowledge", icon: "📚" },
      { href: "/dashboard/news", key: "nav.news", icon: "📰" },
      { href: "/dashboard/model-insights", key: "nav.models", icon: "🤖" },
    ],
  },
  {
    label: "nav.farmerRecords",
    items: [
      { href: "/dashboard/farmer-history", key: "nav.history", icon: "👤" },
    ],
  },
] as const;

export function DashboardShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { t } = useLanguage();

  return (
    <div className="platform-shell">
      <div className="platform-sidebar-container">
        <aside className="platform-sidebar">
          <Link href="/" className="sidebar-brand">
            <div className="brand-icon">🌱</div>
            <div className="brand-text">
              <span className="platform-label">{t("shell.platform")}</span>
              <h1>{t("app.name")}</h1>
            </div>
          </Link>

          <div className="sidebar-scrollable">
            <LanguageSwitcher />

            <nav className="sidebar-nav">
              {NAV_SECTIONS.map((section) => (
                <div key={section.label} className="nav-group">
                  <div className="sidebar-section-label">{t(section.label)}</div>
                  <div className="nav-items-stack">
                    {section.items.map((item) => {
                      const isActive = pathname === item.href;
                      return (
                        <Link
                          key={item.href}
                          href={item.href as never}
                          className={`sidebar-link ${isActive ? "active" : ""}`}
                        >
                          <span className="nav-icon">{item.icon}</span>
                          <span className="nav-label">{t(item.key)}</span>
                          {isActive && <div className="active-indicator" />}
                        </Link>
                      );
                    })}
                  </div>
                </div>
              ))}
            </nav>
          </div>
        </aside>
      </div>

      <main className="platform-content">
        <div className="content-inner">{children}</div>
      </main>
    </div>
  );
}

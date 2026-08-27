"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { Icon, type IconName } from "@/components/ui/Icons";
import { LanguageSwitcher } from "@/components/ui/LanguageSwitcher";
import { useLanguage } from "@/contexts/LanguageContext";

const NAV_SECTIONS = [
  {
    label: "nav.coreTools",
    items: [
      { href: "/dashboard", key: "nav.dashboard", icon: "home" },
      { href: "/dashboard/crop-intelligence", key: "nav.crop", icon: "plant" },
      { href: "/dashboard/soil-health", key: "nav.soil", icon: "soil" },
      { href: "/dashboard/irrigation-planner", key: "nav.irrigation", icon: "water" },
      { href: "/dashboard/fertilizer", key: "nav.fertilizer", icon: "fertilizer" },
      { href: "/dashboard/pest-detection", key: "nav.pest", icon: "pest" },
      { href: "/dashboard/weather", key: "nav.weather", icon: "weather" },
    ],
  },
  {
    label: "nav.marketServices",
    items: [
      { href: "/dashboard/market-prices", key: "nav.market", icon: "market" },
      { href: "/dashboard/schemes", key: "nav.schemes", icon: "scheme" },
      { href: "/dashboard/tool-rental", key: "nav.rental", icon: "tools" },
    ],
  },
  {
    label: "nav.knowledgeHub",
    items: [
      { href: "/dashboard/knowledge", key: "nav.knowledge", icon: "book" },
      { href: "/dashboard/news", key: "nav.news", icon: "news" },
      { href: "/dashboard/model-insights", key: "nav.models", icon: "chart" },
    ],
  },
  {
    label: "nav.farmerRecords",
    items: [
      { href: "/dashboard/farmer-history", key: "nav.history", icon: "history" },
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
            <div className="brand-icon" aria-hidden="true">
              <Icon name="leaf" size={26} />
            </div>
            <div className="brand-text">
              <h1>{t("app.name")}</h1>
              <span className="platform-label">{t("shell.platform")}</span>
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
                          aria-current={isActive ? "page" : undefined}
                        >
                          <span className="nav-icon" aria-hidden="true">
                            <Icon name={item.icon as IconName} size={22} />
                          </span>
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

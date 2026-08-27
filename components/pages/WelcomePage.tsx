"use client";

import Link from "next/link";

import { Icon } from "@/components/ui/Icons";
import { LanguageSwitcher } from "@/components/ui/LanguageSwitcher";
import { useLanguage } from "@/contexts/LanguageContext";

const BENEFITS = [
  { icon: "plant", key: "welcome.benefit1" },
  { icon: "market", key: "dashboard.marketDesc" },
  { icon: "language", key: "welcome.benefit2" },
  { icon: "tools", key: "welcome.benefit3" },
] as const;

export function WelcomePage() {
  const { t } = useLanguage();

  return (
    <div className="welcome-container">
      <div style={{ width: "100%", maxWidth: "600px" }}>
        <h1 className="welcome-title">{t("welcome.title")}</h1>
        <p className="welcome-subtitle">{t("welcome.subtitle")}</p>

        <div className="welcome-benefits-list">
          {BENEFITS.map((benefit) => (
            <div key={benefit.key} className="benefit-item">
              <span className="benefit-icon">
                <Icon name={benefit.icon} size={24} />
              </span>
              <strong>{t(benefit.key)}</strong>
            </div>
          ))}
        </div>

        <div className="mb-4">
          <LanguageSwitcher />
        </div>

        <Link
          href={"/dashboard" as never}
          className="btn-primary w-full"
          style={{ minHeight: "56px" }}
        >
          {t("welcome.ctaTitle")}
          <Icon name="arrow-right" size={22} />
        </Link>
      </div>
    </div>
  );
}

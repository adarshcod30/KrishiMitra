"use client";

import Link from "next/link";
import { LanguageSwitcher } from "@/components/ui/LanguageSwitcher";
import { useLanguage } from "@/contexts/LanguageContext";

const FEATURES = [
  { icon: "🌾", titleKey: "nav.crop", descKey: "dashboard.cropDesc", bg: "rgba(16, 185, 129, 0.05)" },
  { icon: "💧", titleKey: "nav.irrigation", descKey: "dashboard.irrigationDesc", bg: "rgba(2, 132, 199, 0.05)" },
  { icon: "🧪", titleKey: "nav.soil", descKey: "dashboard.soilDesc", bg: "rgba(234, 88, 12, 0.05)" },
  { icon: "🌤️", titleKey: "nav.weather", descKey: "dashboard.weatherDesc", bg: "rgba(2, 132, 199, 0.05)" },
] as const;

export function WelcomePage() {
  const { t } = useLanguage();

  return (
    <div className="welcome-container">
      <div className="welcome-inner">
        <div className="welcome-content">
          <div className="badge badge-brand mb-4">🌱 {t("app.tagline")}</div>
          <h1 className="welcome-title">{t("welcome.title")}</h1>
          <p className="welcome-subtitle">{t("welcome.subtitle")}</p>

          <div className="welcome-benefits-list">
            <div className="benefit-item">
              <span className="benefit-icon">🤖</span>
              <strong>{t("welcome.benefit1")}</strong>
            </div>
            <div className="benefit-item">
              <span className="benefit-icon">🌍</span>
              <strong>{t("welcome.benefit2")}</strong>
            </div>
            <div className="benefit-item">
              <span className="benefit-icon">📊</span>
              <strong>{t("welcome.benefit3")}</strong>
            </div>
          </div>

          <div className="welcome-actions-row">
            <LanguageSwitcher />
            <Link href={"/dashboard" as never} className="primary-btn pulse-glow">
              {t("common.enterDashboard")} →
            </Link>
          </div>
        </div>

        <div className="welcome-visuals">
          <div className="surface-card floating-card front-card">
            <h3>✨ {t("welcome.ctaTitle")}</h3>
            <p>{t("welcome.ctaBody")}</p>
          </div>
          
          <div className="surface-card floating-card back-card">
            <div className="features-preview-grid">
              {FEATURES.map((f) => (
                <div key={f.titleKey} className="feature-preview-item" style={{ backgroundColor: f.bg }}>
                  <span className="preview-icon">{f.icon}</span>
                  <div>
                    <strong>{t(f.titleKey)}</strong>
                    <p>{t(f.descKey)}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

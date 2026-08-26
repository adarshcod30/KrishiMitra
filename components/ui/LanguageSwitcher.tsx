"use client";

import { SUPPORTED_LANGUAGES } from "@/lib/constants";
import { useLanguage } from "@/contexts/LanguageContext";

export function LanguageSwitcher() {
  const { language, setLanguage, t } = useLanguage();

  // No `mounted` gate: LanguageContext reads localStorage through
  // useSyncExternalStore, so the hydration render matches the server output.
  return (
    <div className="language-toggle compact">
      <span className="language-toggle-title">{t("common.language")}</span>
      <div className="language-grid compact">
        {SUPPORTED_LANGUAGES.map((lang) => (
          <button
            key={lang.code}
            type="button"
            className={language === lang.code ? "language-box active compact" : "language-box compact"}
            onClick={() => setLanguage(lang.code)}
          >
            {lang.native}
          </button>
        ))}
      </div>
    </div>
  );
}

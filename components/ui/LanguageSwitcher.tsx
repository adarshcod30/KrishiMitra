"use client";

import { useState, useEffect } from "react";
import { SUPPORTED_LANGUAGES } from "@/lib/constants";
import { useLanguage } from "@/contexts/LanguageContext";

export function LanguageSwitcher() {
  const { language, setLanguage, t } = useLanguage();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return null;

  return (
    <div className="language-toggle compact">
      <span className="language-toggle-title">Lang</span>
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

"use client";

import { Icon } from "@/components/ui/Icons";
import { SUPPORTED_LANGUAGES } from "@/lib/constants";
import { useLanguage } from "@/contexts/LanguageContext";
import type { LanguageCode } from "@/lib/types";

/**
 * A native <select> listing all 11 languages by their native name. A plain
 * select is the most familiar and accessible picker on low-end Android
 * phones: the OS renders it full-screen with large rows.
 */
export function LanguageSwitcher() {
  const { language, setLanguage, t } = useLanguage();

  // No `mounted` gate: LanguageContext reads localStorage through
  // useSyncExternalStore, so the hydration render matches the server output.
  return (
    <div className="language-control">
      <label className="language-control-label" htmlFor="language-select">
        <Icon name="language" size={20} />
        {t("common.language")}
      </label>
      <select
        id="language-select"
        className="language-select"
        value={language}
        onChange={(event) => setLanguage(event.target.value as LanguageCode)}
      >
        {SUPPORTED_LANGUAGES.map((lang) => (
          <option key={lang.code} value={lang.code}>
            {lang.native}
          </option>
        ))}
      </select>
    </div>
  );
}

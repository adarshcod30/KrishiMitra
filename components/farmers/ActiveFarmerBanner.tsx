"use client";

import { useLanguage } from "@/contexts/LanguageContext";
import { useFarmerSession } from "@/contexts/FarmerSessionContext";

export function ActiveFarmerBanner() {
  const { t } = useLanguage();
  const { activeFarmer } = useFarmerSession();

  // No `mounted` gate: FarmerSessionContext reads localStorage through
  // useSyncExternalStore, so the hydration render matches the server output and
  // the stored farmer appears in the very next commit.
  return (
    <div className="active-farmer-banner">
      <span className="farmer-status-pill">{t("common.activeFarmer")}</span>
      <div className="farmer-details">
        {activeFarmer ? (
          <strong className="farmer-name">
            {activeFarmer.name} | {activeFarmer.farmer_id}
          </strong>
        ) : (
          <strong className="farmer-name">{t("common.noFarmer")}</strong>
        )}
      </div>
    </div>
  );
}

"use client";

import { Icon } from "@/components/ui/Icons";
import { useLanguage } from "@/contexts/LanguageContext";
import { useFarmerSession } from "@/contexts/FarmerSessionContext";

export function ActiveFarmerBanner() {
  const { t } = useLanguage();
  const { activeFarmer } = useFarmerSession();

  const placeLine = activeFarmer
    ? [activeFarmer.village, activeFarmer.district].filter(Boolean).join(", ")
    : "";

  // No `mounted` gate: FarmerSessionContext reads localStorage through
  // useSyncExternalStore, so the hydration render matches the server output and
  // the stored farmer appears in the very next commit.
  return (
    <div className={`active-farmer-banner ${activeFarmer ? "" : "muted"}`}>
      <span
        className="farmer-status-pill"
        style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}
      >
        <Icon name="farmer" size={18} />
        {t("common.activeFarmer")}
      </span>
      <div className="farmer-details">
        {activeFarmer ? (
          <>
            <strong className="farmer-name">{activeFarmer.name}</strong>
            <span className="farmer-meta">
              {placeLine ? `${placeLine} · ` : ""}
              {activeFarmer.farmer_id}
            </span>
          </>
        ) : (
          <strong className="farmer-name">{t("common.noFarmer")}</strong>
        )}
      </div>
    </div>
  );
}

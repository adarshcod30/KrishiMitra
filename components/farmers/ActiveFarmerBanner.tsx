"use client";

import { useState, useEffect } from "react";
import { useLanguage } from "@/contexts/LanguageContext";
import { useFarmerSession } from "@/contexts/FarmerSessionContext";

export function ActiveFarmerBanner() {
  const { t } = useLanguage();
  const { activeFarmer } = useFarmerSession();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return null;

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

"use client";

import type { ReactNode } from "react";

import { FarmerSessionProvider } from "@/contexts/FarmerSessionContext";
import { LanguageProvider } from "@/contexts/LanguageContext";

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <LanguageProvider>
      <FarmerSessionProvider>{children}</FarmerSessionProvider>
    </LanguageProvider>
  );
}

"use client";

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState
} from "react";

import type { FarmerSearchResult } from "@/lib/types";

interface FarmerSessionValue {
  activeFarmer: FarmerSearchResult | null;
  setActiveFarmer: (farmer: FarmerSearchResult | null) => void;
  clearActiveFarmer: () => void;
}

const STORAGE_KEY = "agrotech.activeFarmer";

const FarmerSessionContext = createContext<FarmerSessionValue | null>(null);

export function FarmerSessionProvider({ children }: { children: ReactNode }) {
  const [activeFarmer, setActiveFarmerState] = useState<FarmerSearchResult | null>(null);

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        setActiveFarmerState(JSON.parse(stored) as FarmerSearchResult);
      } catch {
        // Ignore
      }
    }
  }, []);

  const setActiveFarmer = useCallback((farmer: FarmerSearchResult | null) => {
    setActiveFarmerState(farmer);
    if (farmer) {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(farmer));
      return;
    }
    window.localStorage.removeItem(STORAGE_KEY);
  }, []);

  const clearActiveFarmer = useCallback(() => {
    setActiveFarmerState(null);
    window.localStorage.removeItem(STORAGE_KEY);
  }, []);

  const value = useMemo(
    () => ({ activeFarmer, setActiveFarmer, clearActiveFarmer }),
    [activeFarmer, clearActiveFarmer, setActiveFarmer]
  );

  return (
    <FarmerSessionContext.Provider value={value}>
      {children}
    </FarmerSessionContext.Provider>
  );
}

export function useFarmerSession() {
  const context = useContext(FarmerSessionContext);
  if (!context) {
    throw new Error("useFarmerSession must be used inside FarmerSessionProvider");
  }
  return context;
}

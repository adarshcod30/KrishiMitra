"use client";

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useSyncExternalStore
} from "react";

import type { FarmerSearchResult } from "@/lib/types";

interface FarmerSessionValue {
  activeFarmer: FarmerSearchResult | null;
  setActiveFarmer: (farmer: FarmerSearchResult | null) => void;
  clearActiveFarmer: () => void;
}

const STORAGE_KEY = "agrotech.activeFarmer";

const FarmerSessionContext = createContext<FarmerSessionValue | null>(null);

/**
 * The active farmer lives in localStorage, which is an external store: it is
 * read through `useSyncExternalStore` instead of being copied into state from
 * an effect.
 *
 * `getServerSnapshot` returns `null`, and React uses that same snapshot for the
 * client's hydration render, so server and client markup agree and the stored
 * farmer appears in the commit immediately after hydration. No `mounted` flag
 * is needed to avoid a mismatch.
 */
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

// `getSnapshot` must be referentially stable between reads, so the parsed
// object is cached against the raw string it was parsed from.
let cachedRaw: string | null = null;
let cachedFarmer: FarmerSearchResult | null = null;
/** Used only when localStorage is unavailable (private mode, blocked cookies). */
let memoryFarmer: FarmerSearchResult | null = null;
let storageAvailable = true;

function parseFarmer(raw: string): FarmerSearchResult | null {
  try {
    return JSON.parse(raw) as FarmerSearchResult;
  } catch {
    return null;
  }
}

function getSnapshot(): FarmerSearchResult | null {
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(STORAGE_KEY);
    storageAvailable = true;
  } catch {
    storageAvailable = false;
  }

  if (!storageAvailable) {
    return memoryFarmer;
  }

  if (raw !== cachedRaw) {
    cachedRaw = raw;
    cachedFarmer = raw ? parseFarmer(raw) : null;
  }
  return cachedFarmer;
}

function getServerSnapshot(): FarmerSearchResult | null {
  return null;
}

export function FarmerSessionProvider({ children }: { children: ReactNode }) {
  const activeFarmer = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const setActiveFarmer = useCallback((farmer: FarmerSearchResult | null) => {
    memoryFarmer = farmer;
    try {
      if (farmer) {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(farmer));
      } else {
        window.localStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      // Persistence failed; the in-memory value above still drives this tab.
    }
    emit();
  }, []);

  const clearActiveFarmer = useCallback(() => {
    setActiveFarmer(null);
  }, [setActiveFarmer]);

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

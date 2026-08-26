"use client";

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useSyncExternalStore
} from "react";

import { SUPPORTED_LANGUAGES } from "@/lib/constants";
import { translations, type TranslationKey } from "@/lib/i18n";
import type { LanguageCode } from "@/lib/types";

interface LanguageContextValue {
  language: LanguageCode;
  setLanguage: (language: LanguageCode) => void;
  t: (key: TranslationKey) => string;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

const STORAGE_KEY = "agrotech.language";
const DEFAULT_LANGUAGE: LanguageCode = "en";

/**
 * localStorage is an external store, so it is read through
 * `useSyncExternalStore` rather than copied into state from an effect.
 *
 * `getServerSnapshot` returns the default, which is also what React uses for
 * the client's hydration render — so the markup matches the server exactly and
 * the stored language is applied in the commit right after hydration. That is
 * what makes the old `mounted` flags unnecessary.
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

function isSupported(value: string | null): value is LanguageCode {
  return Boolean(value) && SUPPORTED_LANGUAGES.some((item) => item.code === value);
}

/** Used only when localStorage is unavailable (private mode, blocked cookies). */
let memoryLanguage: LanguageCode | null = null;

function getSnapshot(): LanguageCode {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (isSupported(stored)) {
      return stored;
    }
  } catch {
    // Fall through to the in-memory value.
  }
  return memoryLanguage ?? DEFAULT_LANGUAGE;
}

function getServerSnapshot(): LanguageCode {
  return DEFAULT_LANGUAGE;
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const language = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const setLanguage = useCallback((nextLanguage: LanguageCode) => {
    memoryLanguage = nextLanguage;
    try {
      window.localStorage.setItem(STORAGE_KEY, nextLanguage);
    } catch {
      // Persistence failed; the in-memory value above still drives this tab.
    }
    emit();
  }, []);

  const t = useCallback(
    (key: TranslationKey) => {
      return translations[language]?.[key] ?? translations.en[key] ?? key;
    },
    [language]
  );

  const value = useMemo(
    () => ({ language, setLanguage, t }),
    [language, setLanguage, t]
  );

  return (
    <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
  );
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error("useLanguage must be used inside LanguageProvider");
  }
  return context;
}

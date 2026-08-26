"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { toUserMessage } from "@/lib/errors";

export type AsyncStatus = "loading" | "ready" | "error";

export interface AsyncResource<T> {
  data: T | null;
  status: AsyncStatus;
  error: string | null;
  isLoading: boolean;
  /** Re-runs the loader (used by "Try again" buttons). */
  reload: () => void;
  /** Replaces the cached value without a round trip (e.g. after a mutation). */
  setData: (value: T) => void;
}

/**
 * Loads an async value and exposes explicit loading / error / ready states so
 * every page can render a real error message instead of a blank screen.
 *
 * `loader` must be stable — wrap it in `useCallback` with its own dependencies.
 * State is only ever written from the promise callbacks, never synchronously
 * inside the effect, so React never sees a cascading render.
 */
export function useAsyncResource<T>(
  loader: () => Promise<T>,
  fallbackMessage?: string
): AsyncResource<T> {
  const [reloadToken, setReloadToken] = useState(0);

  // A fresh identity per (loader, reloadToken) pair. Results carry the source
  // they came from, which lets us derive "loading" instead of setting it.
  const source = useMemo(() => ({ loader, reloadToken }), [loader, reloadToken]);

  const [result, setResult] = useState<{
    source: unknown;
    data: T | null;
    error: string | null;
  } | null>(null);

  useEffect(() => {
    let active = true;

    source
      .loader()
      .then((data) => {
        if (active) {
          setResult({ source, data, error: null });
        }
      })
      .catch((caught: unknown) => {
        if (active) {
          setResult({ source, data: null, error: toUserMessage(caught, fallbackMessage) });
        }
      });

    return () => {
      active = false;
    };
  }, [source, fallbackMessage]);

  const settled = result && result.source === source ? result : null;
  const status: AsyncStatus = settled ? (settled.error ? "error" : "ready") : "loading";

  const reload = useCallback(() => {
    setReloadToken((token) => token + 1);
  }, []);

  const setData = useCallback(
    (value: T) => {
      setResult({ source, data: value, error: null });
    },
    [source]
  );

  return {
    data: settled?.data ?? null,
    status,
    error: settled?.error ?? null,
    isLoading: status === "loading",
    reload,
    setData
  };
}

/** Returns `value` after it has stopped changing for `delayMs` milliseconds. */
export function useDebouncedValue<T>(value: T, delayMs = 350): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}

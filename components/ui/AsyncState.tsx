"use client";

import type { ReactNode } from "react";

import { Icon, ICON_NAMES, type IconName } from "@/components/ui/Icons";
import { useLanguage } from "@/contexts/LanguageContext";
import type { AsyncResource } from "@/lib/hooks";

/**
 * Older callers pass arbitrary strings (even emoji) through the `icon` prop.
 * Only known icon names from components/ui/Icons.tsx are honoured; anything
 * else falls back to the state's default icon so no emoji ever renders.
 */
function resolveIcon(icon: string | undefined, fallback: IconName): IconName {
  if (icon && (ICON_NAMES as string[]).includes(icon)) {
    return icon as IconName;
  }
  return fallback;
}

export function LoadingState({ icon, message }: { icon?: string; message?: string }) {
  const { t } = useLanguage();
  return (
    <div className="state-panel state-panel-loading" role="status" aria-live="polite">
      <div className="state-icon">
        <Icon name={resolveIcon(icon, "info")} size={34} />
      </div>
      <p className="state-message">{message ?? t("common.loading")}</p>
    </div>
  );
}

export function EmptyState({ icon, message }: { icon?: string; message: string }) {
  return (
    <div className="state-panel state-panel-empty">
      <div className="state-icon">
        <Icon name={resolveIcon(icon, "info")} size={34} />
      </div>
      <p className="state-message">{message}</p>
    </div>
  );
}

/**
 * Full-width error placeholder used when a page has nothing to show because a
 * request failed. Always renders a message plus a way to retry, so a failed
 * request can never leave a blank page behind.
 */
export function ErrorState({
  message,
  onRetry
}: {
  message: string;
  onRetry?: () => void;
}) {
  const { t } = useLanguage();
  return (
    <div className="state-panel state-panel-error" role="alert">
      <div className="state-icon">
        <Icon name="alert" size={34} />
      </div>
      <p className="state-title">{t("feedback.loadFailed")}</p>
      <p className="state-message">{message}</p>
      {onRetry ? (
        <button type="button" className="btn-secondary" onClick={onRetry}>
          {t("feedback.retry")}
        </button>
      ) : null}
    </div>
  );
}

/** Inline banner for errors raised by a user action (button click, save, ...). */
export function ErrorNotice({
  message,
  onDismiss
}: {
  message: string;
  onDismiss?: () => void;
}) {
  return (
    <div className="inline-error" role="alert">
      <span className="inline-error-icon" aria-hidden="true">
        <Icon name="alert" size={20} />
      </span>
      <span className="inline-error-text">{message}</span>
      {onDismiss ? (
        <button type="button" className="inline-error-dismiss" onClick={onDismiss} aria-label="Dismiss">
          &times;
        </button>
      ) : null}
    </div>
  );
}

interface AsyncSectionProps<T> {
  resource: AsyncResource<T>;
  icon?: string;
  loadingMessage?: string;
  emptyMessage: string;
  /** Return true when the loaded value should be treated as "no results". */
  isEmpty?: (data: T) => boolean;
  children: (data: T) => ReactNode;
}

/**
 * Renders exactly one of loading / error / empty / content for an
 * `useAsyncResource` value, so no page can silently render nothing.
 */
export function AsyncSection<T>({
  resource,
  icon,
  loadingMessage,
  emptyMessage,
  isEmpty,
  children
}: AsyncSectionProps<T>) {
  if (resource.status === "loading") {
    return <LoadingState icon={icon} message={loadingMessage} />;
  }

  if (resource.status === "error" || resource.data === null) {
    return <ErrorState message={resource.error ?? emptyMessage} onRetry={resource.reload} />;
  }

  if (isEmpty?.(resource.data)) {
    return <EmptyState icon={icon} message={emptyMessage} />;
  }

  return <>{children(resource.data)}</>;
}

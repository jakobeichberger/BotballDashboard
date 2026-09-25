import { AlertTriangle, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import clsx from "clsx";
import { formatTime } from "@/i18n/format";
import { apiErrorMessage } from "@/lib/errors";

interface FreshnessQuery {
  data: unknown;
  dataUpdatedAt: number;
  isError: boolean;
  error: unknown;
  isFetching: boolean;
  refetch: () => unknown;
}

const TIME = { hour: "2-digit", minute: "2-digit", second: "2-digit" } as const;

/**
 * How current a live list is: "Live" while the event stream is connected,
 * otherwise the time of the last successful update. A failed refresh keeps
 * the old data visible but says so ("zuletzt aktualisiert …") instead of
 * silently showing stale numbers; with no data at all it shows the error.
 */
export default function Freshness({ query, live, className }: { query: FreshnessQuery; live: boolean; className?: string }) {
  const { t } = useTranslation();
  const updated = query.dataUpdatedAt ? formatTime(query.dataUpdatedAt, TIME) : null;
  const retry = (
    <button type="button" className="btn-secondary min-h-11 text-xs" onClick={() => void query.refetch()} disabled={query.isFetching}>
      <RefreshCw className={clsx("h-3 w-3", query.isFetching && "animate-spin")} aria-hidden="true" /> {t("retry")}
    </button>
  );
  if (query.isError) {
    return (
      <div role="alert" className={clsx("flex flex-wrap items-center gap-2 rounded-lg bg-warning/[0.08] px-3 py-2 text-sm text-warning", className)}>
        <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span className="flex-1">
          {query.data && updated ? t("live.stale", { time: updated }) : t("live.loadFailed")} {apiErrorMessage(query.error)}
        </span>
        {retry}
      </div>
    );
  }
  if (!updated) return null;
  return (
    <p className={clsx("flex items-center gap-2 text-xs text-leise", className)}>
      {live && (
        <span className="inline-flex items-center gap-1 font-medium text-success">
          <span className="h-2 w-2 rounded-full bg-success" aria-hidden="true" />
          {t("live.connected")}
        </span>
      )}
      <span>{t("live.lastUpdated", { time: updated })}</span>
    </p>
  );
}

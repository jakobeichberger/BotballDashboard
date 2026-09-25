import { AlertTriangle, CloudOff, Loader2, RotateCcw, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useOfflineQueue } from "@/hooks/useOfflineQueue";
import { formatDateTime } from "@/i18n/format";
import type { QueuedScore } from "@/lib/offlineQueue";

/**
 * Score entries waiting in the offline queue, with per-entry retry/discard.
 * `filter` narrows the list to the page's scope (event, practice, …).
 */
export default function PendingScores({ filter }: { filter?: (entry: QueuedScore) => boolean }) {
  const { t } = useTranslation();
  const { entries, retry, discard } = useOfflineQueue(filter);
  if (entries.length === 0) return null;
  return (
    <section aria-labelledby="pending-scores-title" className="card border-amber-300 p-4 dark:border-amber-700">
      <h2 id="pending-scores-title" className="mb-3 flex items-center gap-2 font-semibold">
        <CloudOff className="h-4 w-4" aria-hidden="true" /> {t("pendingScores.title", { count: entries.length })}
      </h2>
      <ul className="space-y-2">
        {entries.map((entry) => {
          const failed = entry.status === "conflict" || entry.status === "error";
          return (
            <li key={entry.id} className="rounded-lg border p-3 text-sm dark:border-gray-700">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-medium">{entry.label || t("pendingScores.score")}</p>
                  <p className="text-xs text-gray-500">{formatDateTime(entry.createdAt)}</p>
                </div>
                <span className={failed ? "badge-red" : "badge-yellow"}>
                  {entry.status === "syncing" && <Loader2 className="mr-1 inline h-3 w-3 animate-spin" aria-hidden="true" />}
                  {failed && <AlertTriangle className="mr-1 inline h-3 w-3" aria-hidden="true" />}
                  {t(`pendingScores.status.${entry.status}`)}
                </span>
              </div>
              {entry.error && <p className="mt-2 text-xs text-red-700 dark:text-red-400">{entry.error}</p>}
              {failed && (
                <div className="mt-2 flex flex-wrap gap-2">
                  <button type="button" className="btn-secondary text-xs" onClick={() => void retry(entry.id)}>
                    <RotateCcw className="h-3 w-3" aria-hidden="true" /> {t("retry")}
                  </button>
                  {entry.status === "conflict" && (
                    <button type="button" className="btn-secondary text-xs" onClick={() => void retry(entry.id, true)}>
                      {t("pendingScores.saveAnyway")}
                    </button>
                  )}
                  <button type="button" className="btn-secondary text-xs text-red-600" onClick={() => { if (window.confirm(t("pendingScores.confirmDiscard"))) void discard(entry.id); }}>
                    <Trash2 className="h-3 w-3" aria-hidden="true" /> {t("pendingScores.discard")}
                  </button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

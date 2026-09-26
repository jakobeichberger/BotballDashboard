import { AlertTriangle, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import clsx from "clsx";
import { apiErrorMessage } from "@/lib/errors";

interface FailedQuery {
  isError: boolean;
  error: unknown;
  isFetching: boolean;
  refetch: () => unknown;
}

/**
 * Error state of a page whose data could not be loaded: says so, names the
 * reason and offers a retry, instead of rendering empty lists and zero KPIs
 * that look like real data. Renders nothing while every query is fine.
 */
export default function QueryErrorState({ queries, className }: { queries: FailedQuery[]; className?: string }) {
  const { t } = useTranslation();
  const failed = queries.filter((query) => query.isError);
  if (!failed.length) return null;
  const fetching = failed.some((query) => query.isFetching);
  return (
    <div role="alert" className={clsx("card flex flex-wrap items-center gap-3 p-4 text-sm text-danger", className)}>
      <AlertTriangle className="h-5 w-5 shrink-0" aria-hidden="true" />
      <span className="min-w-0 flex-1">
        {t("live.loadFailed")} {apiErrorMessage(failed[0].error)}
      </span>
      <button type="button" className="btn-secondary min-h-11" disabled={fetching} onClick={() => failed.forEach((query) => void query.refetch())}>
        <RefreshCw className={clsx("h-4 w-4", fetching && "animate-spin")} aria-hidden="true" />
        {t("retry")}
      </button>
    </div>
  );
}

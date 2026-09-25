import { useEffect, useState } from "react";
import { Clock, Lock, ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatDate, formatDateTime } from "@/i18n/format";
import { DEADLINE_TYPE_LABEL, formatCountdown, passedInternalDeadlines, type PaperDeadline } from "./paperMeta";

/**
 * The season's paper deadline with a live countdown. After the cut-off it
 * shows the locked state; organizers (papers:admin) see that they can still
 * override it.
 */
export function DeadlineBanner({ deadline }: { deadline?: PaperDeadline | null }) {
  const { t } = useTranslation("papers");
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const internal = passedInternalDeadlines(deadline);
  const internalWarning = internal.length > 0 && (
    <div role="status" className="card flex flex-wrap items-center gap-2 border-warning/45 p-3 text-sm">
      <ShieldAlert className="h-4 w-4 text-warning" aria-hidden />
      <span>
        {t("deadlineBanner.internalPassed")}{" "}
        {internal
          .map((d) => `${d.label || DEADLINE_TYPE_LABEL[d.deadline_type] || d.deadline_type} (${formatDate(d.due_date)})`)
          .join(", ")}
        {t("deadlineBanner.uploadStillPossible")}
      </span>
    </div>
  );

  if (!deadline?.cutoff_at) return internalWarning || null;
  const cutoff = new Date(deadline.cutoff_at);
  const when = formatDateTime(cutoff, { dateStyle: "medium", timeStyle: "short" });
  const remaining = formatCountdown(cutoff, now);

  if (remaining) {
    return (
      <>
      {internalWarning}
      <div role="status" className="card flex flex-wrap items-center gap-2 border-info/40 p-3 text-sm">
        <Clock className="h-4 w-4 text-info" aria-hidden />
        <span>
          {t("deadlineBanner.deadline")} <time dateTime={deadline.cutoff_at} className="font-medium">{when}</time>
          <span className="text-leise"> ({deadline.timezone})</span>
        </span>
        <span className="badge-blue ml-auto">{t("deadlineBanner.remaining", { remaining })}</span>
      </div>
      </>
    );
  }
  return (
    <div role="status" className="card flex flex-wrap items-center gap-2 border-danger/40 p-3 text-sm">
      {deadline.can_override ? (
        <ShieldAlert className="h-4 w-4 text-warning" aria-hidden />
      ) : (
        <Lock className="h-4 w-4 text-danger" aria-hidden />
      )}
      <span>
        {t("deadlineBanner.passedAt")} <time dateTime={deadline.cutoff_at} className="font-medium">{when}</time>.{" "}
        {deadline.can_override
          ? t("deadlineBanner.canOverride")
          : t("deadlineBanner.locked")}
      </span>
      <span className={deadline.can_override ? "badge-yellow ml-auto" : "badge-red ml-auto"}>
        {deadline.can_override ? t("deadlineBanner.override") : t("deadlineBanner.lockedBadge")}
      </span>
    </div>
  );
}

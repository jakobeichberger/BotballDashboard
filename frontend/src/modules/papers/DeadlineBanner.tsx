import { useEffect, useState } from "react";
import { Clock, Lock, ShieldAlert } from "lucide-react";
import { formatCountdown, type PaperDeadline } from "./paperMeta";

/**
 * The season's paper deadline with a live countdown. After the cut-off it
 * shows the locked state; organizers (papers:admin) see that they can still
 * override it.
 */
export function DeadlineBanner({ deadline }: { deadline?: PaperDeadline | null }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  if (!deadline?.cutoff_at) return null;
  const cutoff = new Date(deadline.cutoff_at);
  const when = cutoff.toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" });
  const remaining = formatCountdown(cutoff, now);

  if (remaining) {
    return (
      <div role="status" className="card flex flex-wrap items-center gap-2 border-blue-200 p-3 text-sm dark:border-blue-900">
        <Clock className="h-4 w-4 text-blue-600" aria-hidden />
        <span>
          Einreichungsfrist: <time dateTime={deadline.cutoff_at} className="font-medium">{when}</time>
          <span className="text-gray-500"> ({deadline.timezone})</span>
        </span>
        <span className="badge-blue ml-auto">noch {remaining}</span>
      </div>
    );
  }
  return (
    <div role="status" className="card flex flex-wrap items-center gap-2 border-red-200 p-3 text-sm dark:border-red-900">
      {deadline.can_override ? (
        <ShieldAlert className="h-4 w-4 text-yellow-600" aria-hidden />
      ) : (
        <Lock className="h-4 w-4 text-red-600" aria-hidden />
      )}
      <span>
        Einreichungsfrist abgelaufen am <time dateTime={deadline.cutoff_at} className="font-medium">{when}</time>.{" "}
        {deadline.can_override
          ? "Als Organisator kannst du trotzdem hochladen und einreichen."
          : "Hochladen und Einreichen sind gesperrt."}
      </span>
      <span className={deadline.can_override ? "badge-yellow ml-auto" : "badge-red ml-auto"}>
        {deadline.can_override ? "Admin-Override" : "Gesperrt"}
      </span>
    </div>
  );
}

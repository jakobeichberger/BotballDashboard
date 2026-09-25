import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ChevronLeft, ChevronRight, Copy, Download, Link2, RefreshCw, Trash2 } from "lucide-react";
import clsx from "clsx";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { formatDate, formatDateTime } from "@/i18n/format";
import { daysUntil, type CalendarFeedStatus, type DeadlineEntry, type SeasonTimeline } from "@/api/analytics";
import { DEADLINE_DOT } from "./chartTheme";
import { toast } from "@/lib/toast";

const KINDS = ["paper", "review", "printing", "registration", "competition", "event", "phase", "deadline", "milestone"];
const WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

function fmtDay(iso: string) {
  return formatDate(iso.length === 10 ? iso : new Date(iso), { weekday: "short", day: "2-digit", month: "2-digit", year: "numeric" });
}

/** "in 3 Tagen", "heute", "vor 2 Tagen" – the reminder badge of the spec. */
export function RelativeBadge({ entry, now }: { entry: DeadlineEntry; now?: Date }) {
  const { t } = useTranslation("analytics");
  const end = entry.end ?? entry.start;
  const toStart = daysUntil(entry.start, now);
  const toEnd = daysUntil(end, now);
  if (entry.done) return <span className="badge-green text-xs">{t("deadlines.done")}</span>;
  if (toEnd < 0) return <span className="badge-gray text-xs">{t("deadlines.past")}</span>;
  if (toStart <= 0) return <span className="badge-red text-xs">{toStart === 0 ? t("deadlines.today") : t("deadlines.running")}</span>;
  const cls = toStart <= 3 ? "badge-red" : toStart <= 14 ? "badge-yellow" : "badge-blue";
  return <span className={clsx(cls, "text-xs")}>{toStart === 1 ? t("deadlines.tomorrow") : t("deadlines.inDays", { count: toStart })}</span>;
}

/** Chronological deadline list; past entries are greyed out. */
export function DeadlineList({ entries, showSeason = false, now }: { entries: DeadlineEntry[]; showSeason?: boolean; now?: Date }) {
  const { t } = useTranslation("analytics");
  if (!entries.length) return <p className="text-sm text-leise">{t("deadlines.none")}</p>;
  return (
    <ul className="space-y-2" aria-label={t("deadlines.label")}>
      {entries.map((e) => {
        const past = daysUntil(e.end ?? e.start, now) < 0;
        return (
          <li key={e.id} className={clsx("flex items-center gap-3 rounded-lg p-2.5 bg-flaeche-2", past && "opacity-60")}>
            <span className={clsx("h-2.5 w-2.5 shrink-0 rounded-full", DEADLINE_DOT[e.color] ?? "bg-gray-400")} aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className={clsx("truncate text-sm font-medium text-fg", past && "line-through")}>
                {e.title}
                {e.done && <CheckCircle2 className="ml-1 inline h-3.5 w-3.5 text-success" aria-label={t("deadlines.done")} />}
              </p>
              <p className="text-xs text-leise">
                <time dateTime={e.start}>{fmtDay(e.start)}</time>
                {e.end && e.end.slice(0, 10) !== e.start.slice(0, 10) && <> – <time dateTime={e.end}>{fmtDay(e.end)}</time></>}
                {" · "}{KINDS.includes(e.kind) ? t(`deadlines.kind.${e.kind}`) : e.kind}
                {showSeason && ` · ${e.season_name}`}
              </p>
            </div>
            <RelativeBadge entry={e} now={now} />
          </li>
        );
      })}
    </ul>
  );
}

function dayKey(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function entryDays(e: DeadlineEntry): string[] {
  const start = new Date(e.start.length === 10 ? `${e.start}T00:00:00` : e.start);
  const endIso = e.end ?? e.start;
  const end = new Date(endIso.length === 10 ? `${endIso}T00:00:00` : endIso);
  const days: string[] = [];
  const cursor = new Date(start.getFullYear(), start.getMonth(), start.getDate());
  // Guard against absurd ranges (a season-long entry would fill the month).
  for (let i = 0; cursor <= end && i < 62; i++) {
    days.push(dayKey(cursor));
    cursor.setDate(cursor.getDate() + 1);
  }
  return days.length ? days : [dayKey(start)];
}

/** Month grid with coloured deadline chips (Monday first). */
export function MonthCalendar({ entries, initial }: { entries: DeadlineEntry[]; initial?: Date }) {
  const { t } = useTranslation("analytics");
  const [month, setMonth] = useState(() => {
    const d = initial ?? new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1);
  });
  const byDay = useMemo(() => {
    const map: Record<string, DeadlineEntry[]> = {};
    entries.forEach((e) => entryDays(e).forEach((k) => (map[k] ??= []).push(e)));
    return map;
  }, [entries]);
  const offset = (month.getDay() + 6) % 7;
  const daysInMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const cells: Array<Date | null> = [
    ...Array.from({ length: offset }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => new Date(month.getFullYear(), month.getMonth(), i + 1)),
  ];
  while (cells.length % 7) cells.push(null);
  const today = dayKey(new Date());
  const title = formatDate(month, { month: "long", year: "numeric" });

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <button type="button" className="btn-secondary p-1.5" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))} aria-label={t("calendar.previousMonth")}>
          <ChevronLeft className="h-4 w-4" />
        </button>
        <h3 className="font-semibold text-fg" aria-live="polite">{title}</h3>
        <button type="button" className="btn-secondary p-1.5" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))} aria-label={t("calendar.nextMonth")}>
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
      <div className="grid grid-cols-7 gap-px overflow-hidden rounded-lg border bg-gray-200 text-xs dark:bg-gray-700" role="grid" aria-label={title}>
        {WEEKDAYS.map((d) => (
          <div key={d} role="columnheader" className="bg-flaeche-2 py-1 text-center font-medium text-leise">{t(`calendar.weekday.${d}`)}</div>
        ))}
        {cells.map((cell, i) => {
          const key = cell ? dayKey(cell) : `empty-${i}`;
          const items = cell ? byDay[key] ?? [] : [];
          return (
            <div key={key} role="gridcell" className={clsx("min-h-[4.5rem] bg-flaeche p-1", !cell && "bg-flaeche-2")}>
              {cell && (
                <>
                  <span className={clsx("inline-block rounded px-1 tabular-nums", key === today ? "bg-primary text-white" : "text-leise")}>{cell.getDate()}</span>
                  <ul className="mt-0.5 space-y-0.5">
                    {items.slice(0, 3).map((e) => (
                      <li key={e.id} className="flex items-center gap-1 truncate" title={e.title}>
                        <span className={clsx("h-1.5 w-1.5 shrink-0 rounded-full", DEADLINE_DOT[e.color] ?? "bg-gray-400")} aria-hidden="true" />
                        <span className={clsx("truncate", daysUntil(e.end ?? e.start) < 0 ? "text-leise" : "text-fg")}>{e.title}</span>
                      </li>
                    ))}
                    {items.length > 3 && <li className="text-leise">+{items.length - 3}</li>}
                  </ul>
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

const STATUS_STYLE: Record<string, string> = {
  planned: "border-rand-stark/70 bg-flaeche text-fg",
  active: "border-success bg-success/[0.07] text-success ring-2 ring-success/30",
  finished: "border-rand bg-flaeche-2 text-leise",
};
const TIMELINE_STATUSES = ["planned", "active", "finished"];

function fmtRange(start: string | null, end: string | null, noDate: string) {
  if (!start) return noDate;
  const s = formatDate(start);
  const e = end ? formatDate(end) : null;
  return e && e !== s ? `${s} – ${e}` : s;
}

/** Horizontal season process timeline: events in order, phases below. */
export function SeasonTimelineView({ timeline }: { timeline?: SeasonTimeline }) {
  const { t } = useTranslation("analytics");
  const statusLabel = (status: string) => (TIMELINE_STATUSES.includes(status) ? t(`timeline.status.${status}`) : status);
  if (!timeline) return null;
  if (!timeline.events.length) return <p className="text-sm text-leise">{t("timeline.noEvents")}</p>;
  return (
    <ol className="flex gap-3 overflow-x-auto pb-2" aria-label={t("timeline.label", { season: timeline.season_name })}>
      {timeline.events.map((e, index) => (
        <li key={e.id} className="flex min-w-[13rem] flex-1 items-stretch gap-3">
          <div className={clsx("flex-1 rounded-lg border p-3", STATUS_STYLE[e.status] ?? STATUS_STYLE.planned)}>
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 font-medium">
                <span className={clsx("h-2 w-2 rounded-full", DEADLINE_DOT[e.color] ?? "bg-primary")} aria-hidden="true" />
                {e.name}
              </span>
              <span className="text-xs">{statusLabel(e.status)}</span>
            </div>
            <p className="mt-0.5 text-xs">{fmtRange(e.starts_at, e.ends_at, t("timeline.noDate"))}</p>
            {e.phases.length > 0 && (
              <ul className="mt-2 space-y-1">
                {e.phases.map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-2 text-xs">
                    <span className={clsx(p.status === "active" && "font-semibold")}>{p.name}</span>
                    <span className="italic">{statusLabel(p.status)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {index < timeline.events.length - 1 && <span className="self-center text-gray-300" aria-hidden="true">→</span>}
        </li>
      ))}
    </ol>
  );
}

/**
 * Personal iCal subscription. The feed URL carries a secret token that is only
 * shown right after creating it; rotating invalidates older URLs.
 */
export function CalendarFeedPanel() {
  const { t } = useTranslation("analytics");
  const qc = useQueryClient();
  const [url, setUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const { data: status } = useQuery<CalendarFeedStatus>({
    queryKey: ["dashboard", "calendar-feed"],
    queryFn: async () => (await api.get("/dashboard/calendar-feed")).data,
  });
  const create = useMutation({
    mutationFn: async () => (await api.post("/dashboard/calendar-feed")).data as { token: string; path: string },
    onSuccess: (data) => {
      setUrl(`${window.location.origin}${data.path}`);
      setCopied(false);
      qc.invalidateQueries({ queryKey: ["dashboard", "calendar-feed"] });
    },
  });
  const revoke = useMutation({
    mutationFn: () => api.delete("/dashboard/calendar-feed"),
    onSuccess: () => {
      setUrl(null);
      qc.invalidateQueries({ queryKey: ["dashboard", "calendar-feed"] });
    },
  });
  const download = async () => {
    const response = await api.get("/dashboard/deadlines.ics", { responseType: "blob" });
    const href = URL.createObjectURL(new Blob([response.data], { type: "text/calendar" }));
    const a = document.createElement("a");
    a.href = href;
    a.download = "botball-deadlines.ics";
    a.click();
    URL.revokeObjectURL(href);
  };

  return (
    <div className="space-y-3 text-sm">
      <p className="text-leise">
        {t("feed.intro")}
      </p>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn-secondary text-sm" onClick={download}>
          <Download className="h-4 w-4" /> {t("feed.download")}
        </button>
        <button type="button" className="btn-primary text-sm" onClick={() => create.mutate()} disabled={create.isPending}>
          {status?.active ? <RefreshCw className="h-4 w-4" /> : <Link2 className="h-4 w-4" />}
          {status?.active ? t("feed.rotate") : t("feed.create")}
        </button>
        {status?.active && (
          <button type="button" className="btn-danger text-sm" onClick={() => revoke.mutate()} disabled={revoke.isPending}>
            <Trash2 className="h-4 w-4" /> {t("feed.revoke")}
          </button>
        )}
      </div>
      {status?.active && !url && (
        <p className="text-xs text-leise">
          {t("feed.activeSince", { date: formatDate(status.created_at) })}
          {status.last_used_at && t("feed.lastUsed", { date: formatDateTime(status.last_used_at) })}
          {t("feed.shownOnce")}
        </p>
      )}
      {url && (
        <div className="flex items-center gap-2">
          <label htmlFor="ical-url" className="sr-only">{t("feed.address")}</label>
          <input id="ical-url" readOnly value={url} className="input font-mono text-xs" onFocus={(e) => e.currentTarget.select()} />
          <button
            type="button"
            className="btn-secondary text-sm"
            onClick={async () => {
              // Clipboard access can be missing (http, old browsers) or denied:
              // select the address instead so it can be copied by hand.
              try {
                if (!navigator.clipboard) throw new Error("clipboard unavailable");
                await navigator.clipboard.writeText(url);
                setCopied(true);
              } catch {
                setCopied(false);
                (document.getElementById("ical-url") as HTMLInputElement | null)?.select();
                toast.error(t("common:copyFailed"));
              }
            }}
          >
            <Copy className="h-4 w-4" aria-hidden="true" /> {copied ? t("feed.copied") : t("feed.copy")}
          </button>
        </div>
      )}
    </div>
  );
}

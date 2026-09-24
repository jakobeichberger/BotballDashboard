import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ChevronLeft, ChevronRight, Copy, Download, Link2, RefreshCw, Trash2 } from "lucide-react";
import clsx from "clsx";
import { api } from "@/lib/api";
import { daysUntil, type CalendarFeedStatus, type DeadlineEntry, type SeasonTimeline } from "@/api/analytics";
import { DEADLINE_DOT } from "./chartTheme";

const KIND_LABELS: Record<string, string> = {
  paper: "Paper",
  review: "Review",
  printing: "3D-Druck",
  registration: "Anmeldung",
  competition: "Wettbewerb",
  event: "Event",
  phase: "Phase",
  deadline: "Deadline",
  milestone: "Termin",
};

function fmtDay(iso: string) {
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  return d.toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit", year: "numeric" });
}

/** "in 3 Tagen", "heute", "vor 2 Tagen" – the reminder badge of the spec. */
export function RelativeBadge({ entry, now }: { entry: DeadlineEntry; now?: Date }) {
  const end = entry.end ?? entry.start;
  const toStart = daysUntil(entry.start, now);
  const toEnd = daysUntil(end, now);
  if (entry.done) return <span className="badge-green text-xs">erledigt</span>;
  if (toEnd < 0) return <span className="badge-gray text-xs">vorbei</span>;
  if (toStart <= 0) return <span className="badge-red text-xs">{toStart === 0 ? "heute" : "läuft"}</span>;
  const cls = toStart <= 3 ? "badge-red" : toStart <= 14 ? "badge-yellow" : "badge-blue";
  return <span className={clsx(cls, "text-xs")}>{toStart === 1 ? "morgen" : `in ${toStart} Tagen`}</span>;
}

/** Chronological deadline list; past entries are greyed out. */
export function DeadlineList({ entries, showSeason = false, now }: { entries: DeadlineEntry[]; showSeason?: boolean; now?: Date }) {
  if (!entries.length) return <p className="text-sm text-gray-500">Keine anstehenden Deadlines.</p>;
  return (
    <ul className="space-y-2" aria-label="Deadlines">
      {entries.map((e) => {
        const past = daysUntil(e.end ?? e.start, now) < 0;
        return (
          <li key={e.id} className={clsx("flex items-center gap-3 rounded-lg p-2.5 bg-gray-50 dark:bg-gray-800", past && "opacity-60")}>
            <span className={clsx("h-2.5 w-2.5 shrink-0 rounded-full", DEADLINE_DOT[e.color] ?? "bg-gray-400")} aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className={clsx("truncate text-sm font-medium text-gray-900 dark:text-white", past && "line-through")}>
                {e.title}
                {e.done && <CheckCircle2 className="ml-1 inline h-3.5 w-3.5 text-green-600" aria-label="erledigt" />}
              </p>
              <p className="text-xs text-gray-500">
                <time dateTime={e.start}>{fmtDay(e.start)}</time>
                {e.end && e.end.slice(0, 10) !== e.start.slice(0, 10) && <> – <time dateTime={e.end}>{fmtDay(e.end)}</time></>}
                {" · "}{KIND_LABELS[e.kind] ?? e.kind}
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
  const title = month.toLocaleDateString("de-DE", { month: "long", year: "numeric" });

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <button type="button" className="btn-secondary p-1.5" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))} aria-label="Vorheriger Monat">
          <ChevronLeft className="h-4 w-4" />
        </button>
        <h3 className="font-semibold text-gray-900 dark:text-white" aria-live="polite">{title}</h3>
        <button type="button" className="btn-secondary p-1.5" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))} aria-label="Nächster Monat">
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
      <div className="grid grid-cols-7 gap-px overflow-hidden rounded-lg border bg-gray-200 text-xs dark:border-gray-700 dark:bg-gray-700" role="grid" aria-label={title}>
        {["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"].map((d) => (
          <div key={d} role="columnheader" className="bg-gray-50 py-1 text-center font-medium text-gray-500 dark:bg-gray-800">{d}</div>
        ))}
        {cells.map((cell, i) => {
          const key = cell ? dayKey(cell) : `empty-${i}`;
          const items = cell ? byDay[key] ?? [] : [];
          return (
            <div key={key} role="gridcell" className={clsx("min-h-[4.5rem] bg-white p-1 dark:bg-gray-900", !cell && "bg-gray-50 dark:bg-gray-900/40")}>
              {cell && (
                <>
                  <span className={clsx("inline-block rounded px-1 tabular-nums", key === today ? "bg-primary-600 text-white" : "text-gray-500")}>{cell.getDate()}</span>
                  <ul className="mt-0.5 space-y-0.5">
                    {items.slice(0, 3).map((e) => (
                      <li key={e.id} className="flex items-center gap-1 truncate" title={e.title}>
                        <span className={clsx("h-1.5 w-1.5 shrink-0 rounded-full", DEADLINE_DOT[e.color] ?? "bg-gray-400")} aria-hidden="true" />
                        <span className={clsx("truncate", daysUntil(e.end ?? e.start) < 0 ? "text-gray-400" : "text-gray-800 dark:text-gray-200")}>{e.title}</span>
                      </li>
                    ))}
                    {items.length > 3 && <li className="text-gray-400">+{items.length - 3}</li>}
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
  planned: "border-gray-300 bg-white text-gray-700 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-300",
  active: "border-green-500 bg-green-50 text-green-800 ring-2 ring-green-500/30 dark:bg-green-900/30 dark:text-green-200",
  finished: "border-gray-200 bg-gray-100 text-gray-500 dark:border-gray-700 dark:bg-gray-800",
};
const STATUS_LABEL: Record<string, string> = { planned: "geplant", active: "aktiv", finished: "abgeschlossen" };

function fmtRange(start: string | null, end: string | null) {
  if (!start) return "ohne Termin";
  const s = new Date(start).toLocaleDateString("de-DE");
  const e = end ? new Date(end).toLocaleDateString("de-DE") : null;
  return e && e !== s ? `${s} – ${e}` : s;
}

/** Horizontal season process timeline: events in order, phases below. */
export function SeasonTimelineView({ timeline }: { timeline?: SeasonTimeline }) {
  if (!timeline) return null;
  if (!timeline.events.length) return <p className="text-sm text-gray-500">Für diese Saison sind noch keine Events angelegt.</p>;
  return (
    <ol className="flex gap-3 overflow-x-auto pb-2" aria-label={`Ablauf ${timeline.season_name}`}>
      {timeline.events.map((e, index) => (
        <li key={e.id} className="flex min-w-[13rem] flex-1 items-stretch gap-3">
          <div className={clsx("flex-1 rounded-lg border p-3", STATUS_STYLE[e.status] ?? STATUS_STYLE.planned)}>
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 font-medium">
                <span className={clsx("h-2 w-2 rounded-full", DEADLINE_DOT[e.color] ?? "bg-blue-600")} aria-hidden="true" />
                {e.name}
              </span>
              <span className="text-xs">{STATUS_LABEL[e.status] ?? e.status}</span>
            </div>
            <p className="mt-0.5 text-xs opacity-80">{fmtRange(e.starts_at, e.ends_at)}</p>
            {e.phases.length > 0 && (
              <ul className="mt-2 space-y-1">
                {e.phases.map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-2 text-xs">
                    <span className={clsx(p.status === "active" && "font-semibold")}>{p.name}</span>
                    <span className="opacity-70">{STATUS_LABEL[p.status] ?? p.status}</span>
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
      <p className="text-gray-600 dark:text-gray-400">
        Abonniere deine Deadlines in Outlook, Google oder Apple Kalender. Die Adresse ist persönlich – wer sie kennt, sieht deine Termine.
      </p>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn-secondary text-sm" onClick={download}>
          <Download className="h-4 w-4" /> .ics herunterladen
        </button>
        <button type="button" className="btn-primary text-sm" onClick={() => create.mutate()} disabled={create.isPending}>
          {status?.active ? <RefreshCw className="h-4 w-4" /> : <Link2 className="h-4 w-4" />}
          {status?.active ? "Neue Abo-Adresse erzeugen" : "Abo-Adresse erzeugen"}
        </button>
        {status?.active && (
          <button type="button" className="btn-danger text-sm" onClick={() => revoke.mutate()} disabled={revoke.isPending}>
            <Trash2 className="h-4 w-4" /> Abo widerrufen
          </button>
        )}
      </div>
      {status?.active && !url && (
        <p className="text-xs text-gray-500">
          Abo aktiv seit {status.created_at ? new Date(status.created_at).toLocaleDateString("de-DE") : "—"}
          {status.last_used_at && `, zuletzt abgerufen ${new Date(status.last_used_at).toLocaleString("de-DE")}`}. Die Adresse wird aus Sicherheitsgründen nur einmal angezeigt.
        </p>
      )}
      {url && (
        <div className="flex items-center gap-2">
          <label htmlFor="ical-url" className="sr-only">Abo-Adresse</label>
          <input id="ical-url" readOnly value={url} className="input font-mono text-xs" onFocus={(e) => e.currentTarget.select()} />
          <button
            type="button"
            className="btn-secondary text-sm"
            onClick={async () => {
              await navigator.clipboard?.writeText(url);
              setCopied(true);
            }}
          >
            <Copy className="h-4 w-4" /> {copied ? "Kopiert" : "Kopieren"}
          </button>
        </div>
      )}
    </div>
  );
}

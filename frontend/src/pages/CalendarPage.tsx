import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { CalendarClock, CalendarDays, List } from "lucide-react";
import clsx from "clsx";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { useEvent } from "@/hooks/useEvents";
import { useDeadlines, useSeasonTimeline } from "@/api/analytics";
import { CalendarFeedPanel, DeadlineList, MonthCalendar, SeasonTimelineView } from "@/components/analytics/Deadlines";
import { DEADLINE_DOT } from "@/components/analytics/chartTheme";

const LEGEND = ["red", "orange", "blue", "purple", "green", "gray"];

/** Deadline calendar (list + month) and season process timeline. */
export default function CalendarPage() {
  const { t } = useTranslation("analytics");
  const { eventId = "" } = useParams();
  const { data: event } = useEvent(eventId);
  const { data: seasons } = useQuery<Array<{ id: string; name: string; year: number }>>({
    queryKey: ["seasons"],
    queryFn: async () => (await api.get("/seasons")).data,
  });
  // "" = every season that concerns me (active + my teams' seasons).
  const [seasonId, setSeasonId] = useState<string>("");
  useEffect(() => {
    if (event?.season_id) setSeasonId((current) => current || event.season_id);
  }, [event?.season_id]);
  const [view, setView] = useState<"list" | "month">("list");
  const { data: deadlines, isLoading } = useDeadlines(seasonId || undefined);
  const { data: timeline } = useSeasonTimeline(seasonId || undefined);
  const [showPast, setShowPast] = useState(false);

  const today = new Date().toISOString().slice(0, 10);
  const visible = (deadlines ?? []).filter((d) => showPast || (d.end ?? d.start).slice(0, 10) >= today);

  return (
    <div className="p-6 space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <CalendarClock className="w-6 h-6" /> {t("calendarPage.title")}
        </h1>
        <div className="flex items-center gap-2">
          <label htmlFor="calendar-season" className="text-sm text-gray-600 dark:text-gray-400">{t("calendarPage.season")}</label>
          <select id="calendar-season" className="input w-auto" value={seasonId} onChange={(e) => setSeasonId(e.target.value)}>
            <option value="">{t("calendarPage.allRelevant")}</option>
            {seasons?.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.year})</option>)}
          </select>
        </div>
      </div>

      {timeline && (
        <section className="card p-6" aria-labelledby="timeline-heading">
          <h2 id="timeline-heading" className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">{t("calendarPage.timeline", { season: timeline.season_name })}</h2>
          <SeasonTimelineView timeline={timeline} />
        </section>
      )}

      <section className="card p-6" aria-labelledby="deadlines-heading">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 id="deadlines-heading" className="text-lg font-semibold text-gray-900 dark:text-white">{t("calendarPage.deadlineCalendar")}</h2>
          <div className="flex items-center gap-3">
            {view === "list" && (
              <label className="flex items-center gap-1.5 text-sm text-gray-600 dark:text-gray-400">
                <input type="checkbox" checked={showPast} onChange={(e) => setShowPast(e.target.checked)} /> {t("calendarPage.showPast")}
              </label>
            )}
            <div className="inline-flex overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700" role="group" aria-label={t("calendarPage.view")}>
              {([["list", t("calendarPage.list"), List], ["month", t("calendarPage.month"), CalendarDays]] as const).map(([id, label, Icon]) => (
                <button
                  key={id}
                  type="button"
                  aria-pressed={view === id}
                  onClick={() => setView(id)}
                  className={clsx("flex items-center gap-1.5 px-3 py-1.5 text-sm", view === id ? "bg-primary-600 text-white" : "text-gray-600 dark:text-gray-300")}
                >
                  <Icon className="h-4 w-4" aria-hidden="true" /> {label}
                </button>
              ))}
            </div>
          </div>
        </div>
        <ul className="mb-4 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600 dark:text-gray-400" aria-label={t("calendarPage.legend")}>
          {LEGEND.map((color) => (
            <li key={color} className="flex items-center gap-1.5"><span className={clsx("h-2 w-2 rounded-full", DEADLINE_DOT[color])} aria-hidden="true" />{t(`calendarPage.legendItem.${color}`)}</li>
          ))}
        </ul>
        {isLoading && <p className="text-sm text-gray-500">{t("common:loadingEllipsis")}</p>}
        {!isLoading && view === "list" && <DeadlineList entries={visible} showSeason={!seasonId} />}
        {!isLoading && view === "month" && <MonthCalendar entries={deadlines ?? []} />}
      </section>

      <section className="card p-6" aria-labelledby="ical-heading">
        <h2 id="ical-heading" className="mb-3 text-lg font-semibold text-gray-900 dark:text-white">{t("calendarPage.ical")}</h2>
        <CalendarFeedPanel />
      </section>
    </div>
  );
}

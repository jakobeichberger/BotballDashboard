import { useMemo } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { History } from "lucide-react";
import { useTranslation } from "react-i18next";
import { EventLink } from "@/components/EventLink";
import { fmtNum, type TeamHistoryRow } from "@/api/analytics";
import { AXIS_TICK, GRID, SERIES } from "./chartTheme";

function label(row: TeamHistoryRow) {
  return `${row.season_year} · ${row.event_name}`;
}

/**
 * Multi-year view of a team: seeding and overall score per event, the ranks
 * in a second chart (scores and ranks have different scales, so they never
 * share an axis), and the table the charts are drawn from.
 */
export default function TeamHistoryPanel({ rows, isLoading }: { rows?: TeamHistoryRow[]; isLoading?: boolean }) {
  const { t } = useTranslation("analytics");
  const data = useMemo(
    () =>
      (rows ?? []).map((r) => ({
        name: label(r),
        seeding: r.seeding_score,
        seedingRank: r.seeding_rank,
        overallRank: r.overall_rank,
      })),
    [rows],
  );
  const showPractice = (rows ?? []).some((r) => r.practice_runs != null);
  const maxRank = Math.max(2, ...(rows ?? []).map((r) => Math.max(r.seeding_teams, r.overall_teams)));

  return (
    <section className="card overflow-hidden" aria-labelledby="team-history-heading">
      <h2 id="team-history-heading" className="px-4 py-3 border-b font-semibold text-gray-900 dark:text-white flex items-center gap-2">
        <History className="w-4 h-4" aria-hidden="true" /> {t("history.title", { count: rows?.length ?? 0 })}
      </h2>
      {isLoading && <p className="p-4 text-sm text-gray-500">{t("common:loadingEllipsis")}</p>}
      {!isLoading && (!rows || rows.length === 0) && (
        <p className="px-4 py-8 text-center text-gray-400">{t("history.empty")}</p>
      )}
      {rows && rows.length > 0 && (
        <>
          {rows.length > 1 && (
            <div className="grid gap-4 p-4 lg:grid-cols-2">
              <figure>
                <figcaption className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">{t("history.scoreChart")}</figcaption>
                <div className="h-56" data-testid="history-score-chart">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                      <CartesianGrid stroke={GRID} vertical={false} />
                      <XAxis dataKey="name" tick={AXIS_TICK} interval="preserveStartEnd" />
                      <YAxis tick={AXIS_TICK} width={40} />
                      <Tooltip />
                      <Line type="monotone" dataKey="seeding" name={t("history.seedingScore")} stroke={SERIES.primary} strokeWidth={2} dot={{ r: 4 }} connectNulls />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </figure>
              <figure>
                <figcaption className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">{t("history.rankChart")}</figcaption>
                <div className="h-56" data-testid="history-rank-chart">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                      <CartesianGrid stroke={GRID} vertical={false} />
                      <XAxis dataKey="name" tick={AXIS_TICK} interval="preserveStartEnd" />
                      <YAxis reversed allowDecimals={false} domain={[1, maxRank]} tick={AXIS_TICK} width={32} />
                      <Tooltip />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      <Line type="monotone" dataKey="seedingRank" name={t("history.seedingRank")} stroke={SERIES.primary} strokeWidth={2} dot={{ r: 4 }} connectNulls />
                      <Line type="monotone" dataKey="overallRank" name={t("history.overallRank")} stroke={SERIES.secondary} strokeWidth={2} strokeDasharray="5 3" dot={{ r: 4 }} connectNulls />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </figure>
            </div>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">{t("history.caption")}</caption>
              <thead className="bg-gray-50 dark:bg-gray-800">
                <tr>
                  {[
                    t("history.col.season"),
                    t("history.col.event"),
                    t("history.col.seeding"),
                    t("history.col.seedScore"),
                    t("history.col.overall"),
                    t("history.col.overallScore"),
                    t("history.col.runs"),
                    t("history.col.bestRun"),
                    ...(showPractice ? [t("history.col.practiceAvg")] : []),
                  ].map((h) => (
                    <th key={h} scope="col" className="px-4 py-2 text-left font-medium text-gray-600 dark:text-gray-400">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y dark:divide-gray-800">
                {rows.map((r) => (
                  <tr key={`${r.event_id}-${r.team_id}`}>
                    <td className="px-4 py-2 tabular-nums">{r.season_year}</td>
                    <td className="px-4 py-2">
                      <EventLink to={`/events/${r.event_id}/dashboard`} className="text-primary-600 dark:text-primary-400 hover:underline">{r.event_name}</EventLink>
                    </td>
                    <td className="px-4 py-2 tabular-nums">{r.seeding_rank ? `${r.seeding_rank}/${r.seeding_teams}` : "—"}</td>
                    <td className="px-4 py-2 tabular-nums">{fmtNum(r.seeding_score)}</td>
                    <td className="px-4 py-2 tabular-nums">{r.overall_rank ? `${r.overall_rank}/${r.overall_teams}` : "—"}</td>
                    <td className="px-4 py-2 tabular-nums">{fmtNum(r.overall_score, 3)}</td>
                    <td className="px-4 py-2 tabular-nums">{r.official_runs}</td>
                    <td className="px-4 py-2 tabular-nums">{fmtNum(r.best_score)}</td>
                    {showPractice && (
                      <td className="px-4 py-2 tabular-nums">{r.practice_runs ? `${fmtNum(r.practice_avg)} (${r.practice_runs})` : "—"}</td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

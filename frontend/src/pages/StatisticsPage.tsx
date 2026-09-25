import { useState } from "react";
import { useParams } from "react-router-dom";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AlertTriangle, BarChart3, CheckCircle2, ClipboardCheck, ListChecks, Users } from "lucide-react";
import clsx from "clsx";
import { useTranslation } from "react-i18next";
import { fmtNum, useEventStatistics, type Anomaly, type EventStatistics } from "@/api/analytics";
import { BoxPlotList } from "@/components/analytics/BoxPlot";
import MatchReviewModal from "@/components/analytics/MatchReviewModal";
import EventAuditTrail from "@/components/analytics/EventAuditTrail";
import { AXIS_TICK, GRID, SERIES, heatColor, heatTextClass } from "@/components/analytics/chartTheme";
import { ExportButton } from "@/components/ExportButtons";
import { StatGrid, SectionCard } from "./dashboard/widgets";
import { labelMap } from "@/i18n/labels";

const REASON_LABELS = labelMap("analytics:reason", ["out_of_range", "invalid_value", "total_mismatch", "team_outlier", "field_outlier", "jump"]);

export function Heatmap({ heatmap }: { heatmap: EventStatistics["heatmap"] }) {
  const { t } = useTranslation("analytics");
  if (!heatmap.teams.length || !heatmap.fields.length) return <p className="text-sm text-leise">{t("noData")}</p>;
  return (
    <div className="overflow-x-auto">
      <table className="text-sm">
        <caption className="sr-only">{t("heatmap.caption")}</caption>
        <thead>
          <tr>
            <th scope="col" className="px-2 py-1 text-left font-semibold">{t("history.col.team")}</th>
            {heatmap.fields.map((f) => <th key={f.key} scope="col" className="px-2 py-1 text-center font-semibold">{f.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {heatmap.teams.map((team) => (
            <tr key={team.team_id}>
              <th scope="row" className="whitespace-nowrap px-2 py-1 text-left font-semibold">{team.team_name}</th>
              {team.values.map((cell) => (
                <td
                  key={cell.key}
                  className={clsx("min-w-[4.5rem] border border-flaeche px-2 py-1 text-center tabular-nums", heatTextClass(cell.ratio))}
                  style={{ backgroundColor: heatColor(cell.ratio) }}
                  title={cell.ratio != null ? t("heatmap.ofBest", { percent: Math.round(cell.ratio * 100) }) : undefined}
                >
                  {fmtNum(cell.avg)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-leise">{t("heatmap.hint")}</p>
    </div>
  );
}

export function AnomalyList({ anomalies, onSelect }: { anomalies: Anomaly[]; onSelect: (a: Anomaly) => void }) {
  const { t } = useTranslation("analytics");
  if (!anomalies.length) {
    return <p className="flex items-center gap-2 text-sm text-success"><CheckCircle2 className="h-4 w-4" /> {t("anomalies.none")}</p>;
  }
  return (
    <ul className="space-y-2" aria-label={t("anomalies.label")}>
      {anomalies.map((a) => (
        <li key={a.match_id} className="flex flex-wrap items-center gap-3 rounded-lg bg-flaeche-2 p-3">
          <AlertTriangle className={clsx("h-4 w-4 shrink-0", a.severity === "error" ? "text-danger" : "text-warning")} aria-label={a.severity === "error" ? t("anomalies.error") : t("anomalies.warning")} />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-fg">
              {t("anomalies.summary", { team: a.team_name, round: a.round_number, points: fmtNum(a.total_score) })}
              {a.is_practice && <span className="badge-yellow ml-2 text-xs">{t("practice")}</span>}
              {a.confirmed && <span className="badge-green ml-2 text-xs">{t("anomalies.confirmed")}</span>}
            </p>
            <p className="text-xs text-leise">
              {a.reasons.map((r) => `${REASON_LABELS[r.kind] ?? r.kind}: ${r.message}`).join(" · ")}
            </p>
          </div>
          <button type="button" className="btn-secondary text-xs" onClick={() => onSelect(a)}>
            <ClipboardCheck className="h-3.5 w-3.5" /> {t("anomalies.check")}
          </button>
        </li>
      ))}
    </ul>
  );
}

/** Event statistics & anomaly detection for jurors (auftrag 4.2). */
export default function StatisticsPage() {
  const { t } = useTranslation("analytics");
  const { eventId = "" } = useParams();
  const [includePractice, setIncludePractice] = useState(false);
  const { data: stats, isLoading, isError } = useEventStatistics(eventId, includePractice);
  const [selected, setSelected] = useState<Anomaly | null>(null);

  return (
    <div className="p-6">
      <div className="page-header">
        <div className="min-w-0">
          <h1 className="page-title flex items-center gap-2">
            <BarChart3 className="h-7 w-7 shrink-0 text-akzent" aria-hidden="true" /> {t("statistics.title")}
          </h1>
          <p className="page-subtitle">{t("statistics.subtitle")}</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex min-h-11 items-center gap-2 text-sm text-leise">
            <input type="checkbox" checked={includePractice} onChange={(e) => setIncludePractice(e.target.checked)} />
            {t("statistics.includePractice")}
          </label>
          {eventId && <ExportButton url={`/exports/events/${eventId}/matches.csv`} filename="laeufe.csv" label={t("common:export.runsCsv")} variant="csv" />}
        </div>
      </div>
      {isLoading && <p className="text-leise">{t("common:loadingEllipsis")}</p>}
      {isError && <p className="card p-6 text-sm text-danger">{t("statistics.loadFailed")}</p>}
      {stats && (
        <>
          <StatGrid
            ariaLabel={t("statistics.overview")}
            items={[
              { label: t("history.col.runs"), value: stats.overview.runs, icon: ListChecks },
              { label: t("statistics.teams"), value: stats.overview.teams, icon: Users },
              { label: t("statistics.unconfirmed"), value: stats.overview.unconfirmed, icon: ClipboardCheck },
              { label: t("statistics.anomalous"), value: stats.anomalies.length, icon: AlertTriangle },
            ]}
          />

          <SectionCard title={t("statistics.toCheck", { count: stats.anomalies.length })} id="stats-anomalies">
            <AnomalyList anomalies={stats.anomalies} onSelect={setSelected} />
            <p className="mt-3 text-xs text-leise">
              {t("statistics.checksHint")}
            </p>
          </SectionCard>

          <div className="grid gap-6 lg:grid-cols-2">
            <SectionCard title={t("statistics.perRound")} id="stats-rounds">
              <BoxPlotList ariaLabel={t("statistics.perRoundLabel")} rows={stats.rounds.map((r) => ({ label: t("round", { round: r.round_number }), box: r }))} />
            </SectionCard>
            <SectionCard title={t("statistics.perField")} id="stats-fields">
              <BoxPlotList ariaLabel={t("statistics.perFieldLabel")} rows={stats.fields.map((f) => ({ label: f.label, box: f }))} />
            </SectionCard>
          </div>

          <SectionCard title={t("statistics.heatmap")} id="stats-heatmap">
            <Heatmap heatmap={stats.heatmap} />
          </SectionCard>

          <SectionCard title={t("statistics.trend")} id="stats-trend">
            {stats.trend.rounds.length > 0 ? (
              <div className="h-64" data-testid="round-trend-chart">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={stats.trend.rounds} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                    <CartesianGrid stroke={GRID} vertical={false} />
                    <XAxis dataKey="round_number" tick={AXIS_TICK} tickFormatter={(v) => t("roundShort", { round: v })} />
                    <YAxis tick={AXIS_TICK} width={40} />
                    <Tooltip labelFormatter={(v) => t("round", { round: v })} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line type="monotone" dataKey="mean" name={t("statistics.mean")} stroke={SERIES.primary} strokeWidth={2} dot={{ r: 4 }} />
                    <Line type="monotone" dataKey="median" name={t("statistics.median")} stroke={SERIES.secondary} strokeWidth={2} strokeDasharray="5 3" dot={{ r: 4 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : <p className="text-sm text-leise">{t("noData")}</p>}
            {stats.trend.teams.length > 0 && (
              <div className="table-scroll">
              <table className="mt-4 w-full text-sm">
                <caption className="sr-only">{t("statistics.trendPerTeam")}</caption>
                <thead><tr className="text-left text-fg">
                  <th scope="col" className="py-1 font-semibold">{t("history.col.team")}</th>
                  <th scope="col" className="py-1 font-semibold">{t("history.col.runs")}</th>
                  <th scope="col" className="py-1 font-semibold">{t("statistics.scores")}</th>
                  <th scope="col" className="py-1 text-right font-semibold">{t("statistics.trendPerRun")}</th>
                </tr></thead>
                <tbody>
                  {stats.trend.teams.map((row) => (
                    <tr key={row.team_id} className="border-t border-rand">
                      <td className="py-1">{row.team_name}</td>
                      <td className="py-1 tabular-nums">{row.points.length}</td>
                      <td className="py-1 tabular-nums text-leise">{row.points.map((p) => fmtNum(p.total_score, 0)).join(" → ")}</td>
                      <td className={clsx("py-1 text-right tabular-nums", (row.slope ?? 0) > 0 ? "text-success" : (row.slope ?? 0) < 0 ? "text-danger" : "")}>
                        {row.slope != null && row.slope > 0 ? "+" : ""}{fmtNum(row.slope)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            )}
          </SectionCard>
        </>
      )}
      {eventId && (
        <SectionCard title={t("audit.title")} id="stats-audit">
          <p className="mb-3 text-xs text-leise">{t("audit.hint")}</p>
          <EventAuditTrail eventId={eventId} />
        </SectionCard>
      )}
      <MatchReviewModal anomaly={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

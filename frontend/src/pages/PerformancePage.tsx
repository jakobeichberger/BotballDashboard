import { useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Activity, ArrowDownRight, ArrowUpRight, Minus, TrendingUp } from "lucide-react";
import clsx from "clsx";
import { useTranslation } from "react-i18next";
import { formatDate } from "@/i18n/format";
import {
  phaseLabel,
  fmtNum,
  usePerformanceOverview,
  useTeamPerformance,
  type TeamPerformance,
} from "@/api/analytics";
import { AXIS_TICK, GRID, SERIES } from "@/components/analytics/chartTheme";
import { StatGrid, SectionCard } from "./dashboard/widgets";

function TrendIcon({ slope }: { slope: number | null }) {
  const { t } = useTranslation("analytics");
  if (slope == null || Math.abs(slope) < 0.5) return <Minus className="inline h-4 w-4 text-leise" aria-label={t("trend.flat")} />;
  return slope > 0
    ? <ArrowUpRight className="inline h-4 w-4 text-success" aria-label={t("trend.up")} />
    : <ArrowDownRight className="inline h-4 w-4 text-danger" aria-label={t("trend.down")} />;
}

/** Score per run in order; practice and official runs are separate series. */
export function ScoreTrendChart({ runs }: { runs: TeamPerformance["runs"] }) {
  const { t } = useTranslation("analytics");
  const data = runs
    .filter((r) => !r.is_disqualified)
    .map((r, i) => ({
      name: `${i + 1}`,
      label: `${r.is_practice ? t("practice") : phaseLabel(r.phase)} · ${t("round", { round: r.round_number })}${r.created_at ? ` · ${formatDate(r.created_at)}` : ""}`,
      official: r.is_practice ? null : r.total_score,
      practice: r.is_practice ? r.total_score : null,
    }));
  if (!data.length) return <p className="text-sm text-leise">{t("performance.noRuns")}</p>;
  return (
    <div className="h-64" data-testid="score-trend-chart">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="name" tick={AXIS_TICK} label={{ value: t("performance.run"), position: "insideBottomRight", offset: -4, fontSize: 11 }} />
          <YAxis tick={AXIS_TICK} width={40} />
          <Tooltip labelFormatter={(_, payload) => payload?.[0]?.payload?.label ?? ""} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line type="monotone" dataKey="official" name={t("performance.official")} stroke={SERIES.primary} strokeWidth={2} dot={{ r: 4 }} connectNulls />
          <Line type="monotone" dataKey="practice" name={t("performance.practiceInternal")} stroke={SERIES.secondary} strokeWidth={2} strokeDasharray="5 3" dot={{ r: 4, fill: "rgb(var(--flaeche))" }} connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function FieldComparison({ perf }: { perf: TeamPerformance }) {
  const { t } = useTranslation("analytics");
  const rows = perf.fields.filter((f) => f.team_avg != null || f.field_avg != null);
  if (!rows.length) return <p className="text-sm text-leise">{t("performance.noFields")}</p>;
  const data = rows.map((f) => ({ label: f.label, team: f.team_avg, field: f.field_avg }));
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div style={{ height: Math.max(160, rows.length * 44) }} data-testid="field-comparison-chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }} barGap={2}>
            <CartesianGrid stroke={GRID} horizontal={false} />
            <XAxis type="number" tick={AXIS_TICK} />
            <YAxis type="category" dataKey="label" width={110} tick={AXIS_TICK} />
            <Tooltip />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="team" name={perf.team_name} fill={SERIES.primary} radius={[0, 4, 4, 0]} barSize={10} />
            <Bar dataKey="field" name={t("performance.fieldAvg")} fill={SERIES.muted} radius={[0, 4, 4, 0]} barSize={10} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="table-scroll">
      <table className="w-full text-sm self-start">
        <caption className="sr-only">{t("performance.fieldsCaption")}</caption>
        <thead>
          <tr className="text-left text-fg">
            <th scope="col" className="py-1 font-semibold">{t("performance.task")}</th>
            <th scope="col" className="py-1 text-right font-semibold">{t("performance.teamAvg")}</th>
            <th scope="col" className="py-1 text-right font-semibold">{t("performance.fieldAvgShort")}</th>
            <th scope="col" className="py-1 text-right font-semibold">Δ</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((f) => (
            <tr key={f.key} className="border-t border-rand">
              <td className="py-1">
                {f.label}
                {perf.strengths.includes(f.key) && <span className="badge-green ml-2 text-xs">{t("performance.strength")}</span>}
                {perf.weaknesses.includes(f.key) && <span className="badge-red ml-2 text-xs">{t("performance.weakness")}</span>}
              </td>
              <td className="py-1 text-right tabular-nums">{fmtNum(f.team_avg)}</td>
              <td className="py-1 text-right tabular-nums">{fmtNum(f.field_avg)}</td>
              <td className={clsx("py-1 text-right tabular-nums", (f.delta ?? 0) > 0 ? "text-success" : (f.delta ?? 0) < 0 ? "text-danger" : "")}>
                {f.delta != null && f.delta > 0 ? "+" : ""}{fmtNum(f.delta)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    </div>
  );
}

export function TeamPerformanceView({ perf }: { perf: TeamPerformance }) {
  const { t } = useTranslation("analytics");
  const p = perf.ranking_preview;
  const s = perf.summary;
  return (
    <div data-testid="team-performance">
      <StatGrid
        ariaLabel={t("performance.metrics")}
        items={[
          { label: t("performance.officialAvg"), value: `${fmtNum(s.official_avg)} (${s.official_runs})`, icon: Activity },
          { label: t("history.col.bestRun"), value: fmtNum(s.official_best), icon: TrendingUp },
          { label: t("performance.practiceAvg"), value: `${fmtNum(s.practice_avg)} (${s.practice_runs})`, icon: Activity },
          { label: t("performance.trendPerRun"), value: s.trend_per_run == null ? "—" : `${s.trend_per_run > 0 ? "+" : ""}${fmtNum(s.trend_per_run)}`, icon: TrendingUp },
        ]}
      />

      <SectionCard title={t("performance.preview")} id="perf-preview">
        <dl className="grid gap-4 sm:grid-cols-3 text-sm">
          <div>
            <dt className="text-leise">{t("history.col.seeding")}</dt>
            <dd className="text-2xl font-bold text-fg tabular-nums">
              {p.seeding_rank ? `${p.seeding_rank}.` : "—"} <span className="text-sm font-normal text-leise">{t("performance.of", { total: p.seeding_teams })}</span>
            </dd>
            <dd className="text-leise">{t("performance.score", { score: fmtNum(p.seeding_score) })}</dd>
          </div>
          <div>
            <dt className="text-leise">{t("performance.overall", { category: perf.category })}</dt>
            <dd className="text-2xl font-bold text-fg tabular-nums">
              {p.overall_rank ? `${p.overall_rank}.` : "—"} <span className="text-sm font-normal text-leise">{t("performance.of", { total: p.overall_teams })}</span>
            </dd>
            <dd className="text-leise">{t("performance.score", { score: fmtNum(p.overall_score, 3) })}</dd>
          </div>
          <div>
            <dt className="text-leise">{t("performance.gap")}</dt>
            <dd className="text-2xl font-bold text-fg tabular-nums">{p.points_to_next_rank != null ? `+${fmtNum(p.points_to_next_rank)}` : "—"}</dd>
            <dd className="text-leise">{t("performance.gapHint")}</dd>
          </div>
        </dl>
      </SectionCard>

      <SectionCard title={t("performance.scoreTrend")} id="perf-trend">
        <ScoreTrendChart runs={perf.runs} />
        <p className="mt-2 text-xs text-leise">{t("performance.practiceHint")}</p>
      </SectionCard>

      <SectionCard title={t("performance.strengths")} id="perf-fields">
        <FieldComparison perf={perf} />
      </SectionCard>

      <SectionCard title={t("performance.phases")} id="perf-phases">
        <div className="table-scroll">
        <table className="w-full text-sm">
          <caption className="sr-only">{t("performance.phasesCaption")}</caption>
          <thead><tr className="text-left text-fg">
            {[t("performance.phase"), t("history.col.runs"), "Ø", t("statistics.median"), "Min", "Max"].map((h) => <th key={h} scope="col" className="py-1 font-semibold">{h}</th>)}
          </tr></thead>
          <tbody>
            {perf.phases.map((ph) => (
              <tr key={ph.phase} className="border-t border-rand">
                <td className="py-1">{ph.phase === "practice" ? <span className="badge-yellow text-xs">{t("practice")}</span> : phaseLabel(ph.phase)}</td>
                <td className="py-1 tabular-nums">{ph.n}</td>
                <td className="py-1 tabular-nums">{fmtNum(ph.mean)}</td>
                <td className="py-1 tabular-nums">{fmtNum(ph.median)}</td>
                <td className="py-1 tabular-nums">{fmtNum(ph.min)}</td>
                <td className="py-1 tabular-nums">{fmtNum(ph.max)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
        {perf.season_events.length > 1 && (
          <>
            <h3 className="mt-6 mb-2 text-sm font-semibold text-fg">{t("performance.seasonEvents")}</h3>
            <div className="table-scroll">
            <table className="w-full text-sm">
              <caption className="sr-only">{t("performance.seasonEventsCaption")}</caption>
              <thead><tr className="text-left text-fg">
                {[t("history.col.event"), t("history.col.practiceAvg"), t("performance.officialAvgShort"), t("history.col.bestRun")].map((h) => <th key={h} scope="col" className="py-1 font-semibold">{h}</th>)}
              </tr></thead>
              <tbody>
                {perf.season_events.map((e) => (
                  <tr key={e.event_id} className={clsx("border-t border-rand", e.event_id === perf.event_id && "font-semibold")}>
                    <td className="py-1">{e.event_name}</td>
                    <td className="py-1 tabular-nums">{fmtNum(e.practice_avg)} ({e.practice_runs})</td>
                    <td className="py-1 tabular-nums">{fmtNum(e.official_avg)} ({e.official_runs})</td>
                    <td className="py-1 tabular-nums">{fmtNum(e.official_best)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </>
        )}
      </SectionCard>
    </div>
  );
}

/** Performance dashboard (spec 05): team comparison + per-team drill-down. */
export default function PerformancePage() {
  const { t } = useTranslation("analytics");
  const { eventId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const { data: overview, isLoading } = usePerformanceOverview(eventId);
  const selected = params.get("team") ?? overview?.[0]?.team_id ?? "";
  const [includePractice, setIncludePractice] = useState(true);
  const { data: perf, isError } = useTeamPerformance(eventId, selected || undefined, includePractice);
  const sorted = useMemo(() => overview ?? [], [overview]);

  return (
    <div className="p-6">
      <h1 className="page-title mb-6 flex items-center gap-2">
        <Activity className="h-7 w-7 shrink-0 text-akzent" /> {t("performance.title")}
      </h1>

      <SectionCard title={t("performance.comparison")} id="perf-overview">
        {isLoading && <p className="text-sm text-leise">{t("common:loadingEllipsis")}</p>}
        {!isLoading && sorted.length === 0 && <p className="text-sm text-leise">{t("performance.noTeams")}</p>}
        {sorted.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">{t("performance.comparisonCaption")}</caption>
              <thead><tr className="text-left text-fg">
                {[t("history.col.team"), t("history.col.seeding"), t("performance.officialAvg"), t("performance.best"), t("performance.practiceAvg"), t("performance.trend"), ""].map((h, i) => <th key={h || i} scope="col" className="py-1 pr-3 font-semibold">{h}</th>)}
              </tr></thead>
              <tbody>
                {sorted.map((row) => (
                  <tr key={row.team_id} className={clsx("border-t border-rand", row.team_id === selected && "bg-primary/10")}>
                    <td className="py-1.5 pr-3 font-medium">{row.team_name}</td>
                    <td className="py-1.5 pr-3 tabular-nums">{row.seeding_rank ?? "—"}</td>
                    <td className="py-1.5 pr-3 tabular-nums">{fmtNum(row.official_avg)} ({row.official_runs})</td>
                    <td className="py-1.5 pr-3 tabular-nums">{fmtNum(row.official_best)}</td>
                    <td className="py-1.5 pr-3 tabular-nums">{fmtNum(row.practice_avg)} ({row.practice_runs})</td>
                    <td className="py-1.5 pr-3"><TrendIcon slope={row.trend_per_run} /></td>
                    <td className="py-1.5 text-right">
                      <button type="button" className="text-xs text-akzent hover:underline" onClick={() => setParams({ team: row.team_id })} aria-label={t("performance.detailsFor", { team: row.team_name })}>
                        {t("performance.details")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {selected && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-xl font-semibold text-fg">{perf?.team_name ?? t("history.col.team")}</h2>
          <label className="flex items-center gap-2 text-sm text-leise">
            <input type="checkbox" checked={includePractice} onChange={(e) => setIncludePractice(e.target.checked)} />
            {t("performance.includePractice")}
          </label>
        </div>
      )}
      {isError && <p className="card p-6 text-sm text-danger">{t("performance.noAccess")}</p>}
      {perf && <TeamPerformanceView perf={perf} />}
    </div>
  );
}

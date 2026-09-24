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
import {
  PHASE_LABELS,
  fmtNum,
  usePerformanceOverview,
  useTeamPerformance,
  type TeamPerformance,
} from "@/api/analytics";
import { AXIS_TICK, GRID, SERIES } from "@/components/analytics/chartTheme";
import { StatGrid, SectionCard } from "./dashboard/widgets";

function TrendIcon({ slope }: { slope: number | null }) {
  if (slope == null || Math.abs(slope) < 0.5) return <Minus className="inline h-4 w-4 text-gray-400" aria-label="gleichbleibend" />;
  return slope > 0
    ? <ArrowUpRight className="inline h-4 w-4 text-green-600" aria-label="steigend" />
    : <ArrowDownRight className="inline h-4 w-4 text-red-600" aria-label="fallend" />;
}

/** Score per run in order; practice and official runs are separate series. */
export function ScoreTrendChart({ runs }: { runs: TeamPerformance["runs"] }) {
  const data = runs
    .filter((r) => !r.is_disqualified)
    .map((r, i) => ({
      name: `${i + 1}`,
      label: `${r.is_practice ? "Übung" : PHASE_LABELS[r.phase] ?? r.phase} · Runde ${r.round_number}${r.created_at ? ` · ${new Date(r.created_at).toLocaleDateString("de-DE")}` : ""}`,
      official: r.is_practice ? null : r.total_score,
      practice: r.is_practice ? r.total_score : null,
    }));
  if (!data.length) return <p className="text-sm text-gray-500">Noch keine Läufe.</p>;
  return (
    <div className="h-64" data-testid="score-trend-chart">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="name" tick={AXIS_TICK} label={{ value: "Lauf", position: "insideBottomRight", offset: -4, fontSize: 11 }} />
          <YAxis tick={AXIS_TICK} width={40} />
          <Tooltip labelFormatter={(_, payload) => payload?.[0]?.payload?.label ?? ""} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line type="monotone" dataKey="official" name="Wettbewerb" stroke={SERIES.primary} strokeWidth={2} dot={{ r: 4 }} connectNulls />
          <Line type="monotone" dataKey="practice" name="Übung (intern)" stroke={SERIES.secondary} strokeWidth={2} strokeDasharray="5 3" dot={{ r: 4, fill: "#fff" }} connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function FieldComparison({ perf }: { perf: TeamPerformance }) {
  const rows = perf.fields.filter((f) => f.team_avg != null || f.field_avg != null);
  if (!rows.length) return <p className="text-sm text-gray-500">Keine Einzelwertungen vorhanden.</p>;
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
            <Bar dataKey="field" name="Ø Teilnehmerfeld" fill={SERIES.muted} radius={[0, 4, 4, 0]} barSize={10} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <table className="w-full text-sm self-start">
        <caption className="sr-only">Punkte pro Aufgabe: Team gegen Teilnehmerfeld</caption>
        <thead>
          <tr className="text-left text-gray-500">
            <th scope="col" className="py-1 font-medium">Aufgabe</th>
            <th scope="col" className="py-1 text-right font-medium">Team Ø</th>
            <th scope="col" className="py-1 text-right font-medium">Feld Ø</th>
            <th scope="col" className="py-1 text-right font-medium">Δ</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((f) => (
            <tr key={f.key} className="border-t border-gray-100 dark:border-gray-800">
              <td className="py-1">
                {f.label}
                {perf.strengths.includes(f.key) && <span className="badge-green ml-2 text-xs">Stärke</span>}
                {perf.weaknesses.includes(f.key) && <span className="badge-red ml-2 text-xs">Schwäche</span>}
              </td>
              <td className="py-1 text-right tabular-nums">{fmtNum(f.team_avg)}</td>
              <td className="py-1 text-right tabular-nums">{fmtNum(f.field_avg)}</td>
              <td className={clsx("py-1 text-right tabular-nums", (f.delta ?? 0) > 0 ? "text-green-700 dark:text-green-400" : (f.delta ?? 0) < 0 ? "text-red-700 dark:text-red-400" : "")}>
                {f.delta != null && f.delta > 0 ? "+" : ""}{fmtNum(f.delta)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TeamPerformanceView({ perf }: { perf: TeamPerformance }) {
  const p = perf.ranking_preview;
  const s = perf.summary;
  return (
    <div data-testid="team-performance">
      <StatGrid
        ariaLabel="Leistungskennzahlen"
        items={[
          { label: "Ø Wettbewerb", value: `${fmtNum(s.official_avg)} (${s.official_runs})`, icon: Activity },
          { label: "Bester Lauf", value: fmtNum(s.official_best), icon: TrendingUp },
          { label: "Ø Übung", value: `${fmtNum(s.practice_avg)} (${s.practice_runs})`, icon: Activity },
          { label: "Trend pro Lauf", value: s.trend_per_run == null ? "—" : `${s.trend_per_run > 0 ? "+" : ""}${fmtNum(s.trend_per_run)}`, icon: TrendingUp },
        ]}
      />

      <SectionCard title="Ranking-Vorschau – wenn das Event jetzt enden würde" id="perf-preview">
        <dl className="grid gap-4 sm:grid-cols-3 text-sm">
          <div>
            <dt className="text-gray-500">Seeding</dt>
            <dd className="text-2xl font-bold text-gray-900 dark:text-white tabular-nums">
              {p.seeding_rank ? `${p.seeding_rank}.` : "—"} <span className="text-sm font-normal text-gray-500">von {p.seeding_teams}</span>
            </dd>
            <dd className="text-gray-500">Score {fmtNum(p.seeding_score)}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Gesamtwertung ({perf.category})</dt>
            <dd className="text-2xl font-bold text-gray-900 dark:text-white tabular-nums">
              {p.overall_rank ? `${p.overall_rank}.` : "—"} <span className="text-sm font-normal text-gray-500">von {p.overall_teams}</span>
            </dd>
            <dd className="text-gray-500">Score {fmtNum(p.overall_score, 3)}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Abstand zum nächsten Seeding-Rang</dt>
            <dd className="text-2xl font-bold text-gray-900 dark:text-white tabular-nums">{p.points_to_next_rank != null ? `+${fmtNum(p.points_to_next_rank)}` : "—"}</dd>
            <dd className="text-gray-500">Punkte im Seeding-Schnitt</dd>
          </div>
        </dl>
      </SectionCard>

      <SectionCard title="Score-Verlauf" id="perf-trend">
        <ScoreTrendChart runs={perf.runs} />
        <p className="mt-2 text-xs text-gray-500">Übungsläufe (gestrichelt) sind intern und zählen nicht zur Rangliste.</p>
      </SectionCard>

      <SectionCard title="Stärken & Schwächen je Aufgabe" id="perf-fields">
        <FieldComparison perf={perf} />
      </SectionCard>

      <SectionCard title="Phasen-Vergleich" id="perf-phases">
        <table className="w-full text-sm">
          <caption className="sr-only">Scores je Phase</caption>
          <thead><tr className="text-left text-gray-500">
            {["Phase", "Läufe", "Ø", "Median", "Min", "Max"].map((h) => <th key={h} scope="col" className="py-1 font-medium">{h}</th>)}
          </tr></thead>
          <tbody>
            {perf.phases.map((ph) => (
              <tr key={ph.phase} className="border-t border-gray-100 dark:border-gray-800">
                <td className="py-1">{ph.phase === "practice" ? <span className="badge-yellow text-xs">Übung</span> : PHASE_LABELS[ph.phase] ?? ph.phase}</td>
                <td className="py-1 tabular-nums">{ph.n}</td>
                <td className="py-1 tabular-nums">{fmtNum(ph.mean)}</td>
                <td className="py-1 tabular-nums">{fmtNum(ph.median)}</td>
                <td className="py-1 tabular-nums">{fmtNum(ph.min)}</td>
                <td className="py-1 tabular-nums">{fmtNum(ph.max)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {perf.season_events.length > 1 && (
          <>
            <h3 className="mt-6 mb-2 text-sm font-semibold text-gray-700 dark:text-gray-300">Events dieser Saison (Vorbereitung ↔ Turnier)</h3>
            <table className="w-full text-sm">
              <caption className="sr-only">Vergleich der Events der Saison</caption>
              <thead><tr className="text-left text-gray-500">
                {["Event", "Übung Ø", "Wettbewerb Ø", "Bester Lauf"].map((h) => <th key={h} scope="col" className="py-1 font-medium">{h}</th>)}
              </tr></thead>
              <tbody>
                {perf.season_events.map((e) => (
                  <tr key={e.event_id} className={clsx("border-t border-gray-100 dark:border-gray-800", e.event_id === perf.event_id && "font-semibold")}>
                    <td className="py-1">{e.event_name}</td>
                    <td className="py-1 tabular-nums">{fmtNum(e.practice_avg)} ({e.practice_runs})</td>
                    <td className="py-1 tabular-nums">{fmtNum(e.official_avg)} ({e.official_runs})</td>
                    <td className="py-1 tabular-nums">{fmtNum(e.official_best)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </SectionCard>
    </div>
  );
}

/** Performance dashboard (spec 05): team comparison + per-team drill-down. */
export default function PerformancePage() {
  const { eventId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const { data: overview, isLoading } = usePerformanceOverview(eventId);
  const selected = params.get("team") ?? overview?.[0]?.team_id ?? "";
  const [includePractice, setIncludePractice] = useState(true);
  const { data: perf, isError } = useTeamPerformance(eventId, selected || undefined, includePractice);
  const sorted = useMemo(() => overview ?? [], [overview]);

  return (
    <div className="p-6">
      <h1 className="mb-6 text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
        <Activity className="w-6 h-6" /> Performance-Dashboard
      </h1>

      <SectionCard title="Teamvergleich" id="perf-overview">
        {isLoading && <p className="text-sm text-gray-500">Laden…</p>}
        {!isLoading && sorted.length === 0 && <p className="text-sm text-gray-500">Keine Teams mit Daten – Mentor:innen sehen hier nur das eigene Team.</p>}
        {sorted.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Teams nach aktuellem Durchschnitt</caption>
              <thead><tr className="text-left text-gray-500">
                {["Team", "Seeding", "Ø Wettbewerb", "Bester", "Ø Übung", "Trend", ""].map((h, i) => <th key={h || i} scope="col" className="py-1 pr-3 font-medium">{h}</th>)}
              </tr></thead>
              <tbody>
                {sorted.map((row) => (
                  <tr key={row.team_id} className={clsx("border-t border-gray-100 dark:border-gray-800", row.team_id === selected && "bg-primary-50 dark:bg-primary-900/20")}>
                    <td className="py-1.5 pr-3 font-medium">{row.team_name}</td>
                    <td className="py-1.5 pr-3 tabular-nums">{row.seeding_rank ?? "—"}</td>
                    <td className="py-1.5 pr-3 tabular-nums">{fmtNum(row.official_avg)} ({row.official_runs})</td>
                    <td className="py-1.5 pr-3 tabular-nums">{fmtNum(row.official_best)}</td>
                    <td className="py-1.5 pr-3 tabular-nums">{fmtNum(row.practice_avg)} ({row.practice_runs})</td>
                    <td className="py-1.5 pr-3"><TrendIcon slope={row.trend_per_run} /></td>
                    <td className="py-1.5 text-right">
                      <button type="button" className="text-xs text-primary-600 hover:underline dark:text-primary-400" onClick={() => setParams({ team: row.team_id })} aria-label={`Details ${row.team_name}`}>
                        Details
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
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">{perf?.team_name ?? "Team"}</h2>
          <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
            <input type="checkbox" checked={includePractice} onChange={(e) => setIncludePractice(e.target.checked)} />
            Übungsläufe in Stärken/Schwächen einbeziehen
          </label>
        </div>
      )}
      {isError && <p className="card p-6 text-sm text-red-600">Keine Berechtigung für dieses Team oder keine Daten.</p>}
      {perf && <TeamPerformanceView perf={perf} />}
    </div>
  );
}

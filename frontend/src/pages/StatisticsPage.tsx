import { useState } from "react";
import { useParams } from "react-router-dom";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AlertTriangle, BarChart3, CheckCircle2, ClipboardCheck, ListChecks, Users } from "lucide-react";
import clsx from "clsx";
import { fmtNum, useEventStatistics, type Anomaly, type EventStatistics } from "@/api/analytics";
import { BoxPlotList } from "@/components/analytics/BoxPlot";
import MatchReviewModal from "@/components/analytics/MatchReviewModal";
import { AXIS_TICK, GRID, SERIES, heatColor, heatTextClass } from "@/components/analytics/chartTheme";
import { ExportButton } from "@/components/ExportButtons";
import { StatGrid, SectionCard } from "./dashboard/widgets";

const REASON_LABELS: Record<string, string> = {
  out_of_range: "Unmöglicher Wert",
  invalid_value: "Ungültiger Wert",
  total_mismatch: "Summe passt nicht",
  team_outlier: "Ausreißer (Team)",
  field_outlier: "Ausreißer (Feld)",
  jump: "Sprung",
};

export function Heatmap({ heatmap }: { heatmap: EventStatistics["heatmap"] }) {
  if (!heatmap.teams.length || !heatmap.fields.length) return <p className="text-sm text-gray-500">Keine Daten.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="text-sm">
        <caption className="sr-only">Durchschnittliche Punkte je Team und Aufgabe; Farbe relativ zum besten Team der Aufgabe</caption>
        <thead>
          <tr>
            <th scope="col" className="px-2 py-1 text-left font-medium text-gray-500">Team</th>
            {heatmap.fields.map((f) => <th key={f.key} scope="col" className="px-2 py-1 text-center font-medium text-gray-500">{f.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {heatmap.teams.map((team) => (
            <tr key={team.team_id}>
              <th scope="row" className="whitespace-nowrap px-2 py-1 text-left font-medium">{team.team_name}</th>
              {team.values.map((cell) => (
                <td
                  key={cell.key}
                  className={clsx("min-w-[4.5rem] border border-white px-2 py-1 text-center tabular-nums dark:border-gray-900", heatTextClass(cell.ratio))}
                  style={{ backgroundColor: heatColor(cell.ratio) }}
                  title={cell.ratio != null ? `${Math.round(cell.ratio * 100)} % des besten Teams` : undefined}
                >
                  {fmtNum(cell.avg)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-gray-500">Dunkler = näher am besten Team dieser Aufgabe. Helle Zeilen zeigen schwache Aufgabenbereiche.</p>
    </div>
  );
}

export function AnomalyList({ anomalies, onSelect }: { anomalies: Anomaly[]; onSelect: (a: Anomaly) => void }) {
  if (!anomalies.length) {
    return <p className="flex items-center gap-2 text-sm text-green-700 dark:text-green-400"><CheckCircle2 className="h-4 w-4" /> Keine auffälligen Läufe.</p>;
  }
  return (
    <ul className="space-y-2" aria-label="Auffällige Läufe">
      {anomalies.map((a) => (
        <li key={a.match_id} className="flex flex-wrap items-center gap-3 rounded-lg bg-gray-50 p-3 dark:bg-gray-800">
          <AlertTriangle className={clsx("h-4 w-4 shrink-0", a.severity === "error" ? "text-red-600" : "text-yellow-600")} aria-label={a.severity === "error" ? "Fehler" : "Warnung"} />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-gray-900 dark:text-white">
              {a.team_name} · Runde {a.round_number} · {fmtNum(a.total_score)} Punkte
              {a.is_practice && <span className="badge-yellow ml-2 text-xs">Übung</span>}
              {a.confirmed && <span className="badge-green ml-2 text-xs">bestätigt</span>}
            </p>
            <p className="text-xs text-gray-600 dark:text-gray-400">
              {a.reasons.map((r) => `${REASON_LABELS[r.kind] ?? r.kind}: ${r.message}`).join(" · ")}
            </p>
          </div>
          <button type="button" className="btn-secondary text-xs" onClick={() => onSelect(a)}>
            <ClipboardCheck className="h-3.5 w-3.5" /> Prüfen
          </button>
        </li>
      ))}
    </ul>
  );
}

/** Event statistics & anomaly detection for jurors (auftrag 4.2). */
export default function StatisticsPage() {
  const { eventId = "" } = useParams();
  const [includePractice, setIncludePractice] = useState(false);
  const { data: stats, isLoading, isError } = useEventStatistics(eventId, includePractice);
  const [selected, setSelected] = useState<Anomaly | null>(null);

  return (
    <div className="p-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <BarChart3 className="w-6 h-6" /> Statistik & Anomalien
        </h1>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
            <input type="checkbox" checked={includePractice} onChange={(e) => setIncludePractice(e.target.checked)} />
            Übungsläufe einbeziehen
          </label>
          {eventId && <ExportButton url={`/exports/events/${eventId}/matches.csv`} filename="laeufe.csv" label="Läufe CSV" variant="csv" />}
        </div>
      </div>
      {isLoading && <p className="text-gray-500">Laden…</p>}
      {isError && <p className="card p-6 text-sm text-red-600">Statistiken konnten nicht geladen werden.</p>}
      {stats && (
        <>
          <StatGrid
            ariaLabel="Überblick"
            items={[
              { label: "Läufe", value: stats.overview.runs, icon: ListChecks },
              { label: "Teams", value: stats.overview.teams, icon: Users },
              { label: "Unbestätigt", value: stats.overview.unconfirmed, icon: ClipboardCheck },
              { label: "Auffällig", value: stats.anomalies.length, icon: AlertTriangle },
            ]}
          />

          <SectionCard title={`Zu prüfende Läufe (${stats.anomalies.length})`} id="stats-anomalies">
            <AnomalyList anomalies={stats.anomalies} onSelect={setSelected} />
            <p className="mt-3 text-xs text-gray-500">
              Geprüft werden unmögliche Werte, Summen, die nicht zu den Einzelwerten passen, Ausreißer gegenüber den übrigen Läufen des Teams (robuster z-Wert) und gegenüber allen Läufen (3×IQR) sowie unplausible Sprünge.
            </p>
          </SectionCard>

          <div className="grid gap-6 lg:grid-cols-2">
            <SectionCard title="Verteilung je Runde" id="stats-rounds">
              <BoxPlotList ariaLabel="Boxplots je Runde" rows={stats.rounds.map((r) => ({ label: `Runde ${r.round_number}`, box: r }))} />
            </SectionCard>
            <SectionCard title="Verteilung je Aufgabe (Punkte)" id="stats-fields">
              <BoxPlotList ariaLabel="Boxplots je Aufgabe" rows={stats.fields.map((f) => ({ label: f.label, box: f }))} />
            </SectionCard>
          </div>

          <SectionCard title="Heatmap: Punkte je Team und Aufgabe" id="stats-heatmap">
            <Heatmap heatmap={stats.heatmap} />
          </SectionCard>

          <SectionCard title="Trend über die Runden" id="stats-trend">
            {stats.trend.rounds.length > 0 ? (
              <div className="h-64" data-testid="round-trend-chart">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={stats.trend.rounds} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                    <CartesianGrid stroke={GRID} vertical={false} />
                    <XAxis dataKey="round_number" tick={AXIS_TICK} tickFormatter={(v) => `R${v}`} />
                    <YAxis tick={AXIS_TICK} width={40} />
                    <Tooltip labelFormatter={(v) => `Runde ${v}`} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line type="monotone" dataKey="mean" name="Mittelwert" stroke={SERIES.primary} strokeWidth={2} dot={{ r: 4 }} />
                    <Line type="monotone" dataKey="median" name="Median" stroke={SERIES.secondary} strokeWidth={2} strokeDasharray="5 3" dot={{ r: 4 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : <p className="text-sm text-gray-500">Keine Daten.</p>}
            {stats.trend.teams.length > 0 && (
              <table className="mt-4 w-full text-sm">
                <caption className="sr-only">Trend je Team</caption>
                <thead><tr className="text-left text-gray-500">
                  <th scope="col" className="py-1 font-medium">Team</th>
                  <th scope="col" className="py-1 font-medium">Läufe</th>
                  <th scope="col" className="py-1 font-medium">Scores</th>
                  <th scope="col" className="py-1 text-right font-medium">Trend / Lauf</th>
                </tr></thead>
                <tbody>
                  {stats.trend.teams.map((t) => (
                    <tr key={t.team_id} className="border-t border-gray-100 dark:border-gray-800">
                      <td className="py-1">{t.team_name}</td>
                      <td className="py-1 tabular-nums">{t.points.length}</td>
                      <td className="py-1 tabular-nums text-gray-500">{t.points.map((p) => fmtNum(p.total_score, 0)).join(" → ")}</td>
                      <td className={clsx("py-1 text-right tabular-nums", (t.slope ?? 0) > 0 ? "text-green-700 dark:text-green-400" : (t.slope ?? 0) < 0 ? "text-red-700 dark:text-red-400" : "")}>
                        {t.slope != null && t.slope > 0 ? "+" : ""}{fmtNum(t.slope)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </SectionCard>
        </>
      )}
      <MatchReviewModal anomaly={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

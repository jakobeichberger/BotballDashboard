import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { useScoringScope } from "@/hooks/useScoringScope";
import { aerialScore } from "@/lib/scoring";
import { useSeasonCategories } from "@/lib/categories";
import { EventLink } from "@/components/EventLink";
import { Plane, ArrowLeft, Save, Plus, Users, CheckCircle2, Trophy } from "lucide-react";
import { StatGrid } from "@/pages/dashboard/widgets";
import { formatNumber } from "@/i18n/format";

type Run = number | null;

interface AerialEntry {
  team_id: string;
  runs: Run[];
  score?: number | null;
  rank?: number | null;
}

interface Team {
  id: string;
  name: string;
  team_number: string | null;
}

interface Registration {
  team_id: string;
  category: string;
}

const MAX_RUNS = 20;
const ALL = "";

export default function AerialPage() {
  const { t } = useTranslation("scoring");
  const queryClient = useQueryClient();
  // Results belong to the event of the current route, not the season's first event.
  const { base, eventId, seasonId } = useScoringScope();
  const registry = useSeasonCategories(seasonId);
  const aerialCategories = registry.categories.filter((entry) => entry.kind === "aerial");

  const { data: existing } = useQuery<AerialEntry[]>({
    queryKey: ["aerial-results", base],
    queryFn: async () => { const { data } = await api.get(`${base}/aerial-results`); return data; },
    enabled: !!base,
  });

  const { data: teams } = useQuery<Team[]>({
    queryKey: ["teams"],
    queryFn: async () => { const { data } = await api.get("/teams"); return data; },
  });

  const { data: registrations } = useQuery<Registration[]>({
    queryKey: ["event-registrations", eventId],
    queryFn: async () => (await api.get(`/v1/events/${eventId}/registrations`)).data,
    enabled: !!eventId,
  });
  const categoryOf = useMemo(() => new Map((registrations ?? []).map((r) => [r.team_id, r.category])), [registrations]);

  // Default view: the first aerial category that has registered teams.
  const [chosen, setChosen] = useState<string | null>(null);
  const firstWithTeams = aerialCategories.find((entry) => (registrations ?? []).some((r) => r.category === entry.key))?.key ?? ALL;
  const category = chosen ?? firstWithTeams;
  const categoryEntry = registry.byKey.get(category);

  const visibleTeams = (teams ?? []).filter((team) => category === ALL || categoryOf.get(team.id) === category);

  const [draft, setDraft] = useState<Record<string, Run[]>>({});
  const [extraRuns, setExtraRuns] = useState(0);

  const savedRuns = (teamId: string): Run[] => existing?.find((e) => e.team_id === teamId)?.runs ?? [];
  const runsOf = (teamId: string): Run[] => draft[teamId] ?? savedRuns(teamId);

  const longest = Math.max(0, ...visibleTeams.map((team) => runsOf(team.id).length));
  const configured = category === ALL ? Math.max(0, ...aerialCategories.map((entry) => entry.run_count ?? 0)) : categoryEntry?.run_count ?? 0;
  const runCount = Math.min(MAX_RUNS, Math.max(configured || 4, longest) + extraRuns);

  const setRun = (teamId: string, index: number, value: Run) => {
    setDraft((prev) => {
      const runs = [...(prev[teamId] ?? savedRuns(teamId))];
      while (runs.length <= index) runs.push(null);
      runs[index] = value;
      return { ...prev, [teamId]: runs };
    });
  };

  const saveMutation = useMutation({
    mutationFn: async (entries: AerialEntry[]) => {
      await api.put(`${base}/aerial-results`, entries);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["aerial-results", base] });
      queryClient.invalidateQueries({ queryKey: ["aerial-ranking", base] });
      setDraft({});
    },
  });

  const handleSave = () => {
    if (!base) return;
    saveMutation.mutate(Object.entries(draft).map(([team_id, runs]) => ({ team_id, runs })));
  };

  // Same rule as the backend default: the category's counted runs, else all runs.
  const scoreOf = (teamId: string): number | null => aerialScore(runsOf(teamId), registry.byKey.get(categoryOf.get(teamId) ?? "")?.counted_runs);
  const formatAerial = (score: number | null) => (score == null ? "–" : formatNumber(score, { minimumFractionDigits: 1, maximumFractionDigits: 2 }));
  const preview = (teamId: string): string => formatAerial(scoreOf(teamId));
  const scores = visibleTeams.map((team) => scoreOf(team.id)).filter((score): score is number => score != null);

  return (
    <div className="p-6">
      <div className="page-header items-center">
        <div className="flex min-w-0 items-center gap-3">
          <EventLink to="/scoreboard" aria-label={t("backToScoreboard")} className="btn-icon">
            <ArrowLeft className="h-5 w-5" aria-hidden="true" />
          </EventLink>
          <h1 className="page-title flex items-center gap-2">
            <Plane className="h-7 w-7 shrink-0 text-akzent" aria-hidden="true" />
            {t("aerial.title")}
          </h1>
        </div>
        <button
          onClick={handleSave}
          disabled={saveMutation.isPending || Object.keys(draft).length === 0}
          className="btn-primary"
        >
          <Save className="h-5 w-5" aria-hidden="true" />
          {saveMutation.isPending ? t("saving") : t("common:save")}
        </button>
      </div>

      {saveMutation.isSuccess && (
        <div role="status" className="mb-4 rounded-lg border border-success/40 bg-success/[0.07] px-4 py-2 text-sm text-success">{t("profile:saved")}</div>
      )}

      <StatGrid
        ariaLabel={t("aerial.kpi.label")}
        items={[
          { label: t("aerial.kpi.teams"), value: visibleTeams.length, icon: Users, tone: "info" },
          { label: t("aerial.kpi.scored"), value: scores.length, icon: CheckCircle2, tone: "success" },
          { label: t("aerial.kpi.best"), value: formatAerial(scores.length ? Math.max(...scores) : null), icon: Trophy, tone: "primary" },
        ]}
      />

      <div className="filter-bar">
        <label className="min-w-[12rem]">
          <span className="label">{t("aerial.category")}</span>
          <select className="input" value={category} onChange={(e) => { setChosen(e.target.value); setExtraRuns(0); }}>
            <option value={ALL}>{t("aerial.allTeams")}</option>
            {aerialCategories.map((entry) => <option key={entry.key} value={entry.key}>{registry.label(entry.key)}</option>)}
          </select>
        </label>
        <button type="button" className="btn-secondary" disabled={runCount >= MAX_RUNS} onClick={() => setExtraRuns((n) => n + 1)}>
          <Plus className="h-4 w-4" aria-hidden="true" />{t("aerial.addRun")}
        </button>
      </div>

      <p className="text-sm text-leise mb-4">
        {categoryEntry?.counted_runs ? t("aerial.hintBest", { count: categoryEntry.counted_runs }) : t("aerial.hint")}
      </p>

      <div className="card table-scroll">
        <table className="w-full text-sm">
          <thead className="bg-flaeche-2">
            <tr>
              <th className="px-4 py-3 text-left font-semibold">{t("scouting.team")}</th>
              {Array.from({ length: runCount }, (_, i) => (
                <th key={i} className="px-2 py-3 text-center font-semibold">
                  {t("aerial.run", { number: i + 1 })}
                </th>
              ))}
              <th className="px-4 py-3 text-center font-semibold">
                {t("aerial.score")}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {visibleTeams.map((team) => {
              const runs = runsOf(team.id);
              const dirty = !!draft[team.id];
              return (
                <tr key={team.id} className={dirty ? "bg-warning/[0.08]" : "hover:bg-flaeche-2"}>
                  <td className="px-4 py-2">
                    <div className="font-medium">{team.name}</div>
                    <div className="text-xs text-leise font-mono">{team.team_number ?? team.id}</div>
                  </td>
                  {Array.from({ length: runCount }, (_, i) => (
                    <td key={i} className="px-2 py-2 text-center">
                      <input
                        type="number"
                        min={0}
                        value={runs[i] ?? ""}
                        onChange={(ev) => setRun(team.id, i, ev.target.value === "" ? null : Number(ev.target.value))}
                        aria-label={t("aerial.runFor", { number: i + 1, team: team.name })}
                        className="input text-sm w-20 text-center"
                        placeholder="–"
                      />
                    </td>
                  ))}
                  <td className="px-4 py-2 text-center font-bold text-fg tabular-nums">
                    {preview(team.id)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

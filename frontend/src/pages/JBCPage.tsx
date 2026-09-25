import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import clsx from "clsx";
import { ArrowLeft, CheckCircle2, Puzzle, Save, Trophy, Users } from "lucide-react";
import { StatGrid } from "@/pages/dashboard/widgets";
import { api } from "@/lib/api";
import { useScoringScope } from "@/hooks/useScoringScope";
import { useSeasonCategories } from "@/lib/categories";
import { EventLink } from "@/components/EventLink";
import { formatNumber } from "@/i18n/format";
import { toast } from "@/lib/toast";

interface JBCResult {
  team_id: string;
  points: number | null;
  challenges: { key: string; label?: string | null; points: number }[];
  rank: number | null;
}

interface Registration {
  team_id: string;
  team_name: string;
  team_number: string | null;
  category: string;
}

/**
 * Junior Botball Challenge: points for solved challenges per team (ECER 2026
 * publishes "Points for Solved Challenges" and a rank). The overall ranking
 * uses them through the jbc_2026 formula preset (input jbc_points).
 */
export default function JBCPage() {
  const { t } = useTranslation("scoring");
  const queryClient = useQueryClient();
  const { base, eventId, seasonId } = useScoringScope();
  const registry = useSeasonCategories(seasonId);

  const { data: results } = useQuery<JBCResult[]>({
    queryKey: ["jbc-results", base],
    queryFn: async () => (await api.get(`${base}/jbc-results`)).data,
    enabled: !!base,
  });
  const { data: registrations } = useQuery<Registration[]>({
    queryKey: ["event-registrations", eventId],
    queryFn: async () => (await api.get(`/v1/events/${eventId}/registrations`)).data,
    enabled: !!eventId,
  });
  const teams = (registrations ?? []).filter((r) => registry.kindOf(r.category) === "jbc").sort((a, b) => a.team_name.localeCompare(b.team_name));
  const [draft, setDraft] = useState<Record<string, number | null>>({});
  const saved = (teamId: string) => results?.find((r) => r.team_id === teamId);

  const save = useMutation({
    mutationFn: async () => api.put(`${base}/jbc-results`, Object.entries(draft).map(([team_id, points]) => ({ team_id, points }))),
    onSuccess: () => {
      toast.success(t("profile:saved"));
      setDraft({});
      queryClient.invalidateQueries({ queryKey: ["jbc-results", base] });
    },
    onError: (error) => toast.apiError(error),
  });

  const withPoints = teams.map((team) => saved(team.team_id)?.points).filter((points): points is number => points != null);

  return (
    <div className="p-6">
      <div className="page-header items-center">
        <div className="flex min-w-0 items-center gap-3">
          <EventLink to="/scoreboard" aria-label={t("backToScoreboard")} className="btn-icon"><ArrowLeft className="h-5 w-5" aria-hidden="true" /></EventLink>
          <h1 className="page-title flex items-center gap-2"><Puzzle className="h-7 w-7 shrink-0 text-akzent" aria-hidden="true" />{t("jbc.title")}</h1>
        </div>
        <button className="btn-primary" disabled={save.isPending || Object.keys(draft).length === 0} onClick={() => save.mutate()}><Save className="h-5 w-5" aria-hidden="true" />{t("common:save")}</button>
      </div>
      <StatGrid
        ariaLabel={t("jbc.kpi.label")}
        items={[
          { label: t("jbc.kpi.teams"), value: teams.length, icon: Users, tone: "info" },
          { label: t("jbc.kpi.scored"), value: withPoints.length, icon: CheckCircle2, tone: "success" },
          { label: t("jbc.kpi.best"), value: withPoints.length ? formatNumber(Math.max(...withPoints)) : "–", icon: Trophy, tone: "primary" },
        ]}
      />
      <p className="mb-4 text-sm text-leise">{t("jbc.hint")}</p>
      <div className="card table-scroll">
        <table className="w-full text-sm">
          <thead className="bg-flaeche-2">
            <tr>
              <th className="px-4 py-3 text-left font-semibold">{t("scouting.team")}</th>
              <th className="px-4 py-3 text-center font-semibold">{t("jbc.points")}</th>
              <th className="px-4 py-3 text-center font-semibold">{t("jbc.rank")}</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {teams.map((team) => {
              const result = saved(team.team_id);
              const value = team.team_id in draft ? draft[team.team_id] : result?.points ?? null;
              return (
                <tr key={team.team_id} className={team.team_id in draft ? "bg-warning/[0.08]" : "hover:bg-flaeche-2"}>
                  <td className="px-4 py-2"><div className="font-medium text-fg">{team.team_name}</div><div className="font-mono text-xs text-leise">{team.team_number ?? ""}</div></td>
                  <td className="px-4 py-2 text-center">
                    <input type="number" min={0} step={0.5} className="input mx-auto w-24 text-center text-sm" aria-label={t("jbc.pointsFor", { team: team.team_name })} value={value ?? ""} disabled={!!result?.challenges?.length} title={result?.challenges?.length ? t("jbc.fromChallenges") : undefined} onChange={(e) => setDraft((prev) => ({ ...prev, [team.team_id]: e.target.value === "" ? null : Number(e.target.value) }))} />
                  </td>
                  <td className="px-4 py-2 text-center">
                    <span className={clsx("font-display text-lg font-extrabold tabular-nums", result?.rank != null && result.rank <= 3 ? "text-akzent" : "text-fg")}>{result?.rank ?? "–"}</span>
                    {result?.points != null && <span className="ml-2 text-xs tabular-nums text-leise">({formatNumber(result.points)})</span>}
                  </td>
                </tr>
              );
            })}
            {teams.length === 0 && <tr><td colSpan={3} className="px-4 py-8 text-center text-leise">{t("jbc.noTeams")}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

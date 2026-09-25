import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { useScoringScope } from "@/hooks/useScoringScope";
import { EventLink } from "@/components/EventLink";
import { Medal, ArrowLeft, Save } from "lucide-react";
import DEPlacementPanel from "@/modules/scoring/extras/DEPlacementPanel";

interface DEEntry {
  id?: string;
  team_id: string;
  bracket: string;
  de_rank: number | null;
  bracket_score: number | null;
  de_score: number | null;
}

interface Team {
  id: string;
  name: string;
  team_number: string | null;
}

export default function DEPage() {
  const { t } = useTranslation("scoring");
  const queryClient = useQueryClient();
  // Results belong to the event of the current route, not the season's first event.
  const { base, eventId } = useScoringScope();

  const { data: existing } = useQuery<DEEntry[]>({
    queryKey: ["de-results", base],
    queryFn: async () => { const { data } = await api.get(`${base}/de-results`); return data; },
    enabled: !!base,
  });

  const { data: teams } = useQuery<Team[]>({
    queryKey: ["teams"],
    queryFn: async () => { const { data } = await api.get("/teams"); return data; },
  });

  // Local draft state keyed by team_id
  const [draft, setDraft] = useState<Record<string, Partial<DEEntry>>>({});

  const effective = (teamId: string): Partial<DEEntry> => {
    const saved = existing?.find((e) => e.team_id === teamId) ?? {};
    return { ...saved, ...draft[teamId] };
  };

  const setField = (teamId: string, field: keyof DEEntry, value: any) => {
    setDraft((prev) => ({
      ...prev,
      [teamId]: { ...(prev[teamId] ?? {}), [field]: value },
    }));
  };

  const saveMutation = useMutation({
    mutationFn: async (entries: DEEntry[]) => {
      await api.put(`${base}/de-results`, entries);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["de-results", base] });
      queryClient.invalidateQueries({ queryKey: ["overall-ranking"] });
      setDraft({});
    },
  });

  const handleSave = () => {
    if (!teams || !base) return;
    const entries: DEEntry[] = teams
      .filter((t) => {
        const e = effective(t.id);
        return e.bracket;
      })
      .map((t) => {
        const e = effective(t.id);
        return {
          team_id: t.id,
          bracket: e.bracket ?? "A",
          de_rank: e.de_rank != null ? Number(e.de_rank) : null,
          bracket_score: e.bracket_score != null ? Number(e.bracket_score) : null,
          de_score: e.de_score != null ? Number(e.de_score) : null,
        };
      });
    saveMutation.mutate(entries);
  };

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <EventLink to="/scoreboard" aria-label={t("backToScoreboard")} className="text-gray-400 hover:text-gray-600">
            <ArrowLeft className="w-5 h-5" />
          </EventLink>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Medal className="w-6 h-6 text-blue-500" />
            {t("de.title")}
          </h1>
        </div>
        <button
          onClick={handleSave}
          disabled={saveMutation.isPending || Object.keys(draft).length === 0}
          className="btn-primary text-sm flex items-center gap-2"
        >
          <Save className="w-4 h-4" />
          {saveMutation.isPending ? t("saving") : t("common:save")}
        </button>
      </div>

      {saveMutation.isSuccess && (
        <div className="mb-4 px-4 py-2 bg-green-50 text-green-700 rounded-lg text-sm">
          {t("profile:saved")}
        </div>
      )}

      <p className="text-sm text-gray-500 mb-4">
        {t("de.hint")}
      </p>

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">{t("scouting.team")}</th>
              <th className="px-4 py-3 text-center font-medium text-gray-600 dark:text-gray-400">{t("de.bracket")}</th>
              <th className="px-4 py-3 text-center font-medium text-gray-600 dark:text-gray-400">{t("de.rank")}</th>
              <th className="px-4 py-3 text-center font-medium text-gray-600 dark:text-gray-400">{t("de.bracketScore")}</th>
              <th className="px-4 py-3 text-center font-medium text-gray-600 dark:text-gray-400">{t("de.deScore")}</th>
            </tr>
          </thead>
          <tbody className="divide-y dark:divide-gray-800">
            {teams?.map((team) => {
              const e = effective(team.id);
              const dirty = !!draft[team.id];
              return (
                <tr key={team.id} className={dirty ? "bg-yellow-50 dark:bg-yellow-900/10" : "hover:bg-gray-50 dark:hover:bg-gray-800/50"}>
                  <td className="px-4 py-2">
                    <div className="font-medium">{team.name}</div>
                    <div className="text-xs text-gray-400 font-mono">{team.team_number ?? team.id}</div>
                  </td>
                  <td className="px-4 py-2 text-center">
                    <select
                      value={e.bracket ?? ""}
                      onChange={(ev) => setField(team.id, "bracket", ev.target.value)}
                      aria-label={t("de.bracketFor", { team: team.name })}
                      className="input text-sm w-20"
                    >
                      <option value="">–</option>
                      <option value="A">A</option>
                      <option value="B">B</option>
                    </select>
                  </td>
                  <td className="px-4 py-2 text-center">
                    <input
                      type="number"
                      min={1}
                      value={e.de_rank ?? ""}
                      onChange={(ev) => setField(team.id, "de_rank", ev.target.value === "" ? null : Number(ev.target.value))}
                      aria-label={t("de.rankFor", { team: team.name })}
                      className="input text-sm w-20 text-center"
                      placeholder="–"
                    />
                  </td>
                  <td className="px-4 py-2 text-center">
                    <input
                      type="number"
                      min={0} max={1} step={0.0001}
                      value={e.bracket_score ?? ""}
                      onChange={(ev) => setField(team.id, "bracket_score", ev.target.value === "" ? null : Number(ev.target.value))}
                      aria-label={t("de.bracketScoreFor", { team: team.name })}
                      className="input text-sm w-28 text-center"
                      placeholder="–"
                    />
                  </td>
                  <td className="px-4 py-2 text-center">
                    <input
                      type="number"
                      min={0} max={1} step={0.0001}
                      value={e.de_score ?? ""}
                      onChange={(ev) => setField(team.id, "de_score", ev.target.value === "" ? null : Number(ev.target.value))}
                      aria-label={t("de.deScoreFor", { team: team.name })}
                      className="input text-sm w-28 text-center"
                      placeholder="–"
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {eventId && <DEPlacementPanel eventId={eventId} />}
    </div>
  );
}

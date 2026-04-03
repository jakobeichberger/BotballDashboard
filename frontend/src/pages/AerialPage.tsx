import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSearchParams, Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Plane, ArrowLeft, Save } from "lucide-react";

interface AerialEntry {
  team_id: string;
  run1: number | null;
  run2: number | null;
  run3: number | null;
  run4: number | null;
  score?: number | null;
}

interface Team {
  id: string;
  name: string;
  team_number: string | null;
}

export default function AerialPage() {
  const [searchParams] = useSearchParams();
  const sid = searchParams.get("season_id") ?? "";
  const queryClient = useQueryClient();

  const { data: season } = useQuery({
    queryKey: ["seasons", "active"],
    queryFn: async () => { const { data } = await api.get("/seasons/active"); return data; },
  });
  const seasonId = sid || season?.id;

  const { data: existing } = useQuery<AerialEntry[]>({
    queryKey: ["aerial-results", seasonId],
    queryFn: async () => { const { data } = await api.get(`/scoring/seasons/${seasonId}/aerial-results`); return data; },
    enabled: !!seasonId,
  });

  const { data: teams } = useQuery<Team[]>({
    queryKey: ["teams"],
    queryFn: async () => { const { data } = await api.get("/teams"); return data; },
  });

  const [draft, setDraft] = useState<Record<string, Partial<AerialEntry>>>({});

  const effective = (teamId: string): Partial<AerialEntry> => {
    const saved = existing?.find((e) => e.team_id === teamId) ?? {};
    return { ...saved, ...draft[teamId] };
  };

  const setField = (teamId: string, field: keyof AerialEntry, value: any) => {
    setDraft((prev) => ({ ...prev, [teamId]: { ...(prev[teamId] ?? {}), [field]: value } }));
  };

  const saveMutation = useMutation({
    mutationFn: async (entries: AerialEntry[]) => {
      await api.put(`/scoring/seasons/${seasonId}/aerial-results`, entries);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["aerial-results", seasonId] });
      queryClient.invalidateQueries({ queryKey: ["aerial-ranking", seasonId] });
      setDraft({});
    },
  });

  const handleSave = () => {
    if (!teams || !seasonId) return;
    const entries: AerialEntry[] = teams
      .filter((t) => {
        const e = effective(t.id);
        return e.run1 != null || e.run2 != null || e.run3 != null || e.run4 != null;
      })
      .map((t) => {
        const e = effective(t.id);
        return {
          team_id: t.id,
          run1: e.run1 != null ? Number(e.run1) : null,
          run2: e.run2 != null ? Number(e.run2) : null,
          run3: e.run3 != null ? Number(e.run3) : null,
          run4: e.run4 != null ? Number(e.run4) : null,
        };
      });
    saveMutation.mutate(entries);
  };

  const avgBest2 = (e: Partial<AerialEntry>): string => {
    const vals = [e.run1, e.run2, e.run3, e.run4].filter((v): v is number => v != null);
    if (vals.length === 0) return "–";
    const top2 = vals.sort((a, b) => b - a).slice(0, 2);
    return (top2.reduce((a, b) => a + b, 0) / top2.length).toFixed(1);
  };

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Link to="/scoring" className="text-gray-400 hover:text-gray-600">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Plane className="w-6 h-6 text-sky-500" />
            Aerial – Ergebnisse
          </h1>
        </div>
        <button
          onClick={handleSave}
          disabled={saveMutation.isPending || Object.keys(draft).length === 0}
          className="btn-primary text-sm flex items-center gap-2"
        >
          <Save className="w-4 h-4" />
          {saveMutation.isPending ? "Speichern…" : "Speichern"}
        </button>
      </div>

      {saveMutation.isSuccess && (
        <div className="mb-4 px-4 py-2 bg-green-50 text-green-700 rounded-lg text-sm">Gespeichert</div>
      )}

      <p className="text-sm text-gray-500 mb-4">
        Score = Durchschnitt der 2 besten Läufe. Nur Felder mit Wert ≥ 0 werden gespeichert.
      </p>

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Team</th>
              {[1, 2, 3, 4].map((n) => (
                <th key={n} className="px-4 py-3 text-center font-medium text-gray-600 dark:text-gray-400">
                  Run {n}
                </th>
              ))}
              <th className="px-4 py-3 text-center font-medium text-gray-600 dark:text-gray-400">
                Score (⌀ best 2)
              </th>
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
                  {(["run1", "run2", "run3", "run4"] as const).map((run) => (
                    <td key={run} className="px-4 py-2 text-center">
                      <input
                        type="number"
                        min={0}
                        value={e[run] ?? ""}
                        onChange={(ev) =>
                          setField(team.id, run, ev.target.value === "" ? null : Number(ev.target.value))
                        }
                        className="input text-sm w-24 text-center"
                        placeholder="–"
                      />
                    </td>
                  ))}
                  <td className="px-4 py-2 text-center font-bold text-gray-700 dark:text-gray-300">
                    {avgBest2(e)}
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

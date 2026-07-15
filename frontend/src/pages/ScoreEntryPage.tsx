import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ClipboardList, ArrowLeft, Check, Trash2, Save } from "lucide-react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

interface Field {
  key: string;
  label: string;
  multiplier: number;
  max_value: number | null;
  type: "count" | "boolean";
}

export default function ScoreEntryPage() {
  const qc = useQueryClient();
  const isAdmin = useAuthStore((s) => s.hasRole("admin"));
  const isJuror = useAuthStore((s) => s.hasRole("juror"));
  const isMentor = useAuthStore((s) => s.hasRole("mentor"));
  const canEnter = isAdmin || isJuror || isMentor;
  const canManageAll = isAdmin || isJuror; // scoring:admin → any team + confirm/delete

  const { data: season } = useQuery({
    queryKey: ["season-active"],
    queryFn: async () => (await api.get("/seasons/active")).data,
  });
  const sid = season?.id;

  const { data: allTeams } = useQuery({
    queryKey: ["teams"],
    queryFn: async () => (await api.get("/teams")).data,
  });
  const { data: myTeams } = useQuery({
    queryKey: ["teams-mine"],
    queryFn: async () => (await api.get("/teams/mine")).data,
    enabled: canEnter && !canManageAll,
  });
  const { data: schema } = useQuery({
    queryKey: ["scoring-schema", sid],
    queryFn: async () => (await api.get(`/scoring/seasons/${sid}/schema`)).data,
    enabled: !!sid,
  });
  const { data: matches } = useQuery({
    queryKey: ["matches", sid],
    queryFn: async () => (await api.get(`/scoring/seasons/${sid}/matches`)).data,
    enabled: !!sid,
  });

  const entryTeams = canManageAll ? allTeams : myTeams;
  const teamName = (tid: string) => allTeams?.find((t: any) => t.id === tid)?.name ?? tid;

  const [teamId, setTeamId] = useState("");
  const [round, setRound] = useState(1);
  const [scores, setScores] = useState<Record<string, number>>({});

  const fields: Field[] = schema?.fields ?? [];
  const preview = fields.reduce((sum, f) => sum + (Number(scores[f.key] || 0) * f.multiplier), 0);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["matches", sid] });
  const onError = (e: any) => alert(e?.response?.data?.detail ?? "Aktion fehlgeschlagen.");

  const saveM = useMutation({
    mutationFn: () =>
      api.post(`/scoring/seasons/${sid}/matches`, {
        team_id: teamId,
        round_number: round,
        raw_scores: Object.fromEntries(fields.map((f) => [f.key, Number(scores[f.key] || 0)])),
      }),
    onSuccess: () => { setScores({}); invalidate(); },
    onError,
  });
  const confirmM = useMutation({
    mutationFn: (mid: string) => api.put(`/scoring/matches/${mid}/confirm`),
    onSuccess: invalidate, onError,
  });
  const deleteM = useMutation({
    mutationFn: (mid: string) => api.delete(`/scoring/matches/${mid}`),
    onSuccess: invalidate, onError,
  });

  const visibleMatches = (matches ?? [])
    .filter((m: any) => canManageAll || myTeams?.some((t: any) => t.id === m.team_id))
    .sort((a: any, b: any) => a.round_number - b.round_number);

  if (!canEnter) {
    return (
      <div className="p-6">
        <div className="card p-8 text-center text-gray-400">
          Keine Berechtigung zur Wertungserfassung.
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <Link to="/scoring" className="btn-secondary text-sm">
        <ArrowLeft className="w-4 h-4" /> Zurück zur Rangliste
      </Link>

      <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
        <ClipboardList className="w-6 h-6" /> Wertung erfassen
      </h1>

      {!season && <p className="text-red-600 text-sm">Keine aktive Saison.</p>}
      {season && !schema && (
        <p className="text-yellow-600 text-sm">Kein aktives Wertungsschema für diese Saison hinterlegt.</p>
      )}

      {/* Entry form */}
      {season && schema && (
        <div className="card p-6 space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <label className="label">Team</label>
              <select className="input" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
                <option value="">— Team wählen —</option>
                {entryTeams?.map((t: any) => (<option key={t.id} value={t.id}>{t.name}</option>))}
              </select>
            </div>
            <div>
              <label className="label">Runde</label>
              <input type="number" min={1} className="input" value={round}
                     onChange={(e) => setRound(Number(e.target.value) || 1)} />
            </div>
            <div className="flex items-end">
              <div className="text-sm">
                <div className="text-gray-500">Punkte (Vorschau)</div>
                <div className="text-2xl font-bold text-primary-600 dark:text-primary-400">{preview}</div>
              </div>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 border-t pt-4">
            {fields.map((f) => (
              <div key={f.key}>
                <label className="label">
                  {f.label} <span className="text-gray-400">(×{f.multiplier})</span>
                </label>
                {f.type === "boolean" ? (
                  <label className="inline-flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={!!scores[f.key]}
                      onChange={(e) => setScores({ ...scores, [f.key]: e.target.checked ? 1 : 0 })}
                    />
                    Erreicht
                  </label>
                ) : (
                  <input
                    type="number" min={0} max={f.max_value ?? undefined} className="input"
                    value={scores[f.key] ?? ""}
                    onChange={(e) => setScores({ ...scores, [f.key]: Number(e.target.value) })}
                  />
                )}
              </div>
            ))}
          </div>

          <div className="flex justify-end">
            <button
              className="btn-primary disabled:opacity-40"
              disabled={!teamId || saveM.isPending}
              onClick={() => saveM.mutate()}
            >
              <Save className="w-4 h-4" /> Wertung speichern
            </button>
          </div>
          {!canManageAll && (
            <p className="text-xs text-gray-400">
              Deine Wertung wird zur Bestätigung durch die Jury eingereicht.
            </p>
          )}
        </div>
      )}

      {/* Matches list */}
      <section className="card overflow-hidden">
        <h2 className="px-4 py-3 border-b font-semibold text-gray-900 dark:text-white">
          Erfasste Wertungen ({visibleMatches.length})
        </h2>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Team</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Runde</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Punkte</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Status</th>
              {canManageAll && <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Aktionen</th>}
            </tr>
          </thead>
          <tbody className="divide-y dark:divide-gray-800">
            {visibleMatches.map((m: any) => (
              <tr key={m.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <td className="px-4 py-3 text-gray-900 dark:text-white">{teamName(m.team_id)}</td>
                <td className="px-4 py-3 text-right text-gray-500">{m.round_number}</td>
                <td className="px-4 py-3 text-right font-semibold">{m.total_score}</td>
                <td className="px-4 py-3">
                  <span className={m.confirmed_by ? "badge-green" : "badge-yellow"}>
                    {m.confirmed_by ? "Bestätigt" : "Offen"}
                  </span>
                </td>
                {canManageAll && (
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex items-center gap-1">
                      {!m.confirmed_by && (
                        <button onClick={() => confirmM.mutate(m.id)} disabled={confirmM.isPending}
                                className="p-1 rounded text-green-600 hover:bg-green-50 dark:hover:bg-green-900/30 disabled:opacity-40"
                                title="Bestätigen"><Check className="w-4 h-4" /></button>
                      )}
                      <button onClick={() => deleteM.mutate(m.id)} disabled={deleteM.isPending}
                              className="p-1 rounded text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 disabled:opacity-40"
                              title="Löschen"><Trash2 className="w-4 h-4" /></button>
                    </div>
                  </td>
                )}
              </tr>
            ))}
            {visibleMatches.length === 0 && (
              <tr><td colSpan={canManageAll ? 5 : 4} className="px-4 py-8 text-center text-gray-400">Noch keine Wertungen</td></tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}

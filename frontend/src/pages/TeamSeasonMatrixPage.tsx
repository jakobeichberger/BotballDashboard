import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Grid3x3, ArrowLeft, Check, Plus, X } from "lucide-react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

interface Team {
  id: string;
  name: string;
  team_number: string | null;
  competition_level_id: string | null;
}
interface Season {
  id: string;
  name: string;
  year: number;
  is_active: boolean;
}
interface Registration {
  id: string;
  team_id: string;
  season_id: string;
  confirmed: boolean;
}

export default function TeamSeasonMatrixPage() {
  const qc = useQueryClient();
  const canEdit = useAuthStore((s) => s.hasRole("admin"));

  const { data: teams } = useQuery<Team[]>({
    queryKey: ["teams"],
    queryFn: async () => (await api.get("/teams")).data,
  });
  const { data: seasons } = useQuery<Season[]>({
    queryKey: ["seasons"],
    queryFn: async () => (await api.get("/seasons")).data,
  });
  const { data: registrations, isLoading } = useQuery<Registration[]>({
    queryKey: ["registrations"],
    queryFn: async () => (await api.get("/teams/registrations")).data,
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["registrations"] });
  const onError = (e: any) =>
    alert(e?.response?.data?.detail ?? "Aktion fehlgeschlagen.");

  const registerM = useMutation({
    mutationFn: (v: { team_id: string; season_id: string; competition_level_id: string | null }) =>
      api.post("/teams/registrations", v),
    onSuccess: invalidate,
    onError,
  });
  const confirmM = useMutation({
    mutationFn: (id: string) => api.put(`/teams/registrations/${id}/confirm`),
    onSuccess: invalidate,
    onError,
  });
  const removeM = useMutation({
    mutationFn: (id: string) => api.delete(`/teams/registrations/${id}`),
    onSuccess: invalidate,
    onError,
  });

  const busy = registerM.isPending || confirmM.isPending || removeM.isPending;

  const regFor = (teamId: string, seasonId: string) =>
    registrations?.find((r) => r.team_id === teamId && r.season_id === seasonId);

  const confirmedCount = (seasonId: string) =>
    registrations?.filter((r) => r.season_id === seasonId && r.confirmed).length ?? 0;
  const regCount = (seasonId: string) =>
    registrations?.filter((r) => r.season_id === seasonId).length ?? 0;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <Link to="/teams" className="btn-secondary text-sm">
          <ArrowLeft className="w-4 h-4" /> Zurück zu Teams
        </Link>
      </div>

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <Grid3x3 className="w-6 h-6" />
          Saison-Zuweisung
        </h1>
        {!canEdit && (
          <span className="text-sm text-gray-500">Nur-Lese-Ansicht (Admin zum Bearbeiten)</span>
        )}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-4 text-xs text-gray-500">
        <span className="flex items-center gap-1"><span className="badge-green"><Check className="w-3 h-3" /></span> Bestätigt</span>
        <span className="flex items-center gap-1"><span className="badge-yellow">Offen</span> Registriert, nicht bestätigt</span>
        <span className="flex items-center gap-1"><span className="badge-gray">–</span> Nicht zugewiesen</span>
      </div>

      {isLoading && <p className="text-gray-500">Laden...</p>}

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400 sticky left-0 bg-gray-50 dark:bg-gray-800 z-10">
                Team
              </th>
              {seasons?.map((s) => (
                <th key={s.id} className="px-4 py-3 text-center font-medium text-gray-600 dark:text-gray-400 min-w-[9rem]">
                  <div className="flex items-center justify-center gap-1">
                    {s.name}
                    {s.is_active && <span className="badge-green">aktiv</span>}
                  </div>
                  <div className="text-xs font-normal text-gray-400">
                    {confirmedCount(s.id)}/{regCount(s.id)} bestätigt
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y dark:divide-gray-800">
            {teams?.map((team) => (
              <tr key={team.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <td className="px-4 py-3 sticky left-0 bg-white dark:bg-gray-900 z-10">
                  <Link to={`/teams/${team.id}`} className="font-medium text-primary-600 dark:text-primary-400 hover:underline">
                    {team.name}
                  </Link>
                  {team.team_number && (
                    <span className="block text-xs text-gray-400 font-mono">#{team.team_number}</span>
                  )}
                </td>
                {seasons?.map((s) => {
                  const reg = regFor(team.id, s.id);
                  return (
                    <td key={s.id} className="px-4 py-3 text-center">
                      {!reg && (
                        canEdit ? (
                          <button
                            disabled={busy}
                            onClick={() =>
                              registerM.mutate({ team_id: team.id, season_id: s.id, competition_level_id: team.competition_level_id })
                            }
                            className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs text-gray-500 hover:bg-primary-50 hover:text-primary-600 dark:hover:bg-primary-900/30 disabled:opacity-40"
                            aria-label={`${team.name} für ${s.name} registrieren`}
                          >
                            <Plus className="w-3.5 h-3.5" /> Zuweisen
                          </button>
                        ) : (
                          <span className="badge-gray">–</span>
                        )
                      )}
                      {reg && (
                        <div className="inline-flex items-center gap-1.5">
                          <span className={reg.confirmed ? "badge-green" : "badge-yellow"}>
                            {reg.confirmed ? (
                              <span className="flex items-center gap-1"><Check className="w-3 h-3" /> Bestätigt</span>
                            ) : (
                              "Offen"
                            )}
                          </span>
                          {canEdit && !reg.confirmed && (
                            <button
                              disabled={busy}
                              onClick={() => confirmM.mutate(reg.id)}
                              className="p-1 rounded text-green-600 hover:bg-green-50 dark:hover:bg-green-900/30 disabled:opacity-40"
                              aria-label="Bestätigen"
                              title="Bestätigen"
                            >
                              <Check className="w-3.5 h-3.5" />
                            </button>
                          )}
                          {canEdit && (
                            <button
                              disabled={busy}
                              onClick={() => removeM.mutate(reg.id)}
                              className="p-1 rounded text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 disabled:opacity-40"
                              aria-label="Zuweisung entfernen"
                              title="Entfernen"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
            {teams?.length === 0 && (
              <tr>
                <td colSpan={(seasons?.length ?? 0) + 1} className="px-4 py-8 text-center text-gray-400">
                  Noch keine Teams angelegt
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Grid3x3, ArrowLeft, Check, Plus, X } from "lucide-react";
import { api } from "@/lib/api";
import { EventLink } from "@/components/EventLink";
import { useAuthStore } from "@/store/authStore";
import { toast } from "@/lib/toast";

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
  const { t } = useTranslation("teams");
  const qc = useQueryClient();
  const canEdit = useAuthStore((s) => s.hasPermission("teams:admin"));

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
  const onError = (e: unknown) => toast.apiError(e, t("common:actionFailed"));

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
      <div className="flex flex-wrap items-center justify-between gap-3">
        <EventLink to="/teams" className="btn-secondary text-sm">
          <ArrowLeft className="w-4 h-4" /> {t("detail.back")}
        </EventLink>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="page-title flex items-center gap-2">
          <Grid3x3 className="w-6 h-6" />
          {t("matrix.heading")}
        </h1>
        {!canEdit && (
          <span className="text-sm text-leise">{t("matrix.readOnly")}</span>
        )}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-4 text-xs text-leise">
        <span className="flex items-center gap-1"><span className="badge-green"><Check className="w-3 h-3" /></span> {t("registrations.confirmed")}</span>
        <span className="flex items-center gap-1"><span className="badge-yellow">{t("registrations.open")}</span> {t("matrix.registeredUnconfirmed")}</span>
        <span className="flex items-center gap-1"><span className="badge-gray">–</span> {t("matrix.notAssigned")}</span>
      </div>

      {isLoading && <p className="text-leise">{t("common:loading")}</p>}

      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-flaeche-2">
            <tr>
              <th className="px-4 py-3 text-left font-semibold sticky left-0 bg-flaeche-2 z-10">
                {t("matrix.team")}
              </th>
              {seasons?.map((s) => (
                <th key={s.id} className="px-4 py-3 text-center font-semibold min-w-[9rem]">
                  <div className="flex items-center justify-center gap-1">
                    {s.name}
                    {s.is_active && <span className="badge-green">{t("matrix.active")}</span>}
                  </div>
                  <div className="text-xs font-normal text-leise">
                    {t("matrix.confirmedCount", { confirmed: confirmedCount(s.id), total: regCount(s.id) })}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y">
            {teams?.map((team) => (
              <tr key={team.id} className="hover:bg-flaeche-2">
                <td className="px-4 py-3 sticky left-0 bg-flaeche z-10">
                  <EventLink to={`/teams/${team.id}`} className="font-medium text-akzent hover:underline">
                    {team.name}
                  </EventLink>
                  {team.team_number && (
                    <span className="block text-xs text-leise font-mono">#{team.team_number}</span>
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
                            className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs text-leise hover:bg-primary/10 hover:text-akzent disabled:opacity-40"
                            aria-label={t("matrix.registerLabel", { team: team.name, season: s.name })}
                          >
                            <Plus className="w-3.5 h-3.5" /> {t("matrix.assign")}
                          </button>
                        ) : (
                          <span className="badge-gray">–</span>
                        )
                      )}
                      {reg && (
                        <div className="inline-flex items-center gap-1.5">
                          <span className={reg.confirmed ? "badge-green" : "badge-yellow"}>
                            {reg.confirmed ? (
                              <span className="flex items-center gap-1"><Check className="w-3 h-3" /> {t("registrations.confirmed")}</span>
                            ) : (
                              t("registrations.open")
                            )}
                          </span>
                          {canEdit && !reg.confirmed && (
                            <button
                              disabled={busy}
                              onClick={() => confirmM.mutate(reg.id)}
                              className="p-1 rounded text-success hover:bg-success/10 disabled:opacity-40"
                              aria-label={t("matrix.confirm")}
                              title={t("matrix.confirm")}
                            >
                              <Check className="w-3.5 h-3.5" />
                            </button>
                          )}
                          {canEdit && (
                            <button
                              disabled={busy}
                              onClick={() => removeM.mutate(reg.id)}
                              className="p-1 rounded text-danger hover:bg-danger/10 disabled:opacity-40"
                              aria-label={t("matrix.removeAssignment")}
                              title={t("detail.remove")}
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
                <td colSpan={(seasons?.length ?? 0) + 1} className="px-4 py-8 text-center text-leise">
                  {t("empty")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

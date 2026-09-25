import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Plus, Trash2, UserCheck } from "lucide-react";
import { api } from "@/lib/api";
import { formatTime } from "@/i18n/format";
import { CATEGORY_LABEL } from "@/lib/teams";
import type { EventRegistration } from "@/api/types";
import { confirmAction } from "@/lib/confirm";
import { apiErrorMessage } from "@/lib/errors";

/**
 * Teams registered for the event: register, check in on site (sets
 * checked_in_at) and remove a registration.
 */
export default function RegistrationManager({ eventId }: { eventId: string }) {
  const { t } = useTranslation("events");
  const queryClient = useQueryClient();
  const teams = useQuery<Array<{ id: string; name: string }>>({ queryKey: ["teams"], queryFn: async () => (await api.get("/teams")).data });
  const registrations = useQuery<EventRegistration[]>({ queryKey: ["event-registrations", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/registrations`)).data });
  const [teamId, setTeamId] = useState("");
  const [teamCategory, setTeamCategory] = useState("botball");
  const [error, setError] = useState("");

  const refresh = () => { setError(""); queryClient.invalidateQueries({ queryKey: ["event-registrations", eventId] }); };
  const fail = (e: any) => setError(apiErrorMessage(e, t("common:actionFailed")));
  const addTeam = useMutation({
    mutationFn: async () => api.post(`/v1/events/${eventId}/registrations`, { team_id: teamId, category: teamCategory }),
    onSuccess: () => { setTeamId(""); refresh(); },
    onError: fail,
  });
  const checkIn = useMutation({
    mutationFn: async ({ id, checkedIn }: { id: string; checkedIn: boolean }) => api.patch(`/v1/events/${eventId}/registrations/${id}`, { checked_in: checkedIn }),
    onSuccess: refresh,
    onError: fail,
  });
  const remove = useMutation({
    mutationFn: async (id: string) => api.delete(`/v1/events/${eventId}/registrations/${id}`),
    onSuccess: refresh,
    onError: fail,
  });

  const list = [...(registrations.data ?? [])].sort((a, b) => a.team_name.localeCompare(b.team_name));
  const checkedIn = list.filter((item) => item.checked_in_at).length;
  return (
    <section className="card p-5">
      <h2 className="mb-1 text-lg font-semibold">{t("setup.teams", { count: list.length })}</h2>
      {list.length > 0 && <p className="mb-4 flex items-center gap-1 text-sm text-gray-500"><UserCheck className="h-4 w-4" aria-hidden="true" />{t("setup.checkedInCount", { checkedIn, total: list.length })}</p>}
      <form className="grid gap-2 sm:grid-cols-[1fr_8rem_auto]" onSubmit={(e) => { e.preventDefault(); addTeam.mutate(); }}>
        <select required aria-label={t("setup.registerTeam")} className="input min-w-0" value={teamId} onChange={(e) => setTeamId(e.target.value)}><option value="">{t("setup.registerTeam")}</option>{teams.data?.filter((team) => !list.some((item) => item.team_id === team.id)).map((team) => <option key={team.id} value={team.id}>{team.name}</option>)}</select>
        <select aria-label={t("setup.category")} className="input" value={teamCategory} onChange={(e) => setTeamCategory(e.target.value)}>{["botball", "open", "aerial", "jbc"].map((category) => <option key={category} value={category}>{CATEGORY_LABEL[category]}</option>)}</select>
        <button className="btn-secondary" aria-label={t("setup.registerTeam")} disabled={addTeam.isPending}><Plus /></button>
      </form>
      {error && <p role="alert" className="mt-3 text-sm text-red-600">{error}</p>}
      <ul className="mt-4 max-h-80 divide-y overflow-auto text-sm dark:divide-gray-800">
        {list.map((item) => (
          <li key={item.id} className="flex items-center justify-between gap-2 py-1.5">
            <label className="flex min-w-0 items-center gap-2">
              <input
                type="checkbox"
                checked={!!item.checked_in_at}
                disabled={checkIn.isPending}
                aria-label={t("setup.checkInTeam", { team: item.team_name })}
                onChange={(e) => checkIn.mutate({ id: item.id, checkedIn: e.target.checked })}
              />
              <span className="truncate">{item.team_name}{item.team_number ? ` (${item.team_number})` : ""} · {CATEGORY_LABEL[item.category] ?? item.category}</span>
            </label>
            <span className="flex shrink-0 items-center gap-2">
              {item.checked_in_at && <span className="badge-green">{t("setup.checkedInAt", { time: formatTime(item.checked_in_at) })}</span>}
              <button
                type="button"
                className="rounded p-1 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30"
                aria-label={t("setup.removeRegistration", { team: item.team_name })}
                title={t("common:delete")}
                disabled={remove.isPending}
                onClick={() => void confirmAction({ message: t("setup.confirmRemoveRegistration", { team: item.team_name }), tone: "danger" }).then((ok) => ok && remove.mutate(item.id))}
              ><Trash2 className="h-4 w-4" /></button>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

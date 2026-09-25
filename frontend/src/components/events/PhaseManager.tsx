import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Pencil, Plus, Trash2, X } from "lucide-react";
import { api } from "@/lib/api";
import { phaseLabel } from "@/api/analytics";
import type { EventPhase } from "@/api/types";
import { confirmAction } from "@/lib/confirm";
import { apiErrorMessage } from "@/lib/errors";

export const PHASE_TYPES = ["seeding", "double_seeding", "double_elimination", "alliance", "final"] as const;
export const PHASE_STATUSES = ["draft", "scheduled", "live", "completed"] as const;

/** Live and completed phases carry results: they cannot be deleted or change type. */
function phaseLocked(phase: Pick<EventPhase, "status">): boolean {
  return phase.status === "live" || phase.status === "completed";
}

type PhaseDraft = { name: string; phase_type: string; status: string; rounds: number };

/** The phases of an event: create, rename, retype, set status and delete. */
export default function PhaseManager({ eventId }: { eventId: string }) {
  const { t } = useTranslation("events");
  const queryClient = useQueryClient();
  const phases = useQuery<EventPhase[]>({ queryKey: ["event-phases", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/phases`)).data });
  const [phase, setPhase] = useState({ name: "", phase_type: "seeding", rounds: 3 });
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<PhaseDraft>({ name: "", phase_type: "seeding", status: "draft", rounds: 3 });
  const [error, setError] = useState("");

  const refresh = () => {
    setError("");
    queryClient.invalidateQueries({ queryKey: ["event-phases", eventId] });
    queryClient.invalidateQueries({ queryKey: ["event-bracket", eventId] });
  };
  const fail = (e: any) => setError(apiErrorMessage(e, t("common:actionFailed")));
  // sort_order is unique per event: append after the highest one in use.
  const nextSortOrder = Math.max(-1, ...(phases.data ?? []).map((item) => item.sort_order)) + 1;
  const addPhase = useMutation({
    mutationFn: async () => api.post(`/v1/events/${eventId}/phases`, { ...phase, sort_order: nextSortOrder }),
    onSuccess: () => { setPhase({ name: "", phase_type: "seeding", rounds: 3 }); refresh(); },
    onError: fail,
  });
  const updatePhase = useMutation({
    mutationFn: async (item: EventPhase) => {
      const body: Partial<PhaseDraft> = { name: draft.name, status: draft.status, rounds: draft.rounds };
      if (!phaseLocked(item)) body.phase_type = draft.phase_type;
      return api.patch(`/v1/events/${eventId}/phases/${item.id}`, body);
    },
    onSuccess: () => { setEditing(null); refresh(); },
    onError: fail,
  });
  const deletePhase = useMutation({
    mutationFn: async (id: string) => api.delete(`/v1/events/${eventId}/phases/${id}`),
    onSuccess: refresh,
    onError: fail,
  });

  const startEdit = (item: EventPhase) => {
    setEditing(item.id);
    setDraft({ name: item.name, phase_type: item.phase_type, status: item.status, rounds: item.rounds });
  };

  return (
    <section className="card p-5">
      <h2 className="mb-4 text-lg font-semibold">{t("setup.phases")}</h2>
      {error && <p role="alert" className="mb-3 text-sm text-red-600">{error}</p>}
      <ul className="mb-4 space-y-2">
        {phases.data?.map((item) => editing === item.id ? (
          <li key={item.id} className="rounded bg-gray-50 p-2 text-sm dark:bg-gray-800">
            <form className="grid gap-2 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); updatePhase.mutate(item); }}>
              <label className="text-xs font-medium">{t("setup.phaseName")}<input required minLength={2} className="input mt-1 w-full" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
              <label className="text-xs font-medium">{t("setup.phaseType")}
                <select className="input mt-1 w-full" disabled={phaseLocked(item)} value={draft.phase_type} onChange={(e) => setDraft({ ...draft, phase_type: e.target.value })}>{PHASE_TYPES.map((type) => <option key={type} value={type}>{phaseLabel(type)}</option>)}</select>
              </label>
              <label className="text-xs font-medium">{t("common:status")}
                <select className="input mt-1 w-full" value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value })}>{PHASE_STATUSES.map((status) => <option key={status} value={status}>{t(`setup.phaseStatus.${status}`)}</option>)}</select>
              </label>
              <label className="text-xs font-medium">{t("setup.phaseRounds")}<input type="number" min={1} max={100} className="input mt-1 w-full" value={draft.rounds} onChange={(e) => setDraft({ ...draft, rounds: Number(e.target.value) })} /></label>
              {phaseLocked(item) && <p className="text-xs text-amber-700 dark:text-amber-400 sm:col-span-2">{t("setup.phaseLockedHint")}</p>}
              <div className="flex gap-2 sm:col-span-2">
                <button className="btn-primary" disabled={updatePhase.isPending}>{t("common:save")}</button>
                <button type="button" className="btn-secondary" onClick={() => setEditing(null)}><X className="h-4 w-4" />{t("common:cancel")}</button>
              </div>
            </form>
          </li>
        ) : (
          <li key={item.id} className="flex items-center justify-between gap-2 rounded bg-gray-50 p-2 text-sm dark:bg-gray-800">
            <span>{item.sort_order + 1}. {item.name} · {phaseLabel(item.phase_type)} · {t("setup.roundsCount", { count: item.rounds })}
              <span className={`ml-2 ${item.status === "live" ? "badge-green" : item.status === "completed" ? "badge-blue" : "badge-gray"}`}>{t(`setup.phaseStatus.${item.status}`, { defaultValue: item.status })}</span>
            </span>
            <span className="flex shrink-0 gap-1">
              <button type="button" className="rounded p-1 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700" aria-label={t("setup.editPhase", { name: item.name })} title={t("common:edit")} onClick={() => startEdit(item)}><Pencil className="h-4 w-4" /></button>
              <button
                type="button"
                className="rounded p-1 text-red-600 hover:bg-red-50 disabled:opacity-40 dark:hover:bg-red-900/30"
                aria-label={t("setup.deletePhase", { name: item.name })}
                title={phaseLocked(item) ? t("setup.phaseLockedDelete") : t("common:delete")}
                disabled={phaseLocked(item) || deletePhase.isPending}
                onClick={() => void confirmAction({ message: t("setup.confirmDeletePhase", { name: item.name }), tone: "danger" }).then((ok) => ok && deletePhase.mutate(item.id))}
              ><Trash2 className="h-4 w-4" /></button>
            </span>
          </li>
        ))}
      </ul>
      <form className="grid gap-2 sm:grid-cols-[1fr_1fr_5rem_auto]" onSubmit={(e) => { e.preventDefault(); addPhase.mutate(); }}>
        <input required minLength={2} className="input" aria-label={t("setup.phaseName")} placeholder={t("setup.phaseName")} value={phase.name} onChange={(e) => setPhase({ ...phase, name: e.target.value })} />
        <select className="input" aria-label={t("setup.phaseType")} value={phase.phase_type} onChange={(e) => setPhase({ ...phase, phase_type: e.target.value })}>{PHASE_TYPES.map((type) => <option key={type} value={type}>{phaseLabel(type)}</option>)}</select>
        <input className="input" aria-label={t("setup.phaseRounds")} type="number" min={1} value={phase.rounds} onChange={(e) => setPhase({ ...phase, rounds: Number(e.target.value) })} />
        <button className="btn-secondary" aria-label={t("setup.addPhase")} disabled={addPhase.isPending}><Plus /></button>
      </form>
    </section>
  );
}

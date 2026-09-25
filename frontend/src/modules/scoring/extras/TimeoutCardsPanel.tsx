import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Timer, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { formatDateTime } from "@/i18n/format";
import { useAuthStore } from "@/store/authStore";
import { toast } from "@/lib/toast";
import type { EventRegistration } from "@/api/types";

interface TimeoutCard {
  id: string;
  team_id: string;
  team_name: string | null;
  round_number: number | null;
  reason: "before_hands_off" | "inspection" | string;
  note: string | null;
  used_at: string;
}

/**
 * Timeout cards (game review "Timeout Card"): every team has one red card
 * for a single 3-minute timeout per tournament, taken at the table before
 * Hands-Off or at the on-deck inspection. Jurors record it; a second one is
 * refused by the API.
 */
export default function TimeoutCardsPanel({ eventId, registrations }: { eventId: string; registrations: EventRegistration[] }) {
  const { t } = useTranslation("scoring");
  const queryClient = useQueryClient();
  const canRecord = useAuthStore((state) => state.hasPermission("scoring:write"));
  const canRevoke = useAuthStore((state) => state.hasPermission("scoring:admin"));
  const [teamId, setTeamId] = useState("");
  const [round, setRound] = useState("");
  const [reason, setReason] = useState("before_hands_off");
  const timeouts = useQuery<TimeoutCard[]>({ queryKey: ["timeouts", eventId], queryFn: async () => (await api.get(`/scoring/events/${eventId}/timeouts`)).data, enabled: !!eventId });
  const used = new Set((timeouts.data ?? []).map((card) => card.team_id));
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["timeouts", eventId] });
  const record = useMutation({
    mutationFn: async () => api.post(`/scoring/events/${eventId}/timeouts`, { team_id: teamId, round_number: round ? Number(round) : null, reason }),
    onSuccess: () => { setTeamId(""); setRound(""); refresh(); },
    onError: (error) => toast.apiError(error),
  });
  const revoke = useMutation({ mutationFn: async (id: string) => api.delete(`/scoring/events/${eventId}/timeouts/${id}`), onSuccess: refresh, onError: (error) => toast.apiError(error) });

  return (
    <section className="card p-4" aria-labelledby="timeouts-title">
      <h2 id="timeouts-title" className="mb-1 flex items-center gap-2 text-lg font-semibold"><Timer className="h-5 w-5" />{t("timeouts.title")}</h2>
      <p className="mb-3 text-sm text-gray-500">{t("timeouts.hint")}</p>
      {canRecord && (
        <form className="mb-3 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); if (teamId) record.mutate(); }}>
          <select aria-label={t("timeouts.team")} className="input min-w-0 flex-1" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
            <option value="">{t("timeouts.team")}</option>
            {registrations.filter((r) => !used.has(r.team_id)).map((r) => <option key={r.team_id} value={r.team_id}>{r.team_name}</option>)}
          </select>
          <input aria-label={t("timeouts.round")} type="text" inputMode="numeric" pattern="[0-9]*" className="input w-24" placeholder={t("timeouts.round")} value={round} onChange={(e) => setRound(e.target.value.replace(/\D/g, ""))} />
          <select aria-label={t("timeouts.reason")} className="input w-auto" value={reason} onChange={(e) => setReason(e.target.value)}>
            <option value="before_hands_off">{t("timeouts.beforeHandsOff")}</option>
            <option value="inspection">{t("timeouts.inspection")}</option>
          </select>
          <button className="btn-secondary" disabled={!teamId || record.isPending}>{t("timeouts.record")}</button>
        </form>
      )}
      <ul className="space-y-1 text-sm">
        {(timeouts.data ?? []).map((card) => (
          <li key={card.id} className="flex items-center justify-between gap-2">
            <span>{card.team_name}{card.round_number ? ` · ${t("timeouts.roundN", { round: card.round_number })}` : ""} · {card.reason === "inspection" ? t("timeouts.inspection") : t("timeouts.beforeHandsOff")} <span className="text-xs text-gray-500">{formatDateTime(card.used_at)}</span></span>
            {canRevoke && <button type="button" className="btn-secondary px-2" aria-label={t("timeouts.revoke", { team: card.team_name })} onClick={() => revoke.mutate(card.team_id)}><Trash2 className="h-4 w-4" /></button>}
          </li>
        ))}
        {timeouts.data?.length === 0 && <li className="text-gray-500">{t("timeouts.none")}</li>}
      </ul>
    </section>
  );
}

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Award, UserPlus, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import type { CompetitionLevel, QualificationStatusEntry } from "./types";
import { confirmAction } from "@/lib/confirm";
import { apiErrorMessage } from "@/lib/errors";

/**
 * GCER qualification: admins mark teams of the source level (ECER) as
 * qualified, with a note; qualified teams can then be registered at the
 * target level (e.g. for the GCER event).
 */
export default function QualificationPanel({ eventId, seasonId, onMessage }: { eventId: string; seasonId: string; onMessage: (message: string) => void }) {
  const { t } = useTranslation("scoring");
  const queryClient = useQueryClient();
  const canQualify = useAuthStore((state) => state.hasPermission("seasons:write"));
  const levels = useQuery<CompetitionLevel[]>({ queryKey: ["levels"], queryFn: async () => (await api.get("/seasons/competition-levels/all")).data });
  const targets = useMemo(() => (levels.data ?? []).filter((level) => level.qualifies_from_level_id), [levels.data]);
  const [chosenLevel, setChosenLevel] = useState("");
  const levelId = chosenLevel || targets[0]?.id || "";
  const level = targets.find((item) => item.id === levelId);
  const source = levels.data?.find((item) => item.id === level?.qualifies_from_level_id);
  const status = useQuery<QualificationStatusEntry[]>({
    queryKey: ["qualification-status", seasonId, levelId],
    queryFn: async () => (await api.get(`/scoring/seasons/${seasonId}/qualification-status`, { params: { level_id: levelId } })).data,
    enabled: !!seasonId && !!levelId,
  });
  const [selected, setSelected] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const refresh = () => { queryClient.invalidateQueries({ queryKey: ["qualification-status", seasonId, levelId] }); queryClient.invalidateQueries({ queryKey: ["event-registrations", eventId] }); };
  const detail = (error: unknown, fallback: string) => apiErrorMessage(error, fallback);

  const qualify = useMutation({
    mutationFn: async () => api.post(`/scoring/levels/${levelId}/qualify`, { season_id: seasonId, team_ids: selected, note: note || null, source_event_id: eventId }),
    onSuccess: () => { onMessage(t("qualification.qualified", { count: selected.length, level: level?.name })); setSelected([]); setNote(""); refresh(); },
    onError: (error: unknown) => onMessage(detail(error, t("qualification.failed"))),
  });
  const revoke = useMutation({
    mutationFn: async (id: string) => api.delete(`/scoring/qualifications/${id}`),
    onSuccess: refresh,
    onError: (error: unknown) => onMessage(detail(error, t("qualification.revokeFailed"))),
  });
  const register = useMutation({
    mutationFn: async () => (await api.post(`/scoring/events/${eventId}/register-qualified`, { level_id: levelId })).data as unknown[],
    onSuccess: (created) => { onMessage(t("qualification.registered", { count: created.length })); refresh(); },
    onError: (error: unknown) => onMessage(detail(error, t("qualification.registerFailed"))),
  });

  if (!targets.length) {
    return <section className="card p-5 lg:col-span-2"><h2 className="mb-2 flex items-center gap-2 text-lg font-semibold"><Award className="h-5 w-5" />{t("qualification.title")}</h2><p className="text-sm text-leise">{t("qualification.notConfigured")}</p></section>;
  }
  return (
    <section className="card p-5 lg:col-span-2" aria-labelledby="qualification-title">
      <h2 id="qualification-title" className="mb-1 flex items-center gap-2 text-lg font-semibold"><Award className="h-5 w-5" />{t("qualification.title")} {source ? `${source.name} → ` : ""}{level?.name}</h2>
      <p className="mb-3 text-sm text-leise">{t("qualification.hint", { level: level?.name })}</p>
      {targets.length > 1 && <label className="mb-3 block text-sm font-medium">{t("qualification.targetLevel")}<select className="input mt-1" value={levelId} onChange={(e) => { setChosenLevel(e.target.value); setSelected([]); }}>{targets.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
      <ul className="mb-3 max-h-64 divide-y overflow-auto rounded border text-sm">
        {status.data?.map((entry) => (
          <li key={entry.team_id} className="flex items-center justify-between gap-2 p-2">
            <label className="flex items-center gap-2">
              {!entry.qualified && canQualify && <input type="checkbox" checked={selected.includes(entry.team_id)} onChange={(e) => setSelected(e.target.checked ? [...selected, entry.team_id] : selected.filter((id) => id !== entry.team_id))} />}
              <span>{entry.team_name}</span>
            </label>
            {entry.qualified ? (
              <span className="flex items-center gap-2"><span className="badge-green">{t("qualification.qualifiedBadge")}</span>{entry.note && <span className="text-xs text-leise">{entry.note}</span>}{canQualify && entry.qualification_id && <button type="button" className="btn-secondary min-h-11 min-w-11 justify-center px-2" aria-label={t("qualification.revoke", { team: entry.team_name })} disabled={revoke.isPending} onClick={() => void confirmAction({ message: t("qualification.confirmRevoke", { team: entry.team_name, level: level?.name }), tone: "danger", confirmLabel: t("qualification.revokeShort") }).then((ok) => ok && revoke.mutate(entry.qualification_id!))}><X className="h-4 w-4" aria-hidden="true" /></button>}</span>
            ) : <span className="badge-gray">{t("qualification.notYet")}</span>}
          </li>
        ))}
        {status.data?.length === 0 && <li className="p-3 text-leise">{t("qualification.noTeams")}</li>}
      </ul>
      {canQualify && <div className="flex flex-wrap gap-2"><input className="input min-w-0 flex-1" aria-label={t("qualification.notePlaceholder")} placeholder={t("qualification.notePlaceholder")} value={note} onChange={(e) => setNote(e.target.value)} /><button type="button" className="btn-primary" disabled={!selected.length || qualify.isPending} onClick={() => qualify.mutate()}>{t("qualification.qualify")}</button></div>}
      <button type="button" className="btn-secondary mt-3" disabled={register.isPending} onClick={() => register.mutate()}><UserPlus className="h-4 w-4" />{t("qualification.register")}</button>
    </section>
  );
}

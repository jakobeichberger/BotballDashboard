import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Award, UserPlus, X } from "lucide-react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import type { CompetitionLevel, QualificationStatusEntry } from "./types";

/**
 * GCER qualification: admins mark teams of the source level (ECER) as
 * qualified, with a note; qualified teams can then be registered at the
 * target level (e.g. for the GCER event).
 */
export default function QualificationPanel({ eventId, seasonId, onMessage }: { eventId: string; seasonId: string; onMessage: (message: string) => void }) {
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
  const detail = (error: any, fallback: string) => (typeof error.response?.data?.detail === "string" ? error.response.data.detail : fallback);

  const qualify = useMutation({
    mutationFn: async () => api.post(`/scoring/levels/${levelId}/qualify`, { season_id: seasonId, team_ids: selected, note: note || null, source_event_id: eventId }),
    onSuccess: () => { onMessage(`${selected.length} Team(s) für ${level?.name} qualifiziert.`); setSelected([]); setNote(""); refresh(); },
    onError: (error: any) => onMessage(detail(error, "Qualifikation fehlgeschlagen.")),
  });
  const revoke = useMutation({
    mutationFn: async (id: string) => api.delete(`/scoring/qualifications/${id}`),
    onSuccess: refresh,
    onError: (error: any) => onMessage(detail(error, "Qualifikation konnte nicht entfernt werden.")),
  });
  const register = useMutation({
    mutationFn: async () => (await api.post(`/scoring/events/${eventId}/register-qualified`, { level_id: levelId })).data as unknown[],
    onSuccess: (created) => { onMessage(`${created.length} qualifizierte(s) Team(s) für dieses Event registriert.`); refresh(); },
    onError: (error: any) => onMessage(detail(error, "Registrierung fehlgeschlagen.")),
  });

  if (!targets.length) {
    return <section className="card p-5 lg:col-span-2"><h2 className="mb-2 flex items-center gap-2 text-lg font-semibold"><Award className="h-5 w-5" />Qualifikation</h2><p className="text-sm text-gray-500">Keine Stufe mit Qualifikation konfiguriert. Unter Einstellungen → Wettbewerbsstufen „Qualifiziert aus“ setzen (z. B. GCER aus ECER).</p></section>;
  }
  return (
    <section className="card p-5 lg:col-span-2" aria-labelledby="qualification-title">
      <h2 id="qualification-title" className="mb-1 flex items-center gap-2 text-lg font-semibold"><Award className="h-5 w-5" />Qualifikation {source ? `${source.name} → ` : ""}{level?.name}</h2>
      <p className="mb-3 text-sm text-gray-500">Manuelle Entscheidung durch Admins. Nur qualifizierte Teams können auf Stufe {level?.name} registriert werden.</p>
      {targets.length > 1 && <label className="mb-3 block text-sm font-medium">Zielstufe<select className="input mt-1" value={levelId} onChange={(e) => { setChosenLevel(e.target.value); setSelected([]); }}>{targets.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
      <ul className="mb-3 max-h-64 divide-y overflow-auto rounded border text-sm dark:divide-gray-800 dark:border-gray-700">
        {status.data?.map((entry) => (
          <li key={entry.team_id} className="flex items-center justify-between gap-2 p-2">
            <label className="flex items-center gap-2">
              {!entry.qualified && canQualify && <input type="checkbox" checked={selected.includes(entry.team_id)} onChange={(e) => setSelected(e.target.checked ? [...selected, entry.team_id] : selected.filter((id) => id !== entry.team_id))} />}
              <span>{entry.team_name}</span>
            </label>
            {entry.qualified ? (
              <span className="flex items-center gap-2"><span className="badge-green">qualifiziert</span>{entry.note && <span className="text-xs text-gray-500">{entry.note}</span>}{canQualify && entry.qualification_id && <button type="button" className="btn-secondary px-2" aria-label={`Qualifikation von ${entry.team_name} entfernen`} onClick={() => revoke.mutate(entry.qualification_id!)}><X className="h-4 w-4" /></button>}</span>
            ) : <span className="badge-gray">noch nicht freigeschaltet</span>}
          </li>
        ))}
        {status.data?.length === 0 && <li className="p-3 text-gray-500">Keine Teams der Ausgangsstufe in dieser Saison registriert.</li>}
      </ul>
      {canQualify && <div className="flex flex-wrap gap-2"><input className="input min-w-0 flex-1" placeholder="Notiz (z. B. ECER-Sieger)" value={note} onChange={(e) => setNote(e.target.value)} /><button type="button" className="btn-primary" disabled={!selected.length || qualify.isPending} onClick={() => qualify.mutate()}>Qualifizieren</button></div>}
      <button type="button" className="btn-secondary mt-3" disabled={register.isPending} onClick={() => register.mutate()}><UserPlus className="h-4 w-4" />Qualifizierte Teams für dieses Event registrieren</button>
    </section>
  );
}

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { Save, Trophy } from "lucide-react";
import { api } from "@/lib/api";
import { useOnlineStatus } from "@/hooks/useOnlineStatus";
import type { EventRegistration, RankingEntry, ScheduledMatch, ScoringField, ScoringSchema } from "@/api/types";

export default function EventScoringPage() {
  const { eventId = "" } = useParams();
  const online = useOnlineStatus();
  const queryClient = useQueryClient();
  const [teamId, setTeamId] = useState("");
  const [scheduledMatchId, setScheduledMatchId] = useState("");
  const [values, setValues] = useState<Record<string, number | boolean>>({});
  const [message, setMessage] = useState("");
  const registrations = useQuery<EventRegistration[]>({ queryKey: ["event-registrations", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/registrations`)).data });
  const schedule = useQuery<ScheduledMatch[]>({ queryKey: ["event-schedule", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/schedule`)).data });
  const schema = useQuery<ScoringSchema>({ queryKey: ["event-schema", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/scoring-schema`)).data, retry: false });
  const ranking = useQuery<RankingEntry[]>({ queryKey: ["event-ranking", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/ranking`)).data, refetchInterval: 10_000 });
  const total = useMemo(() => schema.data?.fields.reduce((sum, field) => sum + (Number(values[field.key] ?? 0) * field.multiplier), 0) ?? 0, [schema.data, values]);
  const save = useMutation({
    mutationFn: async () => api.post(`/v1/events/${eventId}/matches`, { team_id: teamId, scheduled_match_id: scheduledMatchId || null, raw_scores: values, idempotency_key: crypto.randomUUID() }),
    onSuccess: () => { setMessage("Wertung wurde offiziell gespeichert."); setValues({}); queryClient.invalidateQueries({ queryKey: ["event-ranking", eventId] }); },
    onError: (error: any) => setMessage(error.response?.data?.detail ?? "Speichern fehlgeschlagen."),
  });
  const schemaFields = schema.data?.fields;
  const sections = useMemo(() => {
    const grouped = new Map<string, ScoringField[]>();
    for (const field of schemaFields ?? []) { const section = field.section || "Wertung"; grouped.set(section, [...(grouped.get(section) ?? []), field]); }
    return grouped;
  }, [schemaFields]);
  if (schema.isError) return <div className="p-6"><div className="card p-8 text-center">Für dieses Event ist noch kein aktives Scoring-Schema konfiguriert.</div></div>;
  return (
    <div className="mx-auto max-w-3xl p-4 md:p-6"><h1 className="mb-6 flex items-center gap-2 text-2xl font-bold"><Trophy className="text-yellow-500" />Mobile Wertung</h1>
      <form className="space-y-5" onSubmit={(e) => { e.preventDefault(); setMessage(""); save.mutate(); }}>
        <div className="card grid gap-4 p-4 md:grid-cols-2"><label className="text-sm font-medium">Team<select required className="input mt-1 w-full" value={teamId} onChange={(e) => setTeamId(e.target.value)}><option value="">Team wählen</option>{registrations.data?.map((item) => <option key={item.id} value={item.team_id}>{item.seed_number ? `#${item.seed_number} · ` : ""}{item.team_id}</option>)}</select></label><label className="text-sm font-medium">Geplantes Match<select className="input mt-1 w-full" value={scheduledMatchId} onChange={(e) => setScheduledMatchId(e.target.value)}><option value="">Ohne Zuordnung</option>{schedule.data?.map((item) => <option key={item.id} value={item.id}>{item.code} · Tisch {item.table_number ?? "–"}</option>)}</select></label></div>
        {[...sections].map(([section, fields]) => <fieldset key={section} className="card p-4"><legend className="px-2 font-semibold">{section}</legend><div className="grid gap-4 sm:grid-cols-2">{fields.map((field) => <label key={field.key} className="text-sm font-medium">{field.label} <span className="text-xs text-gray-500">× {field.multiplier}</span>{field.type === "boolean" ? <input className="ml-3 h-5 w-5 align-middle" type="checkbox" checked={Boolean(values[field.key])} onChange={(e) => setValues((current) => ({ ...current, [field.key]: e.target.checked }))} /> : <input className="input mt-1 w-full text-lg" type="number" inputMode="decimal" required={field.required} min={field.min_value ?? undefined} max={field.max_value ?? undefined} value={String(values[field.key] ?? "")} onChange={(e) => setValues((current) => ({ ...current, [field.key]: Number(e.target.value) }))} />}</label>)}</div></fieldset>)}
        <div className="sticky bottom-0 card flex items-center justify-between gap-4 border-primary-200 p-4"><div><p className="text-sm text-gray-500">Berechnete Gesamtwertung</p><p className="text-3xl font-bold">{total.toFixed(2)}</p></div><button className="btn-primary flex min-h-12 items-center gap-2" disabled={!online || save.isPending || !teamId}><Save />Offiziell speichern</button></div>
        <p className="text-sm text-gray-500">Mit dem Speichern wird die Wertung sofort offiziell. Änderungen werden vollständig versioniert.</p>{message && <p role="status" className="rounded-lg bg-gray-100 p-3 text-sm dark:bg-gray-800">{message}</p>}
      </form>
      <section className="mt-8"><h2 className="mb-3 text-xl font-semibold">Aktuelle Rangliste</h2><div className="card overflow-x-auto"><table className="w-full text-sm"><thead className="bg-gray-100 dark:bg-gray-800"><tr><th className="p-3 text-left">#</th><th className="p-3 text-left">Team</th><th className="p-3 text-right">Seed</th><th className="p-3 text-right">Best</th></tr></thead><tbody>{ranking.data?.map((item) => <tr key={item.team_id} className="border-t dark:border-gray-800"><td className="p-3 font-bold">{item.rank}</td><td className="p-3 font-mono text-xs">{item.team_id}</td><td className="p-3 text-right">{item.seed_score.toFixed(2)}</td><td className="p-3 text-right">{item.best_score.toFixed(2)}</td></tr>)}</tbody></table></div></section>
    </div>
  );
}

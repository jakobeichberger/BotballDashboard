import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { Plus, Settings } from "lucide-react";
import { api } from "@/lib/api";
import { useEvent } from "@/hooks/useEvents";
import type { EventPhase, EventRegistration, ScoringField, ScoringSchema } from "@/api/types";

export default function EventSetupPage() {
  const { eventId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: event } = useEvent(eventId);
  const seasons = useQuery<any[]>({ queryKey: ["seasons"], queryFn: async () => (await api.get("/seasons")).data });
  const teams = useQuery<any[]>({ queryKey: ["teams"], queryFn: async () => (await api.get("/teams")).data });
  const phases = useQuery<EventPhase[]>({ queryKey: ["event-phases", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/phases`)).data, enabled: !!eventId });
  const registrations = useQuery<EventRegistration[]>({ queryKey: ["event-registrations", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/registrations`)).data, enabled: !!eventId });
  const schema = useQuery<ScoringSchema>({ queryKey: ["event-schema", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/scoring-schema`)).data, enabled: !!eventId, retry: false });
  const [form, setForm] = useState({ season_id: "", name: "", slug: "", timezone: "Europe/Vienna", venue: "", status: "draft", table_count: 1, public_scoreboard: false, public_schedule: false, public_results: false, public_announcements: false });
  const [phase, setPhase] = useState({ name: "", phase_type: "seeding", rounds: 3 });
  const [teamId, setTeamId] = useState("");
  const [schemaJson, setSchemaJson] = useState("[]");
  const [message, setMessage] = useState("");
  useEffect(() => { if (event) setForm((current) => ({ ...current, ...event, venue: event.venue ?? "" })); }, [event]);
  useEffect(() => { if (schema.data) setSchemaJson(JSON.stringify(schema.data.fields, null, 2)); }, [schema.data]);
  const saveEvent = useMutation({ mutationFn: async () => eventId ? api.patch(`/v1/events/${eventId}`, form) : api.post("/v1/events", form), onSuccess: ({ data }) => { queryClient.invalidateQueries({ queryKey: ["events"] }); setMessage("Event gespeichert."); if (!eventId) navigate(`/events/${data.id}/settings`, { replace: true }); }, onError: (error: any) => setMessage(error.response?.data?.detail ?? "Event konnte nicht gespeichert werden.") });
  const addPhase = useMutation({ mutationFn: async () => api.post(`/v1/events/${eventId}/phases`, { ...phase, sort_order: phases.data?.length ?? 0 }), onSuccess: () => { setPhase({ name: "", phase_type: "seeding", rounds: 3 }); queryClient.invalidateQueries({ queryKey: ["event-phases", eventId] }); } });
  const addTeam = useMutation({ mutationFn: async () => api.post(`/v1/events/${eventId}/registrations`, { team_id: teamId }), onSuccess: () => { setTeamId(""); queryClient.invalidateQueries({ queryKey: ["event-registrations", eventId] }); } });
  const saveSchema = useMutation({ mutationFn: async () => { const fields = JSON.parse(schemaJson) as ScoringField[]; return api.post(`/v1/events/${eventId}/scoring-schema/versions`, { fields, activate: true }); }, onSuccess: () => { setMessage("Neue Scoring-Schema-Version wurde aktiviert."); queryClient.invalidateQueries({ queryKey: ["event-schema", eventId] }); }, onError: (error: any) => setMessage(error instanceof SyntaxError ? "Schema-JSON ist ungültig." : error.response?.data?.detail ?? "Schema konnte nicht gespeichert werden.") });
  return (
    <div className="mx-auto max-w-6xl p-4 md:p-6"><h1 className="mb-6 flex items-center gap-2 text-2xl font-bold"><Settings />{eventId ? "Event-Verwaltung" : "Erstes Event einrichten"}</h1>
      <form className="card grid gap-4 p-5 md:grid-cols-2" onSubmit={(e) => { e.preventDefault(); saveEvent.mutate(); }}>
        {!eventId && <label className="text-sm font-medium">Saison<select required className="input mt-1 w-full" value={form.season_id} onChange={(e) => setForm({ ...form, season_id: e.target.value })}><option value="">Saison wählen</option>{seasons.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
        <label className="text-sm font-medium">Name<input required className="input mt-1 w-full" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        <label className="text-sm font-medium">Slug<input required className="input mt-1 w-full" value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") })} /></label>
        <label className="text-sm font-medium">Zeitzone<input required className="input mt-1 w-full" value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} /></label>
        <label className="text-sm font-medium">Ort<input className="input mt-1 w-full" value={form.venue} onChange={(e) => setForm({ ...form, venue: e.target.value })} /></label>
        <label className="text-sm font-medium">Status<select className="input mt-1 w-full" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>{["draft", "published", "live", "completed", "archived"].map((status) => <option key={status}>{status}</option>)}</select></label>
        <label className="text-sm font-medium">Tische<input type="number" min={1} className="input mt-1 w-full" value={form.table_count} onChange={(e) => setForm({ ...form, table_count: Number(e.target.value) })} /></label>
        <fieldset className="md:col-span-2"><legend className="mb-2 font-medium">Öffentliche Freigaben</legend><div className="flex flex-wrap gap-4">{(["public_scoreboard", "public_schedule", "public_results", "public_announcements"] as const).map((key) => <label key={key} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.checked })} />{key.replace("public_", "")}</label>)}</div></fieldset>
        <div className="md:col-span-2"><button className="btn-primary" disabled={saveEvent.isPending}>Event speichern</button></div>
      </form>
      {message && <p role="status" className="my-4 rounded-lg bg-gray-100 p-3 dark:bg-gray-800">{message}</p>}
      {eventId && <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <section className="card p-5"><h2 className="mb-4 text-lg font-semibold">Phasen</h2><ul className="mb-4 space-y-2">{phases.data?.map((item) => <li key={item.id} className="rounded bg-gray-50 p-2 text-sm dark:bg-gray-800">{item.sort_order + 1}. {item.name} · {item.phase_type}</li>)}</ul><form className="grid gap-2 sm:grid-cols-[1fr_1fr_5rem_auto]" onSubmit={(e) => { e.preventDefault(); addPhase.mutate(); }}><input required className="input" placeholder="Phasenname" value={phase.name} onChange={(e) => setPhase({ ...phase, name: e.target.value })} /><select className="input" value={phase.phase_type} onChange={(e) => setPhase({ ...phase, phase_type: e.target.value })}>{["seeding", "double_seeding", "double_elimination", "alliance", "final"].map((type) => <option key={type}>{type}</option>)}</select><input className="input" type="number" min={1} value={phase.rounds} onChange={(e) => setPhase({ ...phase, rounds: Number(e.target.value) })} /><button className="btn-secondary" aria-label="Phase hinzufügen"><Plus /></button></form></section>
        <section className="card p-5"><h2 className="mb-4 text-lg font-semibold">Teams ({registrations.data?.length ?? 0})</h2><form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); addTeam.mutate(); }}><select required className="input min-w-0 flex-1" value={teamId} onChange={(e) => setTeamId(e.target.value)}><option value="">Team registrieren</option>{teams.data?.filter((team) => !registrations.data?.some((item) => item.team_id === team.id)).map((team) => <option key={team.id} value={team.id}>{team.name}</option>)}</select><button className="btn-secondary"><Plus /></button></form><ul className="mt-4 max-h-52 space-y-1 overflow-auto text-sm">{registrations.data?.map((item) => <li key={item.id}>{teams.data?.find((team) => team.id === item.team_id)?.name ?? item.team_id}</li>)}</ul></section>
        <section className="card p-5 lg:col-span-2"><h2 className="mb-2 text-lg font-semibold">Versioniertes Scoring-Schema</h2><p className="mb-3 text-sm text-gray-500">Felder als JSON-Liste. Speichern erzeugt eine neue aktive Version; bestehende Matches behalten ihren Snapshot.</p><textarea className="input min-h-64 w-full font-mono text-xs" value={schemaJson} onChange={(e) => setSchemaJson(e.target.value)} /><button className="btn-primary mt-3" onClick={() => saveSchema.mutate()}>Neue Version aktivieren</button></section>
      </div>}
    </div>
  );
}

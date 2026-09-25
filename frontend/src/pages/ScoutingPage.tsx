import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { FileDown, Plus, Telescope, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { useEvent } from "@/hooks/useEvents";
import { useAuthStore } from "@/store/authStore";
import type { ExternalTeam, OpponentRankingEntry, ScoutingNote, ScoutingObservation } from "@/modules/scoring/extras/types";

interface OwnTeam { id: string; name: string }

/**
 * Scouting of teams that are not managed in the system: observed scores and
 * notes per event, the combined opponent ranking and the PDF report.
 * Mentors work with their own team's notes; organizers see everything.
 */
export default function ScoutingPage() {
  const { eventId = "" } = useParams();
  const { data: event } = useEvent(eventId);
  const seasonId = event?.season_id;
  const queryClient = useQueryClient();
  const canWrite = useAuthStore((state) => state.hasPermission("scoring:write"));
  const isOrganizer = useAuthStore((state) => state.hasPermission("scoring:admin"));
  const [selected, setSelected] = useState("");
  const [message, setMessage] = useState("");
  const [newTeam, setNewTeam] = useState({ name: "", number: "", country: "" });
  const [ownerTeamId, setOwnerTeamId] = useState("");
  const [note, setNote] = useState({ body: "", threat_level: "" });
  const [observation, setObservation] = useState({ score: "", round_number: "", phase: "seeding", notes: "" });

  const teams = useQuery<ExternalTeam[]>({ queryKey: ["external-teams", seasonId], queryFn: async () => (await api.get(`/scoring/seasons/${seasonId}/external-teams`)).data, enabled: !!seasonId });
  const ranking = useQuery<OpponentRankingEntry[]>({ queryKey: ["opponent-ranking", eventId], queryFn: async () => (await api.get(`/scoring/events/${eventId}/opponent-ranking`)).data, enabled: !!eventId });
  const notes = useQuery<ScoutingNote[]>({ queryKey: ["scouting-notes", eventId, selected], queryFn: async () => (await api.get(`/scoring/events/${eventId}/scouting/notes`, { params: { external_team_id: selected } })).data, enabled: !!selected });
  const observations = useQuery<ScoutingObservation[]>({ queryKey: ["scouting-observations", eventId, selected], queryFn: async () => (await api.get(`/scoring/events/${eventId}/scouting/observations`, { params: { external_team_id: selected } })).data, enabled: !!selected });
  const myTeams = useQuery<OwnTeam[]>({ queryKey: ["teams-mine"], queryFn: async () => (await api.get("/teams/mine")).data, enabled: canWrite && !isOrganizer });
  const selectedTeam = useMemo(() => teams.data?.find((team) => team.id === selected), [teams.data, selected]);
  const owner = ownerTeamId || (myTeams.data?.length === 1 ? myTeams.data[0].id : "");

  const refresh = () => ["external-teams", "opponent-ranking", "scouting-notes", "scouting-observations"].forEach((key) => queryClient.invalidateQueries({ queryKey: [key] }));
  const fail = (error: any) => setMessage(typeof error.response?.data?.detail === "string" ? error.response.data.detail : "Aktion fehlgeschlagen.");
  const createTeam = useMutation({
    mutationFn: async () => (await api.post("/scoring/external-teams", { season_id: seasonId, name: newTeam.name, number: newTeam.number || null, country: newTeam.country || null })).data as ExternalTeam,
    onSuccess: (team) => { setNewTeam({ name: "", number: "", country: "" }); setSelected(team.id); refresh(); },
    onError: fail,
  });
  const addNote = useMutation({
    mutationFn: async () => api.post(`/scoring/events/${eventId}/scouting/notes`, { external_team_id: selected, owner_team_id: owner || null, body: note.body, threat_level: note.threat_level ? Number(note.threat_level) : null }),
    onSuccess: () => { setNote({ body: "", threat_level: "" }); refresh(); },
    onError: fail,
  });
  const addObservation = useMutation({
    mutationFn: async () => api.post(`/scoring/events/${eventId}/scouting/observations`, { external_team_id: selected, owner_team_id: owner || null, score: Number(observation.score), round_number: observation.round_number ? Number(observation.round_number) : null, phase: observation.phase, notes: observation.notes || null }),
    onSuccess: () => { setObservation({ ...observation, score: "", notes: "" }); refresh(); },
    onError: fail,
  });
  const removeNote = useMutation({ mutationFn: async (id: string) => api.delete(`/scoring/scouting/notes/${id}`), onSuccess: refresh, onError: fail });
  const removeObservation = useMutation({ mutationFn: async (id: string) => api.delete(`/scoring/scouting/observations/${id}`), onSuccess: refresh, onError: fail });
  const exportPdf = async () => {
    try {
      const response = await api.get(`/scoring/events/${eventId}/scouting/report.pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(response.data as Blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `scouting-${event?.slug ?? eventId}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) { fail(error); }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 md:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="flex items-center gap-2 text-2xl font-bold"><Telescope />Scouting & Gegner</h1>
        <button type="button" className="btn-secondary" onClick={exportPdf}><FileDown className="h-4 w-4" />Scouting-Bericht (PDF)</button>
      </div>
      {message && <p role="status" className="rounded-lg bg-gray-100 p-3 text-sm dark:bg-gray-800">{message}</p>}

      <section className="card overflow-x-auto" aria-labelledby="opponent-ranking-title">
        <h2 id="opponent-ranking-title" className="border-b px-4 py-3 font-semibold dark:border-gray-800">Gegner-Rangliste</h2>
        <p className="px-4 pt-2 text-xs text-gray-500">Eigene Teams mit offiziellem Seeding-Score, externe Teams mit dem Schnitt der besten zwei beobachteten Läufe.</p>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800"><tr><th className="p-3 text-left">#</th><th className="p-3 text-left">Team</th><th className="p-3 text-left">Land</th><th className="p-3 text-left">Quelle</th><th className="p-3 text-right">Seed</th><th className="p-3 text-right">Best</th><th className="p-3 text-right">Läufe</th></tr></thead>
          <tbody>
            {ranking.data?.map((entry) => (
              <tr key={`${entry.kind}-${entry.team_id}`} className={`border-t dark:border-gray-800 ${entry.kind === "internal" ? "bg-primary-50/50 dark:bg-primary-900/20" : ""}`}>
                <td className="p-3 font-bold">{entry.rank}</td>
                <td className="p-3">{entry.kind === "external" ? <button type="button" className="text-left underline-offset-2 hover:underline" onClick={() => setSelected(entry.team_id)}>{entry.team_name}</button> : entry.team_name}{entry.team_number && <span className="ml-1 text-xs text-gray-500">({entry.team_number})</span>}</td>
                <td className="p-3">{entry.country ?? "–"}</td>
                <td className="p-3">{entry.kind === "internal" ? <span className="badge-green">eigenes Team</span> : <span className="badge-gray">beobachtet</span>}</td>
                <td className="p-3 text-right font-semibold">{entry.seed_score.toFixed(1)}</td>
                <td className="p-3 text-right">{entry.best_score.toFixed(1)}</td>
                <td className="p-3 text-right">{entry.runs}</td>
              </tr>
            ))}
            {ranking.data?.length === 0 && <tr><td colSpan={7} className="p-6 text-center text-gray-400">Noch keine Scores erfasst.</td></tr>}
          </tbody>
        </table>
      </section>

      <div className="grid gap-6 lg:grid-cols-[18rem_1fr]">
        <section className="card p-4" aria-labelledby="external-teams-title">
          <h2 id="external-teams-title" className="mb-3 font-semibold">Externe Teams</h2>
          <ul className="mb-4 max-h-80 space-y-1 overflow-auto text-sm">
            {teams.data?.map((team) => <li key={team.id}><button type="button" className={`w-full rounded px-2 py-1 text-left ${team.id === selected ? "bg-primary-600 text-white" : "hover:bg-gray-100 dark:hover:bg-gray-800"}`} onClick={() => setSelected(team.id)}>{team.name}{team.number ? ` · ${team.number}` : ""}</button></li>)}
            {teams.data?.length === 0 && <li className="text-gray-400">Noch keine externen Teams.</li>}
          </ul>
          {canWrite && (
            <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); createTeam.mutate(); }}>
              <input required aria-label="Teamname" className="input w-full" placeholder="Teamname" value={newTeam.name} onChange={(e) => setNewTeam({ ...newTeam, name: e.target.value })} />
              <div className="flex gap-2"><input aria-label="Teamnummer" className="input min-w-0 flex-1" placeholder="Nummer" value={newTeam.number} onChange={(e) => setNewTeam({ ...newTeam, number: e.target.value })} /><input aria-label="Land" className="input w-20" placeholder="Land" value={newTeam.country} onChange={(e) => setNewTeam({ ...newTeam, country: e.target.value })} /></div>
              <button className="btn-secondary w-full" disabled={!newTeam.name || createTeam.isPending || !seasonId}><Plus className="h-4 w-4" />Team erfassen</button>
            </form>
          )}
        </section>

        <section className="card p-4" aria-live="polite">
          {!selectedTeam ? <p className="text-gray-500">Team auswählen, um Beobachtungen und Notizen zu sehen.</p> : (
            <div className="space-y-5">
              <div>
                <h2 className="text-lg font-semibold">{selectedTeam.name}</h2>
                <p className="text-sm text-gray-500">{[selectedTeam.number, selectedTeam.country, selectedTeam.school].filter(Boolean).join(" · ")}</p>
              </div>
              {canWrite && !isOrganizer && (myTeams.data?.length ?? 0) > 1 && <label className="block text-sm font-medium">Für Team<select className="input mt-1" value={ownerTeamId} onChange={(e) => setOwnerTeamId(e.target.value)}><option value="">Team wählen</option>{myTeams.data?.map((team) => <option key={team.id} value={team.id}>{team.name}</option>)}</select></label>}
              <div>
                <h3 className="mb-2 font-medium">Beobachtete Scores</h3>
                <ul className="mb-2 divide-y text-sm dark:divide-gray-800">
                  {observations.data?.map((obs) => <li key={obs.id} className="flex items-center justify-between py-1"><span>{obs.phase}{obs.round_number ? ` · Runde ${obs.round_number}` : ""}: <strong>{obs.score}</strong>{obs.notes ? ` – ${obs.notes}` : ""}</span>{canWrite && <button type="button" className="btn-secondary px-2" aria-label="Beobachtung löschen" onClick={() => removeObservation.mutate(obs.id)}><Trash2 className="h-4 w-4" /></button>}</li>)}
                  {observations.data?.length === 0 && <li className="py-1 text-gray-400">Keine Beobachtungen.</li>}
                </ul>
                {canWrite && (
                  <form className="grid gap-2 sm:grid-cols-[8rem_6rem_6rem_1fr_auto]" onSubmit={(e) => { e.preventDefault(); addObservation.mutate(); }}>
                    <select aria-label="Phase" className="input" value={observation.phase} onChange={(e) => setObservation({ ...observation, phase: e.target.value })}>{["seeding", "double_seeding", "double_elimination", "alliance", "other"].map((phase) => <option key={phase}>{phase}</option>)}</select>
                    <input aria-label="Runde" className="input" type="number" min={1} placeholder="Runde" value={observation.round_number} onChange={(e) => setObservation({ ...observation, round_number: e.target.value })} />
                    <input required aria-label="Punkte" className="input" type="number" placeholder="Punkte" value={observation.score} onChange={(e) => setObservation({ ...observation, score: e.target.value })} />
                    <input aria-label="Notiz zur Beobachtung" className="input" placeholder="Notiz" value={observation.notes} onChange={(e) => setObservation({ ...observation, notes: e.target.value })} />
                    <button className="btn-secondary" disabled={addObservation.isPending || observation.score === ""}><Plus className="h-4 w-4" /></button>
                  </form>
                )}
              </div>
              <div>
                <h3 className="mb-2 font-medium">Notizen</h3>
                <ul className="mb-2 space-y-2 text-sm">
                  {notes.data?.map((item) => <li key={item.id} className="rounded bg-gray-50 p-2 dark:bg-gray-800"><div className="flex items-start justify-between gap-2"><p className="whitespace-pre-wrap">{item.body}</p>{canWrite && <button type="button" className="btn-secondary px-2" aria-label="Notiz löschen" onClick={() => removeNote.mutate(item.id)}><Trash2 className="h-4 w-4" /></button>}</div>{item.threat_level && <p className="text-xs text-gray-500">Einschätzung {item.threat_level}/5</p>}</li>)}
                  {notes.data?.length === 0 && <li className="text-gray-400">Keine Notizen.</li>}
                </ul>
                {canWrite && (
                  <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); addNote.mutate(); }}>
                    <textarea required aria-label="Notiz" className="input w-full" placeholder="Stärken, Schwächen, Strategie …" value={note.body} onChange={(e) => setNote({ ...note, body: e.target.value })} />
                    <div className="flex gap-2"><select aria-label="Einschätzung" className="input" value={note.threat_level} onChange={(e) => setNote({ ...note, threat_level: e.target.value })}><option value="">Einschätzung</option>{[1, 2, 3, 4, 5].map((level) => <option key={level} value={level}>{level}/5</option>)}</select><button className="btn-primary" disabled={!note.body || addNote.isPending}>Notiz speichern</button></div>
                  </form>
                )}
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

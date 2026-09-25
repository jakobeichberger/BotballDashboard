import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { FileDown, Pencil, Plus, Telescope, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { useEvent } from "@/hooks/useEvents";
import { useAuthStore } from "@/store/authStore";
import { phaseLabel } from "@/api/analytics";
import { formatNumber } from "@/i18n/format";
import type { ExternalTeam, OpponentRankingEntry, ScoutingNote, ScoutingObservation } from "@/modules/scoring/extras/types";
import { confirmAction } from "@/lib/confirm";
import { apiErrorMessage } from "@/lib/errors";

interface OwnTeam { id: string; name: string }

/**
 * Scouting of teams that are not managed in the system: observed scores and
 * notes per event, the combined opponent ranking and the PDF report.
 * Mentors work with their own team's notes; organizers see everything.
 */
const oneDecimal = { minimumFractionDigits: 1, maximumFractionDigits: 1 };

export default function ScoutingPage() {
  const { t } = useTranslation("scoring");
  const { eventId = "" } = useParams();
  const { data: event } = useEvent(eventId);
  const seasonId = event?.season_id;
  const queryClient = useQueryClient();
  const canWrite = useAuthStore((state) => state.hasPermission("scoring:write"));
  const isOrganizer = useAuthStore((state) => state.hasPermission("scoring:admin"));
  const userId = useAuthStore((state) => state.user?.id);
  const [selected, setSelected] = useState("");
  const [message, setMessage] = useState("");
  const [newTeam, setNewTeam] = useState({ name: "", number: "", country: "" });
  const [ownerTeamId, setOwnerTeamId] = useState("");
  const [note, setNote] = useState({ body: "", threat_level: "" });
  const [observation, setObservation] = useState({ score: "", round_number: "", phase: "seeding", notes: "" });
  const [teamEdit, setTeamEdit] = useState<{ name: string; number: string; country: string; school: string; notes: string } | null>(null);
  useEffect(() => setTeamEdit(null), [selected]);

  const teams = useQuery<ExternalTeam[]>({ queryKey: ["external-teams", seasonId], queryFn: async () => (await api.get(`/scoring/seasons/${seasonId}/external-teams`)).data, enabled: !!seasonId });
  const ranking = useQuery<OpponentRankingEntry[]>({ queryKey: ["opponent-ranking", eventId], queryFn: async () => (await api.get(`/scoring/events/${eventId}/opponent-ranking`)).data, enabled: !!eventId });
  const notes = useQuery<ScoutingNote[]>({ queryKey: ["scouting-notes", eventId, selected], queryFn: async () => (await api.get(`/scoring/events/${eventId}/scouting/notes`, { params: { external_team_id: selected } })).data, enabled: !!selected });
  const observations = useQuery<ScoutingObservation[]>({ queryKey: ["scouting-observations", eventId, selected], queryFn: async () => (await api.get(`/scoring/events/${eventId}/scouting/observations`, { params: { external_team_id: selected } })).data, enabled: !!selected });
  const myTeams = useQuery<OwnTeam[]>({ queryKey: ["teams-mine"], queryFn: async () => (await api.get("/teams/mine")).data, enabled: canWrite && !isOrganizer });
  const selectedTeam = useMemo(() => teams.data?.find((team) => team.id === selected), [teams.data, selected]);
  // The backend lets organizers and the team's creator edit; only organizers delete.
  const canEditTeam = !!selectedTeam && canWrite && (isOrganizer || (!!userId && selectedTeam.created_by === userId));
  const owner = ownerTeamId || (myTeams.data?.length === 1 ? myTeams.data[0].id : "");

  const refresh = () => ["external-teams", "opponent-ranking", "scouting-notes", "scouting-observations"].forEach((key) => queryClient.invalidateQueries({ queryKey: [key] }));
  const fail = (error: unknown) => setMessage(apiErrorMessage(error, t("common:actionFailed")));
  const createTeam = useMutation({
    mutationFn: async () => (await api.post("/scoring/external-teams", { season_id: seasonId, name: newTeam.name, number: newTeam.number || null, country: newTeam.country || null })).data as ExternalTeam,
    onSuccess: (team) => { setNewTeam({ name: "", number: "", country: "" }); setSelected(team.id); refresh(); },
    onError: fail,
  });
  const updateTeam = useMutation({
    mutationFn: async () => api.patch(`/scoring/external-teams/${selected}`, {
      name: teamEdit!.name,
      number: teamEdit!.number || null,
      country: teamEdit!.country || null,
      school: teamEdit!.school || null,
      notes: teamEdit!.notes || null,
    }),
    onSuccess: () => { setTeamEdit(null); setMessage(""); refresh(); },
    onError: fail,
  });
  const deleteTeam = useMutation({
    mutationFn: async () => api.delete(`/scoring/external-teams/${selected}`),
    onSuccess: () => { setSelected(""); setTeamEdit(null); setMessage(""); refresh(); },
    onError: fail,
  });
  const startTeamEdit = (team: ExternalTeam) => setTeamEdit({ name: team.name, number: team.number ?? "", country: team.country ?? "", school: team.school ?? "", notes: team.notes ?? "" });
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
        <h1 className="flex items-center gap-2 text-2xl font-bold"><Telescope />{t("scouting.title")}</h1>
        <button type="button" className="btn-secondary" onClick={exportPdf}><FileDown className="h-4 w-4" />{t("scouting.report")}</button>
      </div>
      {message && <p role="status" className="rounded-lg bg-flaeche-2 p-3 text-sm">{message}</p>}

      <section className="card overflow-x-auto" aria-labelledby="opponent-ranking-title">
        <h2 id="opponent-ranking-title" className="border-b px-4 py-3 font-semibold">{t("scouting.ranking")}</h2>
        <p className="px-4 pt-2 text-xs text-leise">{t("scouting.rankingHint")}</p>
        <div className="table-scroll">
        <table className="w-full text-sm">
          <thead className="bg-flaeche-2"><tr><th className="p-3 text-left">#</th><th className="p-3 text-left">{t("scouting.team")}</th><th className="p-3 text-left">{t("scouting.country")}</th><th className="p-3 text-left">{t("scouting.source")}</th><th className="p-3 text-right">{t("scouting.seed")}</th><th className="p-3 text-right">{t("scouting.best")}</th><th className="p-3 text-right">{t("scouting.runs")}</th></tr></thead>
          <tbody>
            {ranking.data?.map((entry) => (
              <tr key={`${entry.kind}-${entry.team_id}`} className={`border-t ${entry.kind === "internal" ? "bg-primary-50/50 dark:bg-primary-900/20" : ""}`}>
                <td className="p-3 font-bold">{entry.rank}</td>
                <td className="p-3">{entry.kind === "external" ? <button type="button" className="text-left underline-offset-2 hover:underline" onClick={() => setSelected(entry.team_id)}>{entry.team_name}</button> : entry.team_name}{entry.team_number && <span className="ml-1 text-xs text-leise">({entry.team_number})</span>}</td>
                <td className="p-3">{entry.country ?? "–"}</td>
                <td className="p-3">{entry.kind === "internal" ? <span className="badge-green">{t("scouting.ownTeam")}</span> : <span className="badge-gray">{t("scouting.observed")}</span>}</td>
                <td className="p-3 text-right font-semibold">{formatNumber(entry.seed_score, oneDecimal)}</td>
                <td className="p-3 text-right">{formatNumber(entry.best_score, oneDecimal)}</td>
                <td className="p-3 text-right">{entry.runs}</td>
              </tr>
            ))}
            {ranking.data?.length === 0 && <tr><td colSpan={7} className="p-6 text-center text-leise">{t("scouting.noScores")}</td></tr>}
          </tbody>
        </table>
      </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-[18rem_1fr]">
        <section className="card p-4" aria-labelledby="external-teams-title">
          <h2 id="external-teams-title" className="mb-3 font-semibold">{t("scouting.externalTeams")}</h2>
          <ul className="mb-4 max-h-80 space-y-1 overflow-auto text-sm">
            {teams.data?.map((team) => <li key={team.id}><button type="button" className={`w-full rounded px-2 py-1 text-left ${team.id === selected ? "bg-primary-600 text-white" : "hover:bg-gray-100 dark:hover:bg-gray-800"}`} onClick={() => setSelected(team.id)}>{team.name}{team.number ? ` · ${team.number}` : ""}</button></li>)}
            {teams.data?.length === 0 && <li className="text-leise">{t("scouting.noExternalTeams")}</li>}
          </ul>
          {canWrite && (
            <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); createTeam.mutate(); }}>
              <input required aria-label={t("scouting.teamName")} className="input w-full" placeholder={t("scouting.teamName")} value={newTeam.name} onChange={(e) => setNewTeam({ ...newTeam, name: e.target.value })} />
              <div className="flex gap-2"><input aria-label={t("scouting.teamNumber")} className="input min-w-0 flex-1" placeholder={t("scouting.number")} value={newTeam.number} onChange={(e) => setNewTeam({ ...newTeam, number: e.target.value })} /><input aria-label={t("scouting.country")} className="input w-20" placeholder={t("scouting.country")} value={newTeam.country} onChange={(e) => setNewTeam({ ...newTeam, country: e.target.value })} /></div>
              <button className="btn-secondary w-full" disabled={!newTeam.name || createTeam.isPending || !seasonId}><Plus className="h-4 w-4" />{t("scouting.addTeam")}</button>
            </form>
          )}
        </section>

        <section className="card p-4" aria-live="polite">
          {!selectedTeam ? <p className="text-leise">{t("scouting.selectTeam")}</p> : (
            <div className="space-y-5">
              {teamEdit ? (
                <form className="grid gap-2 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); updateTeam.mutate(); }}>
                  <label className="text-sm font-medium sm:col-span-2">{t("scouting.teamName")}<input required maxLength={255} className="input mt-1 w-full" value={teamEdit.name} onChange={(e) => setTeamEdit({ ...teamEdit, name: e.target.value })} /></label>
                  <label className="text-sm font-medium">{t("scouting.teamNumber")}<input maxLength={50} className="input mt-1 w-full" value={teamEdit.number} onChange={(e) => setTeamEdit({ ...teamEdit, number: e.target.value })} /></label>
                  <label className="text-sm font-medium">{t("scouting.country")}<input maxLength={100} className="input mt-1 w-full" value={teamEdit.country} onChange={(e) => setTeamEdit({ ...teamEdit, country: e.target.value })} /></label>
                  <label className="text-sm font-medium sm:col-span-2">{t("scouting.school")}<input maxLength={255} className="input mt-1 w-full" value={teamEdit.school} onChange={(e) => setTeamEdit({ ...teamEdit, school: e.target.value })} /></label>
                  <label className="text-sm font-medium sm:col-span-2">{t("scouting.teamNotes")}<textarea maxLength={5000} className="input mt-1 w-full" value={teamEdit.notes} onChange={(e) => setTeamEdit({ ...teamEdit, notes: e.target.value })} /></label>
                  <div className="flex gap-2 sm:col-span-2">
                    <button className="btn-primary" disabled={!teamEdit.name.trim() || updateTeam.isPending}>{t("common:save")}</button>
                    <button type="button" className="btn-secondary" onClick={() => setTeamEdit(null)}>{t("common:cancel")}</button>
                  </div>
                </form>
              ) : (
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <h2 className="text-lg font-semibold">{selectedTeam.name}</h2>
                    <p className="text-sm text-leise">{[selectedTeam.number, selectedTeam.country, selectedTeam.school].filter(Boolean).join(" · ")}</p>
                    {selectedTeam.notes && <p className="mt-1 whitespace-pre-wrap text-sm text-leise">{selectedTeam.notes}</p>}
                  </div>
                  <div className="flex gap-1">
                    {canEditTeam && <button type="button" className="btn-secondary px-2" aria-label={t("scouting.editTeam", { name: selectedTeam.name })} onClick={() => startTeamEdit(selectedTeam)}><Pencil className="h-4 w-4" /></button>}
                    {isOrganizer && <button type="button" className="btn-secondary px-2 text-red-600" aria-label={t("scouting.deleteTeam", { name: selectedTeam.name })} disabled={deleteTeam.isPending} onClick={() => void confirmAction({ message: t("scouting.confirmDeleteTeam", { name: selectedTeam.name }), tone: "danger" }).then((ok) => ok && deleteTeam.mutate())}><Trash2 className="h-4 w-4" /></button>}
                  </div>
                </div>
              )}
              {canWrite && !isOrganizer && (myTeams.data?.length ?? 0) > 1 && <label className="block text-sm font-medium">{t("scouting.forTeam")}<select className="input mt-1" value={ownerTeamId} onChange={(e) => setOwnerTeamId(e.target.value)}><option value="">{t("scouting.chooseTeam")}</option>{myTeams.data?.map((team) => <option key={team.id} value={team.id}>{team.name}</option>)}</select></label>}
              <div>
                <h3 className="mb-2 font-medium">{t("scouting.observedScores")}</h3>
                <ul className="mb-2 divide-y text-sm">
                  {observations.data?.map((obs) => <li key={obs.id} className="flex items-center justify-between py-1"><span>{phaseLabel(obs.phase)}{obs.round_number ? ` · ${t("scouting.round", { round: obs.round_number })}` : ""}: <strong>{obs.score}</strong>{obs.notes ? ` – ${obs.notes}` : ""}</span>{canWrite && <button type="button" className="btn-secondary min-h-11 min-w-11 justify-center px-2" aria-label={t("scouting.deleteObservation")} onClick={() => void confirmAction({ message: t("scouting.confirmDeleteObservation", { score: obs.score }), tone: "danger" }).then((ok) => ok && removeObservation.mutate(obs.id))}><Trash2 className="h-4 w-4" aria-hidden="true" /></button>}</li>)}
                  {observations.data?.length === 0 && <li className="py-1 text-leise">{t("scouting.noObservations")}</li>}
                </ul>
                {canWrite && (
                  <form className="grid gap-2 sm:grid-cols-[8rem_6rem_6rem_1fr_auto]" onSubmit={(e) => { e.preventDefault(); addObservation.mutate(); }}>
                    <select aria-label={t("scouting.phase")} className="input" value={observation.phase} onChange={(e) => setObservation({ ...observation, phase: e.target.value })}>{["seeding", "double_seeding", "double_elimination", "alliance", "other"].map((phase) => <option key={phase} value={phase}>{phaseLabel(phase)}</option>)}</select>
                    <input aria-label={t("scouting.roundLabel")} className="input" type="number" min={1} placeholder={t("scouting.roundLabel")} value={observation.round_number} onChange={(e) => setObservation({ ...observation, round_number: e.target.value })} />
                    <input required aria-label={t("scouting.points")} className="input" type="number" placeholder={t("scouting.points")} value={observation.score} onChange={(e) => setObservation({ ...observation, score: e.target.value })} />
                    <input aria-label={t("scouting.observationNote")} className="input" placeholder={t("scouting.note")} value={observation.notes} onChange={(e) => setObservation({ ...observation, notes: e.target.value })} />
                    <button className="btn-secondary" disabled={addObservation.isPending || observation.score === ""}><Plus className="h-4 w-4" /></button>
                  </form>
                )}
              </div>
              <div>
                <h3 className="mb-2 font-medium">{t("scouting.notes")}</h3>
                <ul className="mb-2 space-y-2 text-sm">
                  {notes.data?.map((item) => <li key={item.id} className="rounded bg-flaeche-2 p-2"><div className="flex items-start justify-between gap-2"><p className="whitespace-pre-wrap">{item.body}</p>{canWrite && <button type="button" className="btn-secondary min-h-11 min-w-11 justify-center px-2" aria-label={t("scouting.deleteNote")} onClick={() => void confirmAction({ message: t("scouting.confirmDeleteNote"), tone: "danger" }).then((ok) => ok && removeNote.mutate(item.id))}><Trash2 className="h-4 w-4" aria-hidden="true" /></button>}</div>{item.threat_level && <p className="text-xs text-leise">{t("scouting.threatValue", { level: item.threat_level })}</p>}</li>)}
                  {notes.data?.length === 0 && <li className="text-leise">{t("scouting.noNotes")}</li>}
                </ul>
                {canWrite && (
                  <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); addNote.mutate(); }}>
                    <textarea required aria-label={t("scouting.note")} className="input w-full" placeholder={t("scouting.notePlaceholder")} value={note.body} onChange={(e) => setNote({ ...note, body: e.target.value })} />
                    <div className="flex gap-2"><select aria-label={t("scouting.threat")} className="input" value={note.threat_level} onChange={(e) => setNote({ ...note, threat_level: e.target.value })}><option value="">{t("scouting.threat")}</option>{[1, 2, 3, 4, 5].map((level) => <option key={level} value={level}>{level}/5</option>)}</select><button className="btn-primary" disabled={!note.body || addNote.isPending}>{t("scouting.saveNote")}</button></div>
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

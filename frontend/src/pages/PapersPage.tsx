import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { useParams } from "react-router-dom";
import { api } from "@/lib/api";
import Modal from "@/components/Modal";
import { useEvent } from "@/hooks/useEvents";
import { useAuthStore } from "@/store/authStore";
import type { EventRegistration } from "@/api/types";

const STATUS_BADGE: Record<string, string> = {
  draft: "badge-gray",
  submitted: "badge-blue",
  under_review: "badge-yellow",
  accepted: "badge-green",
  rejected: "badge-red",
  revision_requested: "badge-yellow",
};

const STATUS_LABEL: Record<string, string> = {
  draft: "Entwurf",
  submitted: "Eingereicht",
  under_review: "In Prüfung",
  accepted: "Angenommen",
  rejected: "Abgelehnt",
  revision_requested: "Überarbeitung",
};

export default function PapersPage() {
  const { eventId = "" } = useParams();
  const { data: event } = useEvent(eventId);
  const canWrite = useAuthStore((state) => state.hasPermission("papers:write"));
  const canAdmin = useAuthStore((state) => state.hasPermission("papers:admin"));
  const canReview = useAuthStore((state) => state.hasPermission("papers:review"));
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ team_id: "", title: "", abstract: "" });
  const [file, setFile] = useState<File | null>(null);
  const [selectedPaperId, setSelectedPaperId] = useState("");
  const [assignment, setAssignment] = useState({ reviewer_id: "", due_at: "" });
  const [review, setReview] = useState({ score_content: "", score_methodology: "", score_presentation: "", score_originality: "", comments: "" });
  const { data: registrations } = useQuery<EventRegistration[]>({
    queryKey: ["event-registrations", eventId],
    queryFn: async () => (await api.get(`/v1/events/${eventId}/registrations`)).data,
    enabled: !!eventId,
  });
  const { data: papers, isLoading } = useQuery({
    queryKey: ["papers", eventId],
    queryFn: async () => {
      const { data } = await api.get("/papers", { params: { event_id: eventId } });
      return data;
    },
  });
  const { data: workload } = useQuery<any[]>({ queryKey: ["paper-workload", eventId], queryFn: async () => (await api.get("/papers/reviewers/workload", { params: { event_id: eventId } })).data, enabled: canAdmin });
  const { data: users } = useQuery<any[]>({ queryKey: ["users"], queryFn: async () => (await api.get("/auth/users")).data, enabled: canAdmin });
  const paperDetail = useQuery<any>({ queryKey: ["paper", selectedPaperId], queryFn: async () => (await api.get(`/papers/${selectedPaperId}`)).data, enabled: !!selectedPaperId });
  const paperHistory = useQuery<any[]>({ queryKey: ["paper-history", selectedPaperId], queryFn: async () => (await api.get(`/papers/${selectedPaperId}/history`)).data, enabled: !!selectedPaperId });

  const createPaper = useMutation({
    mutationFn: async () => {
      const { data } = await api.post("/papers", { ...form, season_id: event?.season_id, event_id: eventId });
      if (file) {
        const body = new FormData();
        body.append("file", file);
        await api.post(`/papers/${data.id}/upload`, body);
      }
      await api.put(`/papers/${data.id}/submit`);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["papers", eventId] });
      setForm({ team_id: "", title: "", abstract: "" });
      setFile(null);
      setOpen(false);
    },
  });
  const assignReviewer = useMutation({ mutationFn: () => api.post(`/papers/${selectedPaperId}/assignments`, { reviewer_id: assignment.reviewer_id, due_at: assignment.due_at ? new Date(assignment.due_at).toISOString() : null }), onSuccess: () => { setAssignment({ reviewer_id: "", due_at: "" }); queryClient.invalidateQueries({ queryKey: ["paper", selectedPaperId] }); queryClient.invalidateQueries({ queryKey: ["paper-workload", eventId] }); } });
  const remindReviewer = useMutation({ mutationFn: (assignmentId: string) => api.post(`/papers/${selectedPaperId}/assignments/${assignmentId}/remind`), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["paper", selectedPaperId] }) });
  const setStatus = useMutation({ mutationFn: (status: string) => api.put(`/papers/${selectedPaperId}/status`, null, { params: { status } }), onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["paper", selectedPaperId] }); queryClient.invalidateQueries({ queryKey: ["paper-history", selectedPaperId] }); queryClient.invalidateQueries({ queryKey: ["papers", eventId] }); } });
  const submitReview = useMutation({ mutationFn: () => api.put(`/papers/${selectedPaperId}/reviews`, Object.fromEntries(Object.entries(review).map(([key, value]) => [key, key === "comments" ? value : value === "" ? null : Number(value)])), { params: { submit: true } }), onSuccess: () => { setReview({ score_content: "", score_methodology: "", score_presentation: "", score_originality: "", comments: "" }); queryClient.invalidateQueries({ queryKey: ["paper", selectedPaperId] }); } });

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <FileText className="w-6 h-6" />
          Paper Review
        </h1>
        {canWrite && <button onClick={() => setOpen(true)} className="btn-primary">+ Paper einreichen</button>}
      </div>

      {isLoading && <p className="text-gray-500">Laden...</p>}

      {canAdmin && workload && <section className="mb-6"><h2 className="mb-2 text-lg font-semibold">Reviewer-Auslastung</h2><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{workload.map((item) => <div key={item.reviewer_id} className="card p-3 text-sm"><p className="font-semibold">{users?.find((user) => user.id === item.reviewer_id)?.display_name ?? item.reviewer_id}</p><p className="text-gray-500">{item.open} offen · {item.overdue} überfällig · {item.completed} erledigt</p></div>)}</div></section>}

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Titel</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Status</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Rev.</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Eingereicht</th>
            </tr>
          </thead>
          <tbody className="divide-y dark:divide-gray-800">
            {papers?.map((paper: any) => (
              <tr key={paper.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <td className="px-4 py-3 font-medium text-gray-900 dark:text-white"><button className="text-left text-primary-700 hover:underline dark:text-primary-300" onClick={() => setSelectedPaperId(paper.id)}>{paper.title}</button></td>
                <td className="px-4 py-3">
                  <span className={STATUS_BADGE[paper.status] ?? "badge-gray"}>
                    {STATUS_LABEL[paper.status] ?? paper.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-500">#{paper.revision_number}</td>
                <td className="px-4 py-3 text-gray-500">
                  {paper.submitted_at
                    ? new Date(paper.submitted_at).toLocaleDateString("de-DE")
                    : "—"}
                </td>
              </tr>
            ))}
            {papers?.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-gray-400">
                  Noch keine Paper eingereicht
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <Modal open={open} title="Paper einreichen" onClose={() => setOpen(false)}>
        <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); createPaper.mutate(); }}>
          <label className="block text-sm font-medium">Team *
            <select className="input mt-1 w-full" required value={form.team_id} onChange={(event) => setForm((current) => ({ ...current, team_id: event.target.value }))}>
              <option value="">Bitte wählen</option>
              {registrations?.map((registration) => <option key={registration.id} value={registration.team_id}>{registration.team_name}</option>)}
            </select>
          </label>
          <label className="block text-sm font-medium">Titel *
            <input className="input mt-1 w-full" required value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} />
          </label>
          <label className="block text-sm font-medium">Kurzfassung
            <textarea className="input mt-1 min-h-24 w-full" value={form.abstract} onChange={(event) => setForm((current) => ({ ...current, abstract: event.target.value }))} />
          </label>
          <label className="block text-sm font-medium">PDF
            <input className="mt-1 block w-full text-sm" type="file" accept="application/pdf" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          </label>
          {createPaper.isError && <p className="text-sm text-red-600">Paper konnte nicht angelegt werden.</p>}
          <div className="flex justify-end gap-3">
            <button type="button" className="btn-secondary" onClick={() => setOpen(false)}>Abbrechen</button>
            <button type="submit" className="btn-primary" disabled={!event || !form.team_id || !form.title || createPaper.isPending}>Einreichen</button>
          </div>
        </form>
      </Modal>
      <Modal open={!!selectedPaperId} title={paperDetail.data?.title ?? "Paper-Workflow"} onClose={() => setSelectedPaperId("")}>
        {paperDetail.isLoading ? <p>Laden…</p> : <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-2"><span className={STATUS_BADGE[paperDetail.data?.status] ?? "badge-gray"}>{STATUS_LABEL[paperDetail.data?.status] ?? paperDetail.data?.status}</span><span className="text-sm text-gray-500">Revision {paperDetail.data?.revision_number}</span>{canAdmin && <select aria-label="Paperstatus ändern" className="input ml-auto" value={paperDetail.data?.status ?? "draft"} onChange={(event) => setStatus.mutate(event.target.value)}>{Object.keys(STATUS_LABEL).map((status) => <option key={status}>{status}</option>)}</select>}</div>
          {canAdmin && <section><h3 className="mb-2 font-semibold">Reviewer-Zuweisungen</h3><div className="space-y-2">{paperDetail.data?.assignments?.map((item: any) => <div key={item.id} className="flex items-center justify-between rounded border p-2 text-sm"><span>{users?.find((user) => user.id === item.reviewer_id)?.display_name ?? item.reviewer_id} · {item.status}{item.due_at ? ` · fällig ${new Date(item.due_at).toLocaleString()}` : ""}</span>{item.status !== "completed" && <button className="btn-secondary" onClick={() => remindReviewer.mutate(item.id)}>Erinnern</button>}</div>)}</div><form className="mt-3 grid gap-2 sm:grid-cols-[1fr_1fr_auto]" onSubmit={(event) => { event.preventDefault(); assignReviewer.mutate(); }}><select required className="input" value={assignment.reviewer_id} onChange={(event) => setAssignment({ ...assignment, reviewer_id: event.target.value })}><option value="">Reviewer wählen</option>{users?.map((user) => <option key={user.id} value={user.id}>{user.display_name}</option>)}</select><input className="input" type="datetime-local" value={assignment.due_at} onChange={(event) => setAssignment({ ...assignment, due_at: event.target.value })} /><button className="btn-primary">Zuweisen</button></form></section>}
          {canReview && <form className="space-y-3" onSubmit={(event) => { event.preventDefault(); submitReview.mutate(); }}><h3 className="font-semibold">Review abschließen</h3><div className="grid grid-cols-2 gap-2">{(["score_content", "score_methodology", "score_presentation", "score_originality"] as const).map((key) => <label key={key} className="text-sm">{key.replace("score_", "")}<input required className="input mt-1 w-full" type="number" min={0} max={10} step={0.5} value={review[key]} onChange={(event) => setReview({ ...review, [key]: event.target.value })} /></label>)}</div><textarea className="input w-full" placeholder="Kommentare" value={review.comments} onChange={(event) => setReview({ ...review, comments: event.target.value })} /><button className="btn-primary" disabled={submitReview.isPending}>Review verbindlich abgeben</button></form>}
          <section><h3 className="mb-2 font-semibold">Statushistorie</h3><ol className="space-y-1 text-sm text-gray-600 dark:text-gray-300">{paperHistory.data?.map((item) => <li key={item.id}>{new Date(item.changed_at).toLocaleString()} · {item.from_status ?? "Start"} → {item.to_status}</li>)}</ol></section>
        </div>}
      </Modal>
    </div>
  );
}

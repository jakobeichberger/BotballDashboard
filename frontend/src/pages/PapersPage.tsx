import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { useParams } from "react-router-dom";
import { api } from "@/lib/api";
import Modal from "@/components/Modal";
import { EventLink } from "@/components/EventLink";
import { ExportButton } from "@/components/ExportButtons";
import { useEvent } from "@/hooks/useEvents";
import { useAuthStore } from "@/store/authStore";
import type { EventRegistration } from "@/api/types";
import { DeadlineBanner } from "@/modules/papers/DeadlineBanner";
import { AutoAssignPanel } from "@/modules/papers/AutoAssignPanel";
import { PaperDeadlinesPanel } from "@/modules/papers/PaperDeadlinesPanel";
import {
  PAPER_STATUS_BADGE,
  PAPER_STATUS_LABEL,
  REVIEW_CRITERIA,
  apiErrorMessage,
  type PaperDeadline,
  type PaperStats,
} from "@/modules/papers/paperMeta";

interface PaperRow {
  id: string;
  title: string;
  status: string;
  revision_number: number;
  current_version?: number | null;
  final_score?: number | null;
  submitted_at: string | null;
}

function pct(value: number | null | undefined) {
  return value == null ? "—" : `${Math.round(value * 100)} %`;
}

function PaperStatsPanel({ stats }: { stats: PaperStats }) {
  const tiles = [
    ["Paper gesamt", String(stats.total)],
    ["Annahmequote", pct(stats.acceptance_rate)],
    ["Ø Endergebnis", pct(stats.average_final_score)],
    ["Ø Review-Score", stats.average_review_score == null ? "—" : `${stats.average_review_score.toFixed(1)} / 10`],
    ["Offene Reviews", String(stats.reviews_open)],
  ];
  return (
    <section className="mb-6" aria-labelledby="paper-stats-heading">
      <h2 id="paper-stats-heading" className="mb-2 text-lg font-semibold">Statistik</h2>
      <dl className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {tiles.map(([label, value]) => (
          <div key={label} className="card p-3">
            <dt className="text-xs text-gray-500">{label}</dt>
            <dd className="text-xl font-semibold text-gray-900 dark:text-white">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-xs text-gray-500">
        {stats.accepted} angenommen · {stats.rejected} abgelehnt · {stats.disqualified} disqualifiziert ·
        Ø je Kriterium:{" "}
        {REVIEW_CRITERIA.map((c) => `${c.label} ${stats.criterion_averages?.[c.key]?.toFixed(1) ?? "—"}`).join(" · ")}
      </p>
    </section>
  );
}

export default function PapersPage() {
  const { eventId = "" } = useParams();
  const { data: event } = useEvent(eventId);
  const canWrite = useAuthStore((state) => state.hasPermission("papers:write"));
  const canAdmin = useAuthStore((state) => state.hasPermission("papers:admin"));
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ team_id: "", title: "", abstract: "" });
  const [file, setFile] = useState<File | null>(null);
  const seasonId = event?.season_id;
  // Mentors may only file for teams they belong to; the backend enforces this
  // too (assert_team_access), this just keeps the choice list honest.
  const { data: myTeams } = useQuery<{ id: string }[]>({
    queryKey: ["teams-mine"],
    queryFn: async () => (await api.get("/teams/mine")).data,
    enabled: canWrite && !canAdmin,
  });
  const { data: registrations } = useQuery<EventRegistration[]>({
    queryKey: ["event-registrations", eventId],
    queryFn: async () => (await api.get(`/v1/events/${eventId}/registrations`)).data,
    enabled: !!eventId,
  });
  const { data: papers, isLoading } = useQuery<PaperRow[]>({
    queryKey: ["papers", eventId],
    queryFn: async () => (await api.get("/papers", { params: { event_id: eventId } })).data,
  });
  const { data: deadline } = useQuery<PaperDeadline>({
    queryKey: ["paper-deadline", seasonId, eventId],
    queryFn: async () =>
      (await api.get("/papers/deadline", { params: { season_id: seasonId, event_id: eventId || undefined } })).data,
    enabled: !!seasonId,
  });
  const { data: stats } = useQuery<PaperStats>({
    queryKey: ["paper-stats", eventId],
    queryFn: async () => (await api.get("/papers/stats", { params: { event_id: eventId || undefined } })).data,
    enabled: canAdmin,
  });
  const { data: workload } = useQuery<any[]>({ queryKey: ["paper-workload", eventId], queryFn: async () => (await api.get("/papers/reviewers/workload", { params: { event_id: eventId } })).data, enabled: canAdmin });
  const { data: users } = useQuery<any[]>({ queryKey: ["users"], queryFn: async () => (await api.get("/auth/users")).data, enabled: canAdmin });

  const locked = !!deadline?.locked;
  const createPaper = useMutation({
    mutationFn: async () => {
      const { data } = await api.post("/papers", { ...form, season_id: seasonId, event_id: eventId });
      // Without a PDF the paper stays a draft; submitting needs an uploaded version.
      if (file) {
        const body = new FormData();
        body.append("file", file);
        await api.post(`/papers/${data.id}/upload`, body);
        await api.put(`/papers/${data.id}/submit`);
      }
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["papers", eventId] });
      setForm({ team_id: "", title: "", abstract: "" });
      setFile(null);
      setOpen(false);
    },
  });

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <FileText className="w-6 h-6" />
          Paper Review
        </h1>
        <div className="flex flex-wrap items-center gap-2">
          {canAdmin && seasonId && (
            <>
              <ExportButton url={`/exports/seasons/${seasonId}/reviews.csv`} filename="paper-reviews.csv" label="Reviews CSV" variant="csv" />
              <ExportButton url={`/exports/seasons/${seasonId}/papers.pdf`} filename="paper-review.pdf" label="Übersicht PDF" />
            </>
          )}
          {canWrite && (
            <button onClick={() => setOpen(true)} className="btn-primary" disabled={locked} title={locked ? "Einreichungsfrist abgelaufen" : undefined}>
              + Paper einreichen
            </button>
          )}
        </div>
      </div>

      {deadline && <div className="mb-6"><DeadlineBanner deadline={deadline} /></div>}

      {isLoading && <p className="text-gray-500">Laden...</p>}

      {seasonId && <PaperDeadlinesPanel seasonId={seasonId} canAdmin={canAdmin} />}

      {canAdmin && stats && <PaperStatsPanel stats={stats} />}

      {canAdmin && seasonId && <AutoAssignPanel seasonId={seasonId} eventId={eventId} />}

      {canAdmin && workload && <section className="mb-6"><h2 className="mb-2 text-lg font-semibold">Reviewer-Auslastung</h2><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{workload.map((item) => <div key={item.reviewer_id} className="card p-3 text-sm"><p className="font-semibold">{users?.find((user) => user.id === item.reviewer_id)?.display_name ?? item.reviewer_id}</p><p className="text-gray-500">{item.open} offen · {item.overdue} überfällig · {item.completed} erledigt</p></div>)}</div></section>}

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Titel</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Status</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Runde</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Version</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Eingereicht</th>
            </tr>
          </thead>
          <tbody className="divide-y dark:divide-gray-800">
            {papers?.map((paper) => (
              <tr key={paper.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">
                  <EventLink to={`/papers/${paper.id}`} className="text-primary-700 hover:underline dark:text-primary-300">{paper.title}</EventLink>
                </td>
                <td className="px-4 py-3">
                  <span className={PAPER_STATUS_BADGE[paper.status] ?? "badge-gray"}>
                    {PAPER_STATUS_LABEL[paper.status] ?? paper.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-500">#{paper.revision_number}</td>
                <td className="px-4 py-3 text-gray-500">{paper.current_version ? `v${paper.current_version}` : "—"}</td>
                <td className="px-4 py-3 text-gray-500">
                  {paper.submitted_at
                    ? new Date(paper.submitted_at).toLocaleDateString("de-DE")
                    : "—"}
                </td>
              </tr>
            ))}
            {papers?.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                  Noch keine Paper eingereicht
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <Modal open={open} title="Paper einreichen" onClose={() => setOpen(false)}>
        <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); createPaper.mutate(); }}>
          <p className="text-xs text-gray-500">Pro Team und Saison gibt es ein Paper. Überarbeitungen werden später als neue Version hochgeladen.</p>
          <label className="block text-sm font-medium">Team *
            <select className="input mt-1 w-full" required value={form.team_id} onChange={(event) => setForm((current) => ({ ...current, team_id: event.target.value }))}>
              <option value="">Bitte wählen</option>
              {registrations
                ?.filter((registration) => canAdmin || myTeams?.some((team) => team.id === registration.team_id))
                .map((registration) => <option key={registration.id} value={registration.team_id}>{registration.team_name}</option>)}
            </select>
          </label>
          <label className="block text-sm font-medium">Titel *
            <input className="input mt-1 w-full" required value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} />
          </label>
          <label className="block text-sm font-medium">Kurzfassung
            <textarea className="input mt-1 min-h-24 w-full" value={form.abstract} onChange={(event) => setForm((current) => ({ ...current, abstract: event.target.value }))} />
          </label>
          <label className="block text-sm font-medium">PDF (ohne PDF bleibt das Paper ein Entwurf)
            <input className="mt-1 block w-full text-sm" type="file" accept="application/pdf" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          </label>
          {createPaper.isError && <p className="text-sm text-red-600">{apiErrorMessage(createPaper.error, "Paper konnte nicht angelegt werden.")}</p>}
          <div className="flex justify-end gap-3">
            <button type="button" className="btn-secondary" onClick={() => setOpen(false)}>Abbrechen</button>
            <button type="submit" className="btn-primary" disabled={!event || !form.team_id || !form.title || createPaper.isPending}>{file ? "Einreichen" : "Als Entwurf anlegen"}</button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import Modal from "@/components/Modal";
import { EventLink } from "@/components/EventLink";
import { ExportButton, PaperExportButtons } from "@/components/ExportButtons";
import { useEvent } from "@/hooks/useEvents";
import { useAuthStore } from "@/store/authStore";
import { formatDate, formatNumber } from "@/i18n/format";
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

const oneDecimal = { minimumFractionDigits: 1, maximumFractionDigits: 1 };

function PaperStatsPanel({ stats }: { stats: PaperStats }) {
  const { t } = useTranslation("papers");
  const tiles = [
    [t("stats.total"), String(stats.total)],
    [t("stats.acceptanceRate"), pct(stats.acceptance_rate)],
    [t("stats.avgFinal"), pct(stats.average_final_score)],
    [t("stats.avgReview"), stats.average_review_score == null ? "—" : `${formatNumber(stats.average_review_score, oneDecimal)} / 10`],
    [t("stats.openReviews"), String(stats.reviews_open)],
  ];
  return (
    <section className="mb-6" aria-labelledby="paper-stats-heading">
      <h2 id="paper-stats-heading" className="mb-2 text-lg font-semibold">{t("stats.title")}</h2>
      <dl className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {tiles.map(([label, value]) => (
          <div key={label} className="card p-3">
            <dt className="text-xs text-leise">{label}</dt>
            <dd className="text-xl font-semibold text-fg">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-xs text-leise">
        {t("stats.decisions", { accepted: stats.accepted, rejected: stats.rejected, disqualified: stats.disqualified })}{" "}
        {t("stats.perCriterion")}{" "}
        {REVIEW_CRITERIA.map((c) => `${c.label} ${formatNumber(stats.criterion_averages?.[c.key], oneDecimal)}`).join(" · ")}
      </p>
    </section>
  );
}

export default function PapersPage() {
  const { t } = useTranslation("papers");
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
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <h1 className="text-2xl font-bold text-fg flex items-center gap-2">
          <FileText className="w-6 h-6" />
          {t("title")}
        </h1>
        <div className="flex flex-wrap items-center gap-2">
          {canAdmin && seasonId && (
            <>
              <ExportButton url={`/exports/seasons/${seasonId}/reviews.csv`} filename="paper-reviews.csv" label={t("reviewsCsv")} variant="csv" />
              <PaperExportButtons seasonId={seasonId} seasonYear={event?.slug} />
            </>
          )}
          {canWrite && (
            <button onClick={() => setOpen(true)} className="btn-primary" disabled={locked} title={locked ? t("deadlinePassed") : undefined}>
              {t("submitNew")}
            </button>
          )}
        </div>
      </div>

      {deadline && <div className="mb-6"><DeadlineBanner deadline={deadline} /></div>}

      {isLoading && <p className="text-leise">{t("common:loading")}</p>}

      {seasonId && <PaperDeadlinesPanel seasonId={seasonId} canAdmin={canAdmin} />}

      {canAdmin && stats && <PaperStatsPanel stats={stats} />}

      {canAdmin && seasonId && <AutoAssignPanel seasonId={seasonId} eventId={eventId} />}

      {canAdmin && workload && <section className="mb-6"><h2 className="mb-2 text-lg font-semibold">{t("workload.title")}</h2><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{workload.map((item) => <div key={item.reviewer_id} className="card p-3 text-sm"><p className="font-semibold">{users?.find((user) => user.id === item.reviewer_id)?.display_name ?? item.reviewer_id}</p><p className="text-leise">{t("workload.summary", { open: item.open, overdue: item.overdue, completed: item.completed })}</p></div>)}</div></section>}

      <div className="card table-scroll">
        <table className="w-full text-sm">
          <thead className="bg-flaeche-2">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-leise">{t("col.title")}</th>
              <th className="px-4 py-3 text-left font-medium text-leise">{t("common:status")}</th>
              <th className="px-4 py-3 text-left font-medium text-leise">{t("col.round")}</th>
              <th className="px-4 py-3 text-left font-medium text-leise">{t("col.version")}</th>
              <th className="px-4 py-3 text-left font-medium text-leise">{t("col.submitted")}</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {papers?.map((paper) => (
              <tr key={paper.id} className="hover:bg-flaeche-2">
                <td className="px-4 py-3 font-medium text-fg">
                  <EventLink to={`/papers/${paper.id}`} className="text-akzent hover:underline">{paper.title}</EventLink>
                </td>
                <td className="px-4 py-3">
                  <span className={PAPER_STATUS_BADGE[paper.status] ?? "badge-gray"}>
                    {PAPER_STATUS_LABEL[paper.status] ?? paper.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-leise">#{paper.revision_number}</td>
                <td className="px-4 py-3 text-leise">{paper.current_version ? `v${paper.current_version}` : "—"}</td>
                <td className="px-4 py-3 text-leise">
                  {formatDate(paper.submitted_at)}
                </td>
              </tr>
            ))}
            {papers?.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-leise">
                  {t("empty")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <Modal open={open} title={t("create.title")} onClose={() => setOpen(false)}>
        <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); createPaper.mutate(); }}>
          <p className="text-xs text-leise">{t("create.hint")}</p>
          <label className="block text-sm font-medium">{t("create.team")}
            <select className="input mt-1 w-full" required value={form.team_id} onChange={(event) => setForm((current) => ({ ...current, team_id: event.target.value }))}>
              <option value="">{t("common:pleaseChoose")}</option>
              {registrations
                ?.filter((registration) => canAdmin || myTeams?.some((team) => team.id === registration.team_id))
                .map((registration) => <option key={registration.id} value={registration.team_id}>{registration.team_name}</option>)}
            </select>
          </label>
          <label className="block text-sm font-medium">{t("create.titleLabel")}
            <input className="input mt-1 w-full" required value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} />
          </label>
          <label className="block text-sm font-medium">{t("create.abstract")}
            <textarea className="input mt-1 min-h-24 w-full" value={form.abstract} onChange={(event) => setForm((current) => ({ ...current, abstract: event.target.value }))} />
          </label>
          <label className="block text-sm font-medium">{t("create.pdf")}
            <input className="mt-1 block w-full text-sm" type="file" accept="application/pdf" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          </label>
          {createPaper.isError && <p className="text-sm text-red-600">{apiErrorMessage(createPaper.error, t("create.failed"))}</p>}
          <div className="flex justify-end gap-3">
            <button type="button" className="btn-secondary" onClick={() => setOpen(false)}>{t("common:cancel")}</button>
            <button type="submit" className="btn-primary" disabled={!event || !form.team_id || !form.title || createPaper.isPending}>{file ? t("create.submit") : t("create.draft")}</button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

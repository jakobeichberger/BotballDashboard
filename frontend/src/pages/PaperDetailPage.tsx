import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  FileText, ArrowLeft, Download, Upload, Users, Award, UserPlus, Send, CheckCircle2,
  History, MessageSquare, Lock, Unlock, BellRing, ListTree,
} from "lucide-react";
import { api } from "@/lib/api";
import { EventLink } from "@/components/EventLink";
import { useAuthStore } from "@/store/authStore";
import { formatDateTime, formatNumber } from "@/i18n/format";
import { labelMap } from "@/i18n/labels";
import { formatFileSize } from "@/lib/teams";
import { DeadlineBanner } from "@/modules/papers/DeadlineBanner";
import { VersionDiff } from "@/modules/papers/VersionDiff";
import { confirmAction } from "@/lib/confirm";
import { toast } from "@/lib/toast";
import { downloadFile } from "@/lib/download";
import {
  ADMIN_STATUS_OPTIONS,
  EDITABLE_STATUSES,
  OPEN_REVIEW_STATUSES,
  PAPER_STATUS_BADGE,
  PAPER_STATUS_LABEL,
  RECOMMENDATION_BADGE,
  RECOMMENDATION_LABEL,
  REVIEW_CRITERIA,
  apiErrorMessage,
  type CriterionKey,
  type PaperDetail,
  type PaperReview,
  type PaperStatusChange,
  type ReviewFeedback,
} from "@/modules/papers/paperMeta";

const ASSIGNMENT_LABEL = labelMap("papers:assignment", ["pending", "in_progress", "completed", "overdue"]);

type ReviewForm = Record<`score_${CriterionKey}` | `comment_${CriterionKey}`, string> & {
  recommendation: string;
  comments: string;
  revision_notes: string;
  private_notes: string;
};

function emptyForm(): ReviewForm {
  const form = { recommendation: "", comments: "", revision_notes: "", private_notes: "" } as ReviewForm;
  for (const { key } of REVIEW_CRITERIA) {
    form[`score_${key}`] = "";
    form[`comment_${key}`] = "";
  }
  return form;
}

function formFromReview(review: PaperReview): ReviewForm {
  const form = emptyForm();
  for (const { key } of REVIEW_CRITERIA) {
    form[`score_${key}`] = review[`score_${key}`]?.toString() ?? "";
    form[`comment_${key}`] = review[`comment_${key}`] ?? "";
  }
  form.recommendation = review.recommendation ?? "";
  form.comments = review.comments ?? "";
  form.revision_notes = review.revision_notes ?? "";
  form.private_notes = review.private_notes ?? "";
  return form;
}

function fmtDate(v?: string | null) {
  return formatDateTime(v);
}
function fmtBytes(n?: number | null) {
  return n ? formatFileSize(n) : "—";
}

/** Scores and comments of one review, as the team and organizers read them. */
function ReviewBody({ review }: { review: ReviewFeedback }) {
  const { t } = useTranslation("papers");
  return (
    <>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-sm mb-3">
        {REVIEW_CRITERIA.map((c) => (
          <div key={c.key}>
            <div className="text-gray-500">{c.label}</div>
            <div className="font-semibold text-gray-900 dark:text-white">{review[`score_${c.key}`] ?? "—"}</div>
          </div>
        ))}
        <div>
          <div className="text-gray-500">{t("detail.total")}</div>
          <div className="font-semibold text-gray-900 dark:text-white">{review.total_score ?? "—"}</div>
        </div>
      </div>
      <dl className="space-y-2 text-sm">
        {REVIEW_CRITERIA.filter((c) => review[`comment_${c.key}`]).map((c) => (
          <div key={c.key}>
            <dt className="font-medium text-gray-700 dark:text-gray-300">{c.label}</dt>
            <dd className="text-gray-600 dark:text-gray-400 whitespace-pre-line">{review[`comment_${c.key}`]}</dd>
          </div>
        ))}
        {review.comments && (
          <div><dt className="font-medium text-gray-700 dark:text-gray-300">{t("detail.overallComment")}</dt><dd className="text-gray-600 dark:text-gray-400 whitespace-pre-line">{review.comments}</dd></div>
        )}
        {review.revision_notes && (
          <div><dt className="font-medium text-gray-700 dark:text-gray-300">{t("detail.toRevise")}</dt><dd className="text-gray-600 dark:text-gray-400 whitespace-pre-line">{review.revision_notes}</dd></div>
        )}
      </dl>
    </>
  );
}

export default function PaperDetailPage() {
  const { t } = useTranslation("papers");
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const isAdmin = useAuthStore((s) => s.hasPermission("papers:admin"));
  const canPapersWrite = useAuthStore((s) => s.hasPermission("papers:write"));

  const { data: paper, isLoading, isError } = useQuery<PaperDetail>({
    queryKey: ["paper", id],
    queryFn: async () => (await api.get(`/papers/${id}`)).data,
    enabled: !!id,
  });
  const { data: history } = useQuery<PaperStatusChange[]>({
    queryKey: ["paper-history", id],
    queryFn: async () => (await api.get(`/papers/${id}/history`)).data,
    enabled: !!id,
  });
  const { data: teams } = useQuery({
    queryKey: ["teams"],
    queryFn: async () => (await api.get("/teams")).data,
  });
  const { data: levels } = useQuery({
    queryKey: ["competition-levels"],
    queryFn: async () => (await api.get("/seasons/competition-levels/all")).data,
  });
  const { data: users } = useQuery({
    queryKey: ["users"],
    queryFn: async () => (await api.get("/auth/users")).data,
    enabled: isAdmin,
  });
  const { data: myTeams } = useQuery({
    queryKey: ["teams-mine"],
    queryFn: async () => (await api.get("/teams/mine")).data,
    enabled: !isAdmin,
  });

  const team = teams?.find((item: any) => item.id === paper?.team_id);
  const levelName = levels?.find((l: any) => l.id === paper?.competition_level_id)?.name ?? "—";
  const userName = (uid: string) =>
    users?.find((u: any) => u.id === uid)?.display_name ?? t("detail.reviewerFallback", { id: uid.slice(0, 8) });

  const myReview = paper?.reviews?.find(
    (r) => r.reviewer_id === user?.id && r.revision_number === paper?.revision_number
  );
  const isAssigned = !!paper?.assignments?.some((a) => a.reviewer_id === user?.id);
  const reviewOpen = !!paper && OPEN_REVIEW_STATUSES.has(paper.status) && !paper.finalized_at;
  const myReviewLocked = !!myReview?.is_submitted || !reviewOpen;

  const submittedReviews = (paper?.reviews ?? []).filter(
    (r) => r.is_submitted && r.revision_number === paper?.revision_number && r.total_score != null
  );
  const avgScore = submittedReviews.length
    ? formatNumber(submittedReviews.reduce((s, r) => s + (r.total_score ?? 0), 0) / submittedReviews.length, {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
      })
    : null;

  // ── Reviewer form state ────────────────────────────────────────────────
  const [form, setForm] = useState<ReviewForm>(emptyForm);
  // Re-seed whenever the paper OR the matching review changes. The router
  // reuses this component across /papers/:id, so without the reset branch the
  // previous paper's scores stayed in the form and could be saved onto the
  // next one. The same applies after a revision is requested, which makes
  // myReview undefined (reviews are per revision_number).
  useEffect(() => {
    setForm(myReview ? formFromReview(myReview) : emptyForm());
  }, [id, myReview?.id, myReview?.is_submitted]); // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["paper", id] });
    qc.invalidateQueries({ queryKey: ["paper-history", id] });
    qc.invalidateQueries({ queryKey: ["papers"] });
  };
  const onError = (e: unknown) => toast.error(apiErrorMessage(e));

  const saveReviewM = useMutation({
    mutationFn: (submit: boolean) => {
      const payload: Record<string, string | number | null> = {
        recommendation: form.recommendation || null,
        comments: form.comments || null,
        revision_notes: form.revision_notes || null,
        private_notes: form.private_notes || null,
      };
      for (const { key } of REVIEW_CRITERIA) {
        const score = form[`score_${key}`];
        payload[`score_${key}`] = score === "" ? null : Number(score);
        payload[`comment_${key}`] = form[`comment_${key}`] || null;
      }
      return api.put(`/papers/${id}/reviews`, payload, { params: { submit } });
    },
    onSuccess: refresh,
    onError,
  });

  const [newStatus, setNewStatus] = useState("");
  const [statusReason, setStatusReason] = useState("");
  const setStatusM = useMutation({
    mutationFn: (status: string) =>
      api.put(`/papers/${id}/status`, null, { params: { status, reason: statusReason || undefined } }),
    onSuccess: () => { setNewStatus(""); setStatusReason(""); refresh(); },
    onError,
  });

  const [assignId, setAssignId] = useState("");
  const assignM = useMutation({
    mutationFn: (reviewerId: string) => api.post(`/papers/${id}/assignments`, { reviewer_id: reviewerId }),
    onSuccess: () => { setAssignId(""); refresh(); },
    onError,
  });

  const remindM = useMutation({
    mutationFn: (assignmentId: string) => api.post(`/papers/${id}/assignments/${assignmentId}/remind`),
    onSuccess: refresh,
    onError,
  });

  const [deduction, setDeduction] = useState("");
  const [deductionReason, setDeductionReason] = useState("");
  useEffect(() => {
    setDeduction(paper?.format_deduction ? String(paper.format_deduction) : "");
    setDeductionReason(paper?.format_deduction_reason ?? "");
  }, [paper?.id, paper?.format_deduction, paper?.format_deduction_reason]);
  const deductionM = useMutation({
    mutationFn: () =>
      api.put(`/papers/${id}/score`, {
        format_deduction: deduction === "" ? 0 : Number(deduction),
        format_deduction_reason: deductionReason || null,
      }),
    onSuccess: refresh,
    onError,
  });

  const stageM = useMutation({
    mutationFn: (presented: boolean) => api.put(`/papers/${id}/score`, { presented_on_stage: presented }),
    onSuccess: refresh,
    onError,
  });

  const reopenM = useMutation({
    mutationFn: (reviewId: string) => api.post(`/papers/${id}/reviews/${reviewId}/reopen`),
    onSuccess: refresh,
    onError,
  });

  const [file, setFile] = useState<File | null>(null);
  const uploadM = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append("file", file as File);
      return api.post(`/papers/${id}/upload`, fd);
    },
    onSuccess: () => { setFile(null); refresh(); },
    onError,
  });

  const submitPaperM = useMutation({
    mutationFn: () => api.put(`/papers/${id}/submit`),
    onSuccess: refresh,
    onError,
  });
  const finalizeM = useMutation({
    mutationFn: () => api.post(`/papers/${id}/finalize`),
    onSuccess: refresh,
    onError,
  });

  const handleDownload = async (version?: number, name?: string) => {
    try {
      await downloadFile(`/papers/${id}/download`, name ?? paper?.file_name ?? "paper.pdf", version ? { version } : undefined);
    } catch (error) {
      toast.apiError(error, t("detail.fileUnavailable"));
    }
  };

  if (isLoading) return <div className="p-6 text-gray-500">{t("common:loading")}</div>;
  if (isError || !paper) {
    return (
      <div className="p-6">
        <EventLink to="/papers" className="btn-secondary text-sm mb-6">
          <ArrowLeft className="w-4 h-4" /> {t("detail.back")}
        </EventLink>
        <div className="card p-8 text-center text-gray-400">{t("detail.notFound")}</div>
      </div>
    );
  }

  const assignableUsers = (users ?? []).filter(
    (u: any) =>
      u.is_active !== false &&
      (u.is_superuser || u.permissions?.includes("papers:review")) &&
      !paper.assignments?.some((a) => a.reviewer_id === u.id)
  );
  const isMyTeam = !!myTeams?.some((item: any) => item.id === paper.team_id);
  const canWritePaper = canPapersWrite && (isAdmin || isMyTeam); // upload / submit
  const editable = EDITABLE_STATUSES.has(paper.status);
  // First submission: the submission deadline; revisions: a blocking official_final one.
  const deadlineLocked =
    paper.revision_number <= 1 ? !!paper.deadline?.locked : !!paper.deadline?.final_locked;
  const versions = [...(paper.versions ?? [])].reverse();

  return (
    <div className="p-6 space-y-6">
      <EventLink to="/papers" className="btn-secondary text-sm">
        <ArrowLeft className="w-4 h-4" /> {t("detail.back")}
      </EventLink>

      {/* Header */}
      <div className="card p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <h1 className="flex min-w-0 items-start gap-2 break-words text-2xl font-bold text-gray-900 dark:text-white">
            <FileText className="w-6 h-6 mt-1 shrink-0" />
            {paper.title}
          </h1>
          <span className={PAPER_STATUS_BADGE[paper.status] ?? "badge-gray"}>
            {PAPER_STATUS_LABEL[paper.status] ?? paper.status}
          </span>
        </div>

        <dl className="mt-4 grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-5 text-sm">
          <div>
            <dt className="text-gray-500">{t("detail.team")}</dt>
            <dd>
              {team ? (
                <EventLink to={`/teams/${team.id}`} className="text-primary-600 dark:text-primary-400 hover:underline flex items-center gap-1">
                  <Users className="w-3.5 h-3.5" /> {team.name}
                </EventLink>
              ) : (<span className="text-gray-900 dark:text-white">{paper.team_id}</span>)}
            </dd>
          </div>
          <div><dt className="text-gray-500">{t("detail.level")}</dt><dd className="text-gray-900 dark:text-white">{levelName}</dd></div>
          <div><dt className="text-gray-500">{t("detail.reviewRound")}</dt><dd className="text-gray-900 dark:text-white">#{paper.revision_number}</dd></div>
          <div><dt className="text-gray-500">{t("detail.currentVersion")}</dt><dd className="text-gray-900 dark:text-white">{paper.current_version ? `v${paper.current_version}` : "—"}</dd></div>
          <div><dt className="text-gray-500">{t("col.submitted")}</dt><dd className="text-gray-900 dark:text-white">{fmtDate(paper.submitted_at)}</dd></div>
        </dl>

        {(paper.final_score != null || avgScore || paper.format_deduction > 0) && (
          <div className="mt-4 border-t pt-4 flex flex-wrap gap-6 text-sm">
            {avgScore && (
              <div className="flex items-center gap-2">
                <span className="text-gray-500">{t("detail.avgReviewerScore")}</span>
                <span className="font-semibold text-gray-900 dark:text-white">{avgScore} / 10</span>
                <span className="text-gray-400">{t("detail.submittedCount", { count: submittedReviews.length })}</span>
              </div>
            )}
            {paper.format_deduction > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-gray-500">{t("detail.formatDeduction")}</span>
                <span className="font-semibold text-red-600">{t("detail.deductionPoints", { points: paper.format_deduction })}</span>
                {paper.format_deduction_reason && <span className="text-gray-400">({paper.format_deduction_reason})</span>}
              </div>
            )}
            {paper.final_score != null && (
              <div className="flex flex-wrap items-center gap-2">
                <Award className="w-4 h-4 text-primary-500" />
                <span className="text-gray-500">{t("detail.finalResult")}</span>
                <span className="font-semibold text-gray-900 dark:text-white">{Math.round(paper.final_score * 100)}%</span>
                {paper.paper_rank != null && <span className="badge-green">{t("detail.rank", { rank: paper.paper_rank })}</span>}
              </div>
            )}
          </div>
        )}
        {paper.status === "disqualified_ai" && (
          <p className="mt-4 rounded bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-300">
            {t("detail.disqualifiedAi")}
          </p>
        )}
      </div>

      {canWritePaper && editable && <DeadlineBanner deadline={paper.deadline} />}

      {/* Abstract */}
      <section className="card p-6">
        <h2 className="font-semibold text-gray-900 dark:text-white mb-2">{t("detail.abstract")}</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 whitespace-pre-line">
          {paper.abstract || t("detail.noAbstract")}
        </p>
      </section>

      {/* Versions */}
      <section className="card overflow-hidden" aria-labelledby="paper-versions-heading">
        <h2 id="paper-versions-heading" className="px-4 py-3 border-b font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <History className="w-4 h-4" /> {t("detail.versions", { count: paper.versions?.length ?? 0 })}
        </h2>
        <div className="table-scroll">
        <table className="w-full text-sm">
          <tbody className="divide-y dark:divide-gray-800">
            {versions.map((v) => (
              <tr key={v.id}>
                <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">v{v.version_number}</td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{v.file_name} <span className="text-gray-400">({fmtBytes(v.file_size_bytes)}{v.page_count != null ? ` · ${t("detail.pages", { count: v.page_count })}` : ""})</span></td>
                <td className="px-4 py-3 text-gray-500">{t("detail.round", { round: v.revision_number })}</td>
                <td className="px-4 py-3 text-gray-500">{t("detail.uploadedAt", { date: fmtDate(v.uploaded_at) })}</td>
                <td className="px-4 py-3">{v.submitted_at ? <span className="badge-green">{t("detail.submittedAt", { date: fmtDate(v.submitted_at) })}</span> : <span className="badge-gray">{t("detail.notSubmitted")}</span>}</td>
                <td className="px-4 py-3 text-right">
                  <button onClick={() => handleDownload(v.version_number, v.file_name)} className="btn-secondary text-xs" aria-label={t("detail.downloadVersion", { version: v.version_number })}>
                    <Download className="w-3.5 h-3.5" /> PDF
                  </button>
                </td>
              </tr>
            ))}
            {versions.length === 0 && (
              <tr><td className="px-4 py-6 text-center text-gray-400">{t("detail.noFile")}</td></tr>
            )}
          </tbody>
        </table>
      </div>
        <VersionDiff paperId={paper.id} versions={paper.versions ?? []} />
        {canWritePaper && (
          <div className="border-t p-4 flex flex-wrap items-center gap-2 bg-gray-50 dark:bg-gray-800/40">
            {editable ? (
              <>
                <input
                  type="file"
                  accept="application/pdf"
                  aria-label={t("detail.newVersionPdf")}
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  className="text-xs text-gray-500 file:mr-2 file:btn file:btn-secondary file:text-xs"
                />
                <button
                  disabled={!file || uploadM.isPending || deadlineLocked}
                  onClick={() => uploadM.mutate()}
                  className="btn-primary text-sm disabled:opacity-40"
                >
                  <Upload className="w-4 h-4" /> {t("detail.uploadVersion")}
                </button>
                <button
                  disabled={!paper.current_version || submitPaperM.isPending || deadlineLocked}
                  onClick={() => submitPaperM.mutate()}
                  className="btn-secondary text-sm disabled:opacity-40"
                  title={paper.current_version ? undefined : t("detail.uploadFirst")}
                >
                  <Send className="w-4 h-4" /> {paper.status === "revision_requested" ? t("detail.resubmit", { version: paper.current_version ?? "?" }) : t("create.submit")}
                </button>
              </>
            ) : (
              <span className="text-xs text-gray-500 flex items-center gap-1">
                <Lock className="w-3.5 h-3.5" /> {t("detail.versionsLocked")}
              </span>
            )}
          </div>
        )}
      </section>

      {/* Team feedback */}
      {(isMyTeam || isAdmin) && (
        <section className="space-y-3" aria-labelledby="paper-feedback-heading">
          <h2 id="paper-feedback-heading" className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <MessageSquare className="w-4 h-4" /> {t("detail.feedback")}
          </h2>
          {paper.feedback?.length ? (
            paper.feedback.map((f, index) => (
              <div key={f.id} className="card p-4">
                <div className="flex items-center justify-between mb-3 text-sm text-gray-600 dark:text-gray-300">
                  <span>{t("detail.reviewNumber", { number: index + 1 })} · {t("detail.round", { round: f.revision_number })}{f.version_number ? ` · v${f.version_number}` : ""}</span>
                  {f.recommendation && <span className={RECOMMENDATION_BADGE[f.recommendation] ?? "badge-gray"}>{RECOMMENDATION_LABEL[f.recommendation] ?? f.recommendation}</span>}
                </div>
                <ReviewBody review={f} />
              </div>
            ))
          ) : (
            <div className="card p-6 text-center text-sm text-gray-400">
              {t("detail.feedbackPending")}
            </div>
          )}
        </section>
      )}

      {/* ── Admin panel ──────────────────────────────────────────────── */}
      {isAdmin && (
        <section className="card p-6 space-y-5 border-primary-200 dark:border-primary-900">
          <h2 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-primary-500" /> {t("detail.admin")}
          </h2>

          <div className="grid gap-5 md:grid-cols-2">
            {/* Status */}
            <div>
              <label className="label" htmlFor="paper-status">{t("detail.changeStatus")}</label>
              <div className="flex flex-wrap items-center gap-2">
                <select id="paper-status" className="input" value={newStatus} onChange={(e) => setNewStatus(e.target.value)}>
                  <option value="">{t("detail.choose")}</option>
                  {ADMIN_STATUS_OPTIONS.map((s) => (<option key={s} value={s}>{PAPER_STATUS_LABEL[s]}</option>))}
                </select>
                <input className="input flex-1" aria-label={t("detail.reason")} placeholder={t("detail.reasonOptional")} value={statusReason} onChange={(e) => setStatusReason(e.target.value)} />
                <button
                  disabled={!newStatus || setStatusM.isPending}
                  onClick={async () => {
                    if (newStatus === "disqualified_ai" && !(await confirmAction({ message: t("detail.confirmDisqualify"), tone: "danger", confirmLabel: t("detail.apply") }))) return;
                    setStatusM.mutate(newStatus);
                  }}
                  className="btn-secondary text-sm disabled:opacity-40"
                >{t("detail.apply")}</button>
              </div>
            </div>

            {/* Assign reviewer */}
            <div>
              <label className="label" htmlFor="paper-assign">{t("detail.assignReviewer")}</label>
              <div className="flex items-center gap-2">
                <select id="paper-assign" className="input" value={assignId} onChange={(e) => setAssignId(e.target.value)}>
                  <option value="">{t("detail.chooseReviewer")}</option>
                  {assignableUsers.map((u: any) => (<option key={u.id} value={u.id}>{u.display_name} ({u.email})</option>))}
                </select>
                <button
                  disabled={!assignId || assignM.isPending}
                  onClick={() => assignM.mutate(assignId)}
                  className="btn-secondary text-sm disabled:opacity-40"
                ><UserPlus className="w-4 h-4" /> {t("autoAssign.assign")}</button>
              </div>
              <p className="text-xs text-gray-400 mt-1">{t("detail.conflictHint")}</p>
            </div>

            {/* Format deduction */}
            <div>
              <label className="label" htmlFor="paper-deduction">{t("detail.deductionLabel")}</label>
              <div className="flex flex-wrap items-center gap-2">
                <input id="paper-deduction" type="number" min={0} max={100} step={1} className="input w-24" value={deduction} onChange={(e) => setDeduction(e.target.value)} />
                <input className="input flex-1" aria-label={t("detail.deductionReason")} placeholder={t("detail.deductionReasonPlaceholder")} value={deductionReason} onChange={(e) => setDeductionReason(e.target.value)} />
                <button disabled={deductionM.isPending} onClick={() => deductionM.mutate()} className="btn-secondary text-sm disabled:opacity-40">{t("common:save")}</button>
              </div>
              <p className="text-xs text-gray-400 mt-1">{t("detail.deductionHint")}</p>
            </div>

            {/* On-stage presentation */}
            <div>
              <label className="flex items-center gap-2 text-sm font-medium">
                <input type="checkbox" className="h-4 w-4" checked={!!paper.presented_on_stage} disabled={stageM.isPending} onChange={(e) => stageM.mutate(e.target.checked)} />
                {t("detail.presentedOnStage")}
              </label>
              <p className="text-xs text-gray-400 mt-1">{t("detail.presentedOnStageHint")}</p>
            </div>
          </div>

          <div className="flex flex-wrap gap-2 border-t pt-4">
            <button disabled={finalizeM.isPending} onClick={() => finalizeM.mutate()} className="btn-primary text-sm disabled:opacity-40">
              <Award className="w-4 h-4" /> {t("detail.finalize")}
            </button>
            <span className="text-xs text-gray-400 self-center">
              {t("detail.finalizeHint")}
              {paper.finalized_at && ` ${t("detail.lastFinalized", { date: fmtDate(paper.finalized_at) })}`}
            </span>
          </div>
        </section>
      )}

      {/* ── Reviewer form ────────────────────────────────────────────── */}
      {isAssigned && (
        <section className="card p-6 space-y-4" aria-labelledby="my-review-heading">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 id="my-review-heading" className="font-semibold text-gray-900 dark:text-white">
              {t("detail.myReview")} {paper.current_version ? `(v${paper.current_version})` : ""}
            </h2>
            <span className={myReview?.is_submitted ? "badge-green" : "badge-yellow"}>
              {myReview?.is_submitted ? t("detail.reviewSubmitted") : t("detail.reviewDraft")}
            </span>
          </div>
          {myReviewLocked && (
            <p className="text-xs text-gray-500 flex items-center gap-1">
              <Lock className="w-3.5 h-3.5" />
              {myReview?.is_submitted
                ? t("detail.lockedSubmitted")
                : t("detail.notOpen")}
            </p>
          )}

          <fieldset disabled={myReviewLocked} className="space-y-4">
            {REVIEW_CRITERIA.map((c) => (
              <div key={c.key} className="grid gap-2 sm:grid-cols-[12rem_6rem_1fr] sm:items-start">
                <label className="label" htmlFor={`score-${c.key}`}>
                  {c.label} <span className="block text-xs font-normal text-gray-400">{c.hint}</span>
                </label>
                <input
                  id={`score-${c.key}`}
                  type="number" min={0} max={10} step={0.5} className="input"
                  aria-label={`${c.label} (0–10)`}
                  value={form[`score_${c.key}`]}
                  onChange={(e) => setForm({ ...form, [`score_${c.key}`]: e.target.value })}
                />
                <textarea
                  className="input min-h-[2.5rem]"
                  aria-label={t("detail.commentFor", { criterion: c.label })}
                  placeholder={t("detail.comment")}
                  value={form[`comment_${c.key}`]}
                  onChange={(e) => setForm({ ...form, [`comment_${c.key}`]: e.target.value })}
                />
              </div>
            ))}

            <div>
              <label className="label" htmlFor="review-recommendation">{t("detail.recommendation")}</label>
              <select id="review-recommendation" className="input" value={form.recommendation} onChange={(e) => setForm({ ...form, recommendation: e.target.value })}>
                <option value="">{t("detail.choose")}</option>
                {Object.entries(RECOMMENDATION_LABEL).map(([v, l]) => (<option key={v} value={v}>{l}</option>))}
              </select>
            </div>

            <div>
              <label className="label" htmlFor="review-comments">{t("detail.overallComment")}</label>
              <textarea id="review-comments" className="input min-h-[5rem]" value={form.comments} onChange={(e) => setForm({ ...form, comments: e.target.value })} placeholder={t("detail.feedbackPlaceholder")} />
            </div>
            <div>
              <label className="label" htmlFor="review-revision-notes">{t("detail.revisionNotes")}</label>
              <textarea id="review-revision-notes" className="input min-h-[4rem]" value={form.revision_notes} onChange={(e) => setForm({ ...form, revision_notes: e.target.value })} placeholder={t("detail.revisionNotesPlaceholder")} />
            </div>
            <div>
              <label className="label" htmlFor="review-private-notes">{t("detail.privateNotes")}</label>
              <textarea id="review-private-notes" className="input min-h-[3rem]" value={form.private_notes} onChange={(e) => setForm({ ...form, private_notes: e.target.value })} />
            </div>

            <div className="flex items-center gap-2">
              <button disabled={saveReviewM.isPending} onClick={() => saveReviewM.mutate(false)} className="btn-secondary text-sm disabled:opacity-40">
                {t("detail.saveDraft")}
              </button>
              <button disabled={saveReviewM.isPending} onClick={() => void confirmAction({ message: t("detail.confirmSubmitReview") }).then((ok) => ok && saveReviewM.mutate(true))} className="btn-primary text-sm disabled:opacity-40">
                <Send className="w-4 h-4" /> {t("detail.submitReview")}
              </button>
              <span className="text-xs text-gray-400">{t("detail.submitReviewHint")}</span>
            </div>
          </fieldset>
        </section>
      )}

      {/* Reviews (organizers: all, reviewers: own) */}
      {(isAdmin || (paper.reviews?.length ?? 0) > 0) && (
        <section className="space-y-3">
          <h2 className="font-semibold text-gray-900 dark:text-white">{t(isAdmin ? "detail.allReviews" : "detail.myReviews", { count: paper.reviews?.length ?? 0 })}</h2>
          {paper.reviews?.map((r) => (
            <div key={r.id} className="card p-4">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                <span className="text-sm text-gray-600 dark:text-gray-300">
                  {userName(r.reviewer_id)} · {t("detail.round", { round: r.revision_number })}{r.version_number ? ` · v${r.version_number}` : ""}
                </span>
                <div className="flex flex-wrap items-center gap-2">
                  {r.recommendation && (<span className={RECOMMENDATION_BADGE[r.recommendation] ?? "badge-gray"}>{RECOMMENDATION_LABEL[r.recommendation] ?? r.recommendation}</span>)}
                  <span className={r.is_submitted ? "badge-green" : "badge-yellow"}>{r.is_submitted ? t("detail.reviewSubmitted") : t("detail.reviewDraft")}</span>
                  {isAdmin && r.is_submitted && reviewOpen && r.revision_number === paper.revision_number && (
                    <button onClick={() => reopenM.mutate(r.id)} disabled={reopenM.isPending} className="btn-secondary text-xs">
                      <Unlock className="w-3.5 h-3.5" /> {t("detail.reopen")}
                    </button>
                  )}
                </div>
              </div>
              <ReviewBody review={r} />
            </div>
          ))}
          {(!paper.reviews || paper.reviews.length === 0) && (<div className="card p-8 text-center text-gray-400">{t("detail.noReviews")}</div>)}
        </section>
      )}

      {/* Assignments */}
      {(isAdmin || isAssigned) && (
        <section className="card overflow-hidden">
          <h2 className="px-4 py-3 border-b font-semibold text-gray-900 dark:text-white">{t("detail.assignedReviewers", { count: paper.assignments?.length ?? 0 })}</h2>
          <div className="table-scroll">
          <table className="w-full text-sm">
            <tbody className="divide-y dark:divide-gray-800">
              {paper.assignments?.map((a) => (
                <tr key={a.id}>
                  <td className="px-4 py-3 text-gray-900 dark:text-white">{userName(a.reviewer_id)}</td>
                  <td className="px-4 py-3"><span className={a.status === "completed" ? "badge-green" : a.status === "overdue" ? "badge-red" : "badge-yellow"}>{ASSIGNMENT_LABEL[a.status] ?? a.status}</span></td>
                  <td className="px-4 py-3 text-gray-500">{a.version_number ? `v${a.version_number}` : "—"}</td>
                  <td className="px-4 py-3 text-right text-gray-500">{fmtDate(a.assigned_at)}</td>
                  {isAdmin && (
                    <td className="px-4 py-3 text-right">
                      {a.reminder_sent_at && <span className="mr-2 text-xs text-gray-500">{t("detail.remindedAt", { date: fmtDate(a.reminder_sent_at) })}</span>}
                      {a.status !== "completed" && (
                        <button
                          type="button"
                          className="btn-secondary text-xs"
                          disabled={remindM.isPending}
                          aria-label={t("detail.remindReviewer", { name: userName(a.reviewer_id) })}
                          onClick={() => remindM.mutate(a.id)}
                        >
                          <BellRing className="w-3.5 h-3.5" /> {t("detail.remind")}
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
              {(!paper.assignments || paper.assignments.length === 0) && (
                <tr><td className="px-4 py-8 text-center text-gray-400">{t("detail.noAssignments")}</td></tr>
              )}
            </tbody>
          </table>
        </div>
        </section>
      )}

      {/* Status history */}
      {(history?.length ?? 0) > 0 && (
        <section className="card overflow-hidden">
          <h2 className="px-4 py-3 border-b font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <ListTree className="w-4 h-4" /> {t("detail.statusHistory")}
          </h2>
          <ol className="divide-y text-sm dark:divide-gray-800">
            {history!.map((entry) => (
              <li key={entry.id} className="flex flex-wrap items-center gap-2 px-4 py-2">
                <span className="text-gray-500 tabular-nums">{fmtDate(entry.changed_at)}</span>
                {entry.from_status && (
                  <>
                    <span className={PAPER_STATUS_BADGE[entry.from_status] ?? "badge-gray"}>{PAPER_STATUS_LABEL[entry.from_status] ?? entry.from_status}</span>
                    <span aria-hidden="true">→</span>
                  </>
                )}
                <span className={PAPER_STATUS_BADGE[entry.to_status] ?? "badge-gray"}>{PAPER_STATUS_LABEL[entry.to_status] ?? entry.to_status}</span>
                {entry.reason && <span className="text-gray-600 dark:text-gray-400">– {entry.reason}</span>}
                {isAdmin && entry.changed_by && <span className="ml-auto text-xs text-gray-500">{userName(entry.changed_by)}</span>}
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}

import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, Link } from "react-router-dom";
import { FileText, ArrowLeft, Download, Upload, Users, Award, UserPlus, Send, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

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
const STATUS_OPTIONS = ["submitted", "under_review", "accepted", "rejected", "revision_requested"];

const RECO_BADGE: Record<string, string> = {
  accept: "badge-green",
  reject: "badge-red",
  revision_minor: "badge-yellow",
  revision_major: "badge-yellow",
};
const RECO_LABEL: Record<string, string> = {
  accept: "Annehmen",
  reject: "Ablehnen",
  revision_minor: "Kleine Überarbeitung",
  revision_major: "Große Überarbeitung",
};

const CRITERIA: [keyof ReviewForm, string][] = [
  ["score_content", "Inhalt"],
  ["score_methodology", "Methodik"],
  ["score_presentation", "Präsentation"],
  ["score_originality", "Originalität"],
];

interface ReviewForm {
  score_content: string;
  score_methodology: string;
  score_presentation: string;
  score_originality: string;
  recommendation: string;
  comments: string;
}
const EMPTY_FORM: ReviewForm = {
  score_content: "", score_methodology: "", score_presentation: "",
  score_originality: "", recommendation: "", comments: "",
};

function fmtDate(v?: string | null) {
  return v ? new Date(v).toLocaleString("de-DE") : "—";
}
function fmtBytes(n?: number | null) {
  if (!n) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export default function PaperDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const isAdmin = useAuthStore((s) => s.hasRole("admin"));

  const { data: paper, isLoading, isError } = useQuery({
    queryKey: ["paper", id],
    queryFn: async () => (await api.get(`/papers/${id}`)).data,
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

  const team = teams?.find((t: any) => t.id === paper?.team_id);
  const levelName = levels?.find((l: any) => l.id === paper?.competition_level_id)?.name ?? "—";
  const userName = (uid: string) =>
    users?.find((u: any) => u.id === uid)?.display_name ?? `Reviewer ${uid.slice(0, 8)}`;

  const myReview = paper?.reviews?.find(
    (r: any) => r.reviewer_id === user?.id && r.revision_number === paper?.revision_number
  );
  const isAssigned = paper?.assignments?.some((a: any) => a.reviewer_id === user?.id);

  const submittedReviews = (paper?.reviews ?? []).filter(
    (r: any) => r.is_submitted && r.revision_number === paper?.revision_number && r.total_score != null
  );
  const avgScore = submittedReviews.length
    ? (submittedReviews.reduce((s: number, r: any) => s + r.total_score, 0) / submittedReviews.length).toFixed(1)
    : null;

  // ── Reviewer form state ────────────────────────────────────────────────
  const [form, setForm] = useState<ReviewForm>(EMPTY_FORM);
  useEffect(() => {
    if (myReview) {
      setForm({
        score_content: myReview.score_content ?? "",
        score_methodology: myReview.score_methodology ?? "",
        score_presentation: myReview.score_presentation ?? "",
        score_originality: myReview.score_originality ?? "",
        recommendation: myReview.recommendation ?? "",
        comments: myReview.comments ?? "",
      });
    }
  }, [myReview?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["paper", id] });
    qc.invalidateQueries({ queryKey: ["papers"] });
  };
  const onError = (e: any) => alert(e?.response?.data?.detail ?? "Aktion fehlgeschlagen.");

  const saveReviewM = useMutation({
    mutationFn: (submit: boolean) => {
      const payload = {
        score_content: form.score_content === "" ? null : Number(form.score_content),
        score_methodology: form.score_methodology === "" ? null : Number(form.score_methodology),
        score_presentation: form.score_presentation === "" ? null : Number(form.score_presentation),
        score_originality: form.score_originality === "" ? null : Number(form.score_originality),
        recommendation: form.recommendation || null,
        comments: form.comments || null,
      };
      return api.put(`/papers/${id}/reviews?submit=${submit}`, payload);
    },
    onSuccess: refresh,
    onError,
  });

  const [newStatus, setNewStatus] = useState("");
  const setStatusM = useMutation({
    mutationFn: (status: string) => api.put(`/papers/${id}/status?status=${status}`),
    onSuccess: refresh,
    onError,
  });

  const [assignId, setAssignId] = useState("");
  const assignM = useMutation({
    mutationFn: (reviewerId: string) => api.post(`/papers/${id}/assignments`, { reviewer_id: reviewerId }),
    onSuccess: () => { setAssignId(""); refresh(); },
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

  const handleDownload = async () => {
    try {
      const res = await api.get(`/papers/${id}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = paper?.file_name ?? "paper.pdf";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert("Datei ist nicht verfügbar (noch nicht hochgeladen).");
    }
  };

  if (isLoading) return <div className="p-6 text-gray-500">Laden...</div>;
  if (isError || !paper) {
    return (
      <div className="p-6">
        <Link to="/papers" className="btn-secondary text-sm mb-6">
          <ArrowLeft className="w-4 h-4" /> Zurück zu Paper Review
        </Link>
        <div className="card p-8 text-center text-gray-400">Paper nicht gefunden.</div>
      </div>
    );
  }

  const assignableUsers = (users ?? []).filter(
    (u: any) =>
      u.roles?.some((r: any) => r.name === "reviewer") &&
      !paper.assignments?.some((a: any) => a.reviewer_id === u.id)
  );
  const canSubmitPaper = ["draft", "revision_requested"].includes(paper.status);

  return (
    <div className="p-6 space-y-6">
      <Link to="/papers" className="btn-secondary text-sm">
        <ArrowLeft className="w-4 h-4" /> Zurück zu Paper Review
      </Link>

      {/* Header */}
      <div className="card p-6">
        <div className="flex items-start justify-between gap-4">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-start gap-2">
            <FileText className="w-6 h-6 mt-1 shrink-0" />
            {paper.title}
          </h1>
          <span className={STATUS_BADGE[paper.status] ?? "badge-gray"}>
            {STATUS_LABEL[paper.status] ?? paper.status}
          </span>
        </div>

        <dl className="mt-4 grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-4 text-sm">
          <div>
            <dt className="text-gray-500">Team</dt>
            <dd>
              {team ? (
                <Link to={`/teams/${team.id}`} className="text-primary-600 dark:text-primary-400 hover:underline flex items-center gap-1">
                  <Users className="w-3.5 h-3.5" /> {team.name}
                </Link>
              ) : (<span className="text-gray-900 dark:text-white">{paper.team_id}</span>)}
            </dd>
          </div>
          <div><dt className="text-gray-500">Stufe</dt><dd className="text-gray-900 dark:text-white">{levelName}</dd></div>
          <div><dt className="text-gray-500">Revision</dt><dd className="text-gray-900 dark:text-white">#{paper.revision_number}</dd></div>
          <div><dt className="text-gray-500">Eingereicht</dt><dd className="text-gray-900 dark:text-white">{fmtDate(paper.submitted_at)}</dd></div>
        </dl>

        {(paper.final_score != null || avgScore) && (
          <div className="mt-4 border-t pt-4 flex flex-wrap gap-6 text-sm">
            {avgScore && (
              <div className="flex items-center gap-2">
                <span className="text-gray-500">Ø Reviewer-Score</span>
                <span className="font-semibold text-gray-900 dark:text-white">{avgScore} / 10</span>
                <span className="text-gray-400">({submittedReviews.length} abgegeben)</span>
              </div>
            )}
            {paper.final_score != null && (
              <div className="flex items-center gap-2">
                <Award className="w-4 h-4 text-primary-500" />
                <span className="text-gray-500">Endergebnis</span>
                <span className="font-semibold text-gray-900 dark:text-white">{Math.round(paper.final_score * 100)}%</span>
                {paper.paper_rank != null && <span className="badge-green">Rang #{paper.paper_rank}</span>}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Abstract */}
      <section className="card p-6">
        <h2 className="font-semibold text-gray-900 dark:text-white mb-2">Abstract</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 whitespace-pre-line">
          {paper.abstract || "Kein Abstract vorhanden."}
        </p>
      </section>

      {/* File */}
      <section className="card p-4 flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm">
          <div className="font-medium text-gray-900 dark:text-white">{paper.file_name ?? "Keine Datei hochgeladen"}</div>
          {paper.file_name && <div className="text-gray-500">{fmtBytes(paper.file_size_bytes)}</div>}
        </div>
        <div className="flex items-center gap-2">
          {paper.file_name && (
            <button onClick={handleDownload} className="btn-secondary text-sm">
              <Download className="w-4 h-4" /> Herunterladen
            </button>
          )}
          {isAdmin && (
            <>
              <input
                type="file"
                accept="application/pdf"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="text-xs text-gray-500 file:mr-2 file:btn file:btn-secondary file:text-xs"
              />
              <button
                disabled={!file || uploadM.isPending}
                onClick={() => uploadM.mutate()}
                className="btn-primary text-sm disabled:opacity-40"
              >
                <Upload className="w-4 h-4" /> Hochladen
              </button>
            </>
          )}
        </div>
      </section>

      {/* ── Admin panel ──────────────────────────────────────────────── */}
      {isAdmin && (
        <section className="card p-6 space-y-5 border-primary-200 dark:border-primary-900">
          <h2 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-primary-500" /> Verwaltung (Admin)
          </h2>

          <div className="grid gap-5 md:grid-cols-2">
            {/* Status */}
            <div>
              <label className="label">Status ändern</label>
              <div className="flex items-center gap-2">
                <select className="input" value={newStatus} onChange={(e) => setNewStatus(e.target.value)}>
                  <option value="">— wählen —</option>
                  {STATUS_OPTIONS.map((s) => (<option key={s} value={s}>{STATUS_LABEL[s]}</option>))}
                </select>
                <button
                  disabled={!newStatus || setStatusM.isPending}
                  onClick={() => setStatusM.mutate(newStatus)}
                  className="btn-secondary text-sm disabled:opacity-40"
                >Anwenden</button>
              </div>
            </div>

            {/* Assign reviewer */}
            <div>
              <label className="label">Reviewer zuweisen</label>
              <div className="flex items-center gap-2">
                <select className="input" value={assignId} onChange={(e) => setAssignId(e.target.value)}>
                  <option value="">— Reviewer wählen —</option>
                  {assignableUsers.map((u: any) => (<option key={u.id} value={u.id}>{u.display_name} ({u.email})</option>))}
                </select>
                <button
                  disabled={!assignId || assignM.isPending}
                  onClick={() => assignM.mutate(assignId)}
                  className="btn-secondary text-sm disabled:opacity-40"
                ><UserPlus className="w-4 h-4" /> Zuweisen</button>
              </div>
              {assignableUsers.length === 0 && (
                <p className="text-xs text-gray-400 mt-1">Alle Reviewer sind bereits zugewiesen.</p>
              )}
            </div>
          </div>

          <div className="flex flex-wrap gap-2 border-t pt-4">
            {canSubmitPaper && (
              <button disabled={submitPaperM.isPending} onClick={() => submitPaperM.mutate()} className="btn-secondary text-sm disabled:opacity-40">
                <Send className="w-4 h-4" /> Paper einreichen
              </button>
            )}
            <button disabled={finalizeM.isPending} onClick={() => finalizeM.mutate()} className="btn-primary text-sm disabled:opacity-40">
              <Award className="w-4 h-4" /> Bewertung finalisieren
            </button>
            <span className="text-xs text-gray-400 self-center">
              Finalisieren mittelt alle abgegebenen Reviews zum Endergebnis und aktualisiert das Ranking.
            </span>
          </div>
        </section>
      )}

      {/* ── Reviewer form ────────────────────────────────────────────── */}
      {isAssigned && (
        <section className="card p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-gray-900 dark:text-white">Meine Bewertung</h2>
            <span className={myReview?.is_submitted ? "badge-green" : "badge-yellow"}>
              {myReview?.is_submitted ? "Abgegeben" : "Entwurf"}
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {CRITERIA.map(([key, label]) => (
              <div key={key}>
                <label className="label">{label} (0–10)</label>
                <input
                  type="number" min={0} max={10} step={0.5} className="input"
                  value={form[key]}
                  onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                />
              </div>
            ))}
          </div>

          <div>
            <label className="label">Empfehlung</label>
            <select className="input" value={form.recommendation} onChange={(e) => setForm({ ...form, recommendation: e.target.value })}>
              <option value="">— wählen —</option>
              {Object.entries(RECO_LABEL).map(([v, l]) => (<option key={v} value={v}>{l}</option>))}
            </select>
          </div>

          <div>
            <label className="label">Kommentare</label>
            <textarea
              className="input min-h-[6rem]" value={form.comments}
              onChange={(e) => setForm({ ...form, comments: e.target.value })}
              placeholder="Feedback für das Team…"
            />
          </div>

          <div className="flex items-center gap-2">
            <button disabled={saveReviewM.isPending} onClick={() => saveReviewM.mutate(false)} className="btn-secondary text-sm disabled:opacity-40">
              Entwurf speichern
            </button>
            <button disabled={saveReviewM.isPending} onClick={() => saveReviewM.mutate(true)} className="btn-primary text-sm disabled:opacity-40">
              <Send className="w-4 h-4" /> Bewertung abgeben
            </button>
            {myReview?.is_submitted && (
              <span className="text-xs text-gray-400">Bereits abgegeben — erneutes Speichern aktualisiert die Bewertung.</span>
            )}
          </div>
        </section>
      )}

      {/* Reviews (all) */}
      <section className="space-y-3">
        <h2 className="font-semibold text-gray-900 dark:text-white">Alle Reviews ({paper.reviews?.length ?? 0})</h2>
        {paper.reviews?.map((r: any) => (
          <div key={r.id} className="card p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm text-gray-600 dark:text-gray-300">{userName(r.reviewer_id)}</span>
              <div className="flex items-center gap-2">
                {r.recommendation && (<span className={RECO_BADGE[r.recommendation] ?? "badge-gray"}>{RECO_LABEL[r.recommendation] ?? r.recommendation}</span>)}
                <span className={r.is_submitted ? "badge-green" : "badge-yellow"}>{r.is_submitted ? "Abgegeben" : "Entwurf"}</span>
              </div>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-sm mb-3">
              {[["Inhalt", r.score_content], ["Methodik", r.score_methodology], ["Präsentation", r.score_presentation], ["Originalität", r.score_originality], ["Gesamt", r.total_score]].map(([label, val]) => (
                <div key={label as string}>
                  <div className="text-gray-500">{label}</div>
                  <div className="font-semibold text-gray-900 dark:text-white">{val ?? "—"}</div>
                </div>
              ))}
            </div>
            {r.comments && (<p className="text-sm text-gray-600 dark:text-gray-400 border-t pt-3 whitespace-pre-line">{r.comments}</p>)}
          </div>
        ))}
        {(!paper.reviews || paper.reviews.length === 0) && (<div className="card p-8 text-center text-gray-400">Noch keine Reviews</div>)}
      </section>

      {/* Assignments */}
      <section className="card overflow-hidden">
        <h2 className="px-4 py-3 border-b font-semibold text-gray-900 dark:text-white">Zugewiesene Reviewer ({paper.assignments?.length ?? 0})</h2>
        <table className="w-full text-sm">
          <tbody className="divide-y dark:divide-gray-800">
            {paper.assignments?.map((a: any) => (
              <tr key={a.id}>
                <td className="px-4 py-3 text-gray-900 dark:text-white">{userName(a.reviewer_id)}</td>
                <td className="px-4 py-3 text-right text-gray-500">{fmtDate(a.assigned_at)}</td>
              </tr>
            ))}
            {(!paper.assignments || paper.assignments.length === 0) && (
              <tr><td className="px-4 py-8 text-center text-gray-400">Keine Zuweisungen</td></tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}

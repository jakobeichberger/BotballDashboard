import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { FileText } from "lucide-react";
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

export default function PapersPage() {
  const qc = useQueryClient();
  const isAdmin = useAuthStore((s) => s.hasRole("admin"));
  const [showForm, setShowForm] = useState(false);
  const [teamId, setTeamId] = useState("");
  const [title, setTitle] = useState("");
  const [abstract, setAbstract] = useState("");

  const { data: papers, isLoading } = useQuery({
    queryKey: ["papers"],
    queryFn: async () => (await api.get("/papers")).data,
  });
  const { data: teams } = useQuery({
    queryKey: ["teams"],
    queryFn: async () => (await api.get("/teams")).data,
  });
  const { data: activeSeason } = useQuery({
    queryKey: ["season-active"],
    queryFn: async () => (await api.get("/seasons/active")).data,
    enabled: isAdmin,
  });

  const teamName = (tid: string) => teams?.find((t: any) => t.id === tid)?.name ?? tid;

  const createM = useMutation({
    mutationFn: () =>
      api.post("/papers", {
        season_id: activeSeason?.id,
        team_id: teamId,
        title,
        abstract: abstract || null,
        competition_level_id: teams?.find((t: any) => t.id === teamId)?.competition_level_id ?? null,
      }),
    onSuccess: () => {
      setShowForm(false); setTeamId(""); setTitle(""); setAbstract("");
      qc.invalidateQueries({ queryKey: ["papers"] });
    },
    onError: (e: any) => alert(e?.response?.data?.detail ?? "Anlegen fehlgeschlagen."),
  });

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <FileText className="w-6 h-6" />
          Paper Review
        </h1>
        {isAdmin && (
          <button className="btn-primary" onClick={() => setShowForm((v) => !v)}>
            {showForm ? "Abbrechen" : "+ Paper anlegen"}
          </button>
        )}
      </div>

      {isAdmin && showForm && (
        <div className="card p-5 mb-6 space-y-4">
          {!activeSeason && (
            <p className="text-sm text-red-600">Keine aktive Saison — bitte zuerst eine Saison aktivieren.</p>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label">Team</label>
              <select className="input" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
                <option value="">— Team wählen —</option>
                {teams?.map((t: any) => (<option key={t.id} value={t.id}>{t.name}</option>))}
              </select>
            </div>
            <div>
              <label className="label">Titel</label>
              <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Titel des Papers" />
            </div>
          </div>
          <div>
            <label className="label">Abstract (optional)</label>
            <textarea className="input min-h-[5rem]" value={abstract} onChange={(e) => setAbstract(e.target.value)} />
          </div>
          <div className="flex justify-end">
            <button
              className="btn-primary disabled:opacity-40"
              disabled={!activeSeason || !teamId || !title || createM.isPending}
              onClick={() => createM.mutate()}
            >
              Paper anlegen
            </button>
          </div>
        </div>
      )}

      {isLoading && <p className="text-gray-500">Laden...</p>}

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Titel</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Team</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Status</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Ergebnis</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Rang</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Eingereicht</th>
            </tr>
          </thead>
          <tbody className="divide-y dark:divide-gray-800">
            {papers?.map((paper: any) => (
              <tr key={paper.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <td className="px-4 py-3 font-medium">
                  <Link to={`/papers/${paper.id}`} className="text-primary-600 dark:text-primary-400 hover:underline">
                    {paper.title}
                  </Link>
                </td>
                <td className="px-4 py-3 text-gray-500">{teamName(paper.team_id)}</td>
                <td className="px-4 py-3">
                  <span className={STATUS_BADGE[paper.status] ?? "badge-gray"}>
                    {STATUS_LABEL[paper.status] ?? paper.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-right text-gray-700 dark:text-gray-300">
                  {paper.final_score != null ? `${Math.round(paper.final_score * 100)}%` : "—"}
                </td>
                <td className="px-4 py-3 text-right">
                  {paper.paper_rank != null ? <span className="badge-green">#{paper.paper_rank}</span> : "—"}
                </td>
                <td className="px-4 py-3 text-gray-500">
                  {paper.submitted_at ? new Date(paper.submitted_at).toLocaleDateString("de-DE") : "—"}
                </td>
              </tr>
            ))}
            {papers?.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                  Noch keine Paper eingereicht
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

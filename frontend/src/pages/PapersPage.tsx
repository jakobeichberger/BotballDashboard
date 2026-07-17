import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { api } from "@/lib/api";
import Modal from "@/components/Modal";

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
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ team_id: "", title: "", abstract: "" });
  const [file, setFile] = useState<File | null>(null);
  const { data: activeSeason } = useQuery({
    queryKey: ["seasons", "active"],
    queryFn: async () => (await api.get("/seasons/active")).data,
  });
  const { data: teams } = useQuery<any[]>({
    queryKey: ["teams"],
    queryFn: async () => (await api.get("/teams")).data,
  });
  const { data: papers, isLoading } = useQuery({
    queryKey: ["papers"],
    queryFn: async () => {
      const { data } = await api.get("/papers");
      return data;
    },
  });

  const createPaper = useMutation({
    mutationFn: async () => {
      const { data } = await api.post("/papers", { ...form, season_id: activeSeason.id });
      if (file) {
        const body = new FormData();
        body.append("file", file);
        await api.post(`/papers/${data.id}/upload`, body);
      }
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["papers"] });
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
        <button onClick={() => setOpen(true)} className="btn-primary">+ Paper einreichen</button>
      </div>

      {isLoading && <p className="text-gray-500">Laden...</p>}

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
                <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{paper.title}</td>
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
              {teams?.map((team) => <option key={team.id} value={team.id}>{team.name}</option>)}
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
            <button type="submit" className="btn-primary" disabled={!activeSeason || !form.team_id || !form.title || createPaper.isPending}>Einreichen</button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

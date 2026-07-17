import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Printer } from "lucide-react";
import { api } from "@/lib/api";
import Modal from "@/components/Modal";

const STATUS_BADGE: Record<string, string> = {
  pending: "badge-gray",
  approved: "badge-blue",
  queued: "badge-blue",
  printing: "badge-yellow",
  completed: "badge-green",
  failed: "badge-red",
  cancelled: "badge-gray",
};

export default function PrintingPage() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ team_id: "", file_name: "", material: "PLA", color: "", estimated_grams: "" });
  const { data: activeSeason } = useQuery({
    queryKey: ["seasons", "active"],
    queryFn: async () => (await api.get("/seasons/active")).data,
  });
  const { data: teams } = useQuery<any[]>({
    queryKey: ["teams"],
    queryFn: async () => (await api.get("/teams")).data,
  });
  const { data: jobs, isLoading } = useQuery({
    queryKey: ["print-jobs"],
    queryFn: async () => {
      const { data } = await api.get("/printing/jobs");
      return data;
    },
  });

  const createJob = useMutation({
    mutationFn: () => api.post("/printing/jobs", {
      team_id: form.team_id,
      season_id: activeSeason.id,
      file_name: form.file_name,
      material: form.material,
      color: form.color || null,
      estimated_grams: form.estimated_grams ? Number(form.estimated_grams) : null,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["print-jobs"] });
      setForm({ team_id: "", file_name: "", material: "PLA", color: "", estimated_grams: "" });
      setOpen(false);
    },
  });

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <Printer className="w-6 h-6" />
          3D-Druck
        </h1>
        <button onClick={() => setOpen(true)} className="btn-primary">+ Druckauftrag</button>
      </div>

      {isLoading && <p className="text-gray-500">Laden...</p>}

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Datei</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Material</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Status</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Gramm</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Min.</th>
            </tr>
          </thead>
          <tbody className="divide-y dark:divide-gray-800">
            {jobs?.map((job: any) => (
              <tr key={job.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{job.file_name}</td>
                <td className="px-4 py-3 text-gray-500">{job.material}</td>
                <td className="px-4 py-3">
                  <span className={STATUS_BADGE[job.status] ?? "badge-gray"}>{job.status}</span>
                </td>
                <td className="px-4 py-3 text-right text-gray-500">
                  {job.actual_grams ?? job.estimated_grams ?? "—"}g
                </td>
                <td className="px-4 py-3 text-right text-gray-500">
                  {job.actual_minutes ?? job.estimated_minutes ?? "—"}
                </td>
              </tr>
            ))}
            {jobs?.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                  Noch keine Druckaufträge
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <Modal open={open} title="Druckauftrag erstellen" onClose={() => setOpen(false)}>
        <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); createJob.mutate(); }}>
          <label className="block text-sm font-medium">Team *
            <select className="input mt-1 w-full" required value={form.team_id} onChange={(event) => setForm((current) => ({ ...current, team_id: event.target.value }))}>
              <option value="">Bitte wählen</option>
              {teams?.map((team) => <option key={team.id} value={team.id}>{team.name}</option>)}
            </select>
          </label>
          <label className="block text-sm font-medium">Dateiname *
            <input className="input mt-1 w-full" required value={form.file_name} onChange={(event) => setForm((current) => ({ ...current, file_name: event.target.value }))} placeholder="robot-part.3mf" />
          </label>
          <div className="grid grid-cols-2 gap-4">
            <label className="block text-sm font-medium">Material
              <select className="input mt-1 w-full" value={form.material} onChange={(event) => setForm((current) => ({ ...current, material: event.target.value }))}>
                {['PLA', 'PETG', 'ABS', 'TPU'].map((material) => <option key={material}>{material}</option>)}
              </select>
            </label>
            <label className="block text-sm font-medium">Farbe
              <input className="input mt-1 w-full" value={form.color} onChange={(event) => setForm((current) => ({ ...current, color: event.target.value }))} />
            </label>
          </div>
          <label className="block text-sm font-medium">Geschätzte Gramm
            <input className="input mt-1 w-full" type="number" min={0} step={0.1} value={form.estimated_grams} onChange={(event) => setForm((current) => ({ ...current, estimated_grams: event.target.value }))} />
          </label>
          {createJob.isError && <p className="text-sm text-red-600">Druckauftrag konnte nicht angelegt werden.</p>}
          <div className="flex justify-end gap-3">
            <button type="button" className="btn-secondary" onClick={() => setOpen(false)}>Abbrechen</button>
            <button type="submit" className="btn-primary" disabled={!activeSeason || !form.team_id || !form.file_name || createJob.isPending}>Erstellen</button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

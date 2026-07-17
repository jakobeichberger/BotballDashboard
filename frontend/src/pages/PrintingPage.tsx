import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Printer } from "lucide-react";
import { useParams } from "react-router-dom";
import { api } from "@/lib/api";
import Modal from "@/components/Modal";
import { useEvent } from "@/hooks/useEvents";
import { useAuthStore } from "@/store/authStore";
import type { EventRegistration } from "@/api/types";

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
  const { eventId = "" } = useParams();
  const { data: event } = useEvent(eventId);
  const canWrite = useAuthStore((state) => state.hasPermission("printing:write"));
  const canAdmin = useAuthStore((state) => state.hasPermission("printing:admin"));
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ team_id: "", file_name: "", material: "PLA", color: "", estimated_grams: "" });
  const [printerForm, setPrinterForm] = useState({ name: "", printer_type: "octoprint", api_url: "", device_id: "", api_key: "" });
  const [jobPrinters, setJobPrinters] = useState<Record<string, string>>({});
  const { data: registrations } = useQuery<EventRegistration[]>({
    queryKey: ["event-registrations", eventId],
    queryFn: async () => (await api.get(`/v1/events/${eventId}/registrations`)).data,
    enabled: !!eventId,
  });
  const { data: jobs, isLoading } = useQuery({
    queryKey: ["print-jobs", eventId],
    queryFn: async () => {
      const { data } = await api.get("/printing/jobs", { params: { event_id: eventId } });
      return data;
    },
  });
  const { data: printers } = useQuery<any[]>({
    queryKey: ["printers"],
    queryFn: async () => (await api.get("/printing/printers")).data,
    enabled: canAdmin,
    refetchInterval: 15_000,
  });

  const createJob = useMutation({
    mutationFn: () => api.post("/printing/jobs", {
      team_id: form.team_id,
      season_id: event?.season_id,
      event_id: eventId,
      file_name: form.file_name,
      material: form.material,
      color: form.color || null,
      estimated_grams: form.estimated_grams ? Number(form.estimated_grams) : null,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["print-jobs", eventId] });
      setForm({ team_id: "", file_name: "", material: "PLA", color: "", estimated_grams: "" });
      setOpen(false);
    },
  });
  const createPrinter = useMutation({
    mutationFn: () => api.post("/printing/printers", { ...printerForm, device_id: printerForm.device_id || null }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["printers"] }); setPrinterForm({ name: "", printer_type: "octoprint", api_url: "", device_id: "", api_key: "" }); },
  });
  const changeJob = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "approve" | "queue" }) => action === "approve" ? api.put(`/printing/jobs/${id}/approve`) : api.patch(`/printing/jobs/${id}`, { status: "queued", printer_id: jobPrinters[id] }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["print-jobs", eventId] }),
  });

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <Printer className="w-6 h-6" />
          3D-Druck
        </h1>
        {canWrite && <button onClick={() => setOpen(true)} className="btn-primary">+ Druckauftrag</button>}
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
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Fortschritt</th>
              {canAdmin && <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Aktion</th>}
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
                <td className="px-4 py-3 text-gray-500">{job.progress != null ? `${job.progress.toFixed(0)}%` : job.status_message ?? "—"}</td>
                {canAdmin && <td className="px-4 py-3">{job.status === "pending" ? <button className="btn-secondary" onClick={() => changeJob.mutate({ id: job.id, action: "approve" })}>Freigeben</button> : job.status === "approved" ? <div className="flex gap-2"><select className="input" aria-label="Drucker wählen" value={jobPrinters[job.id] ?? ""} onChange={(event) => setJobPrinters((current) => ({ ...current, [job.id]: event.target.value }))}><option value="">Drucker</option>{printers?.map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}</select><button className="btn-secondary" disabled={!jobPrinters[job.id]} onClick={() => changeJob.mutate({ id: job.id, action: "queue" })}>Einreihen</button></div> : null}</td>}
              </tr>
            ))}
            {jobs?.length === 0 && (
              <tr>
                <td colSpan={canAdmin ? 7 : 6} className="px-4 py-8 text-center text-gray-400">
                  Noch keine Druckaufträge
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {canAdmin && <section className="card mt-6 p-5"><h2 className="mb-4 text-lg font-semibold">Drucker-Adapter</h2><div className="mb-4 grid gap-2 md:grid-cols-5">{printers?.map((printer) => <div key={printer.id} className="rounded-lg border p-3 text-sm"><p className="font-semibold">{printer.name}</p><p className={printer.is_online ? "text-green-600" : "text-gray-500"}>{printer.is_online ? "online" : "offline"} · {printer.printer_type}</p></div>)}</div><form className="grid gap-2 md:grid-cols-6" onSubmit={(event) => { event.preventDefault(); createPrinter.mutate(); }}><input required className="input" placeholder="Name" value={printerForm.name} onChange={(event) => setPrinterForm({ ...printerForm, name: event.target.value })} /><select className="input" value={printerForm.printer_type} onChange={(event) => setPrinterForm({ ...printerForm, printer_type: event.target.value })}><option value="octoprint">OctoPrint</option><option value="bambu">Bambu LAN</option></select><input required className="input" placeholder="URL / Host" value={printerForm.api_url} onChange={(event) => setPrinterForm({ ...printerForm, api_url: event.target.value })} /><input className="input" placeholder="Bambu Seriennummer" value={printerForm.device_id} onChange={(event) => setPrinterForm({ ...printerForm, device_id: event.target.value })} /><input required type="password" autoComplete="new-password" className="input" placeholder="API-Key / Access Code" value={printerForm.api_key} onChange={(event) => setPrinterForm({ ...printerForm, api_key: event.target.value })} /><button className="btn-primary" disabled={createPrinter.isPending}>Verbinden</button></form></section>}
      <Modal open={open} title="Druckauftrag erstellen" onClose={() => setOpen(false)}>
        <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); createJob.mutate(); }}>
          <label className="block text-sm font-medium">Team *
            <select className="input mt-1 w-full" required value={form.team_id} onChange={(event) => setForm((current) => ({ ...current, team_id: event.target.value }))}>
              <option value="">Bitte wählen</option>
              {registrations?.map((registration) => <option key={registration.id} value={registration.team_id}>{registration.team_name}</option>)}
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
            <button type="submit" className="btn-primary" disabled={!event || !form.team_id || !form.file_name || createJob.isPending}>Erstellen</button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

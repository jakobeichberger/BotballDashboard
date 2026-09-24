import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Printer } from "lucide-react";
import { useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { EventLink } from "@/components/EventLink";
import Modal from "@/components/Modal";
import { PrintingExportButtons } from "@/components/ExportButtons";
import { useEvent } from "@/hooks/useEvents";
import { useAuthStore } from "@/store/authStore";
import type { EventRegistration } from "@/api/types";
import {
  PRINT_FILE_ACCEPT,
  PRINT_REFRESH_MS,
  PRINTER_STATE_LABEL,
  PRINTER_TYPE_LABEL,
  STATUS_BADGE,
  STATUS_LABEL,
  apiError,
  formatDuration,
  uploadPrintFile,
  type PrintJob,
  type PrintJobCreated,
  type PrinterInfo,
} from "@/lib/printing";

const EMPTY_FORM = { team_id: "", material: "PLA", color: "", estimated_grams: "", estimated_minutes: "", notes: "", quota_override: false };
const EMPTY_PRINTER = { name: "", printer_type: "octoprint", api_url: "", device_id: "", api_key: "" };

export default function PrintingPage() {
  const { eventId = "" } = useParams();
  const { data: event } = useEvent(eventId);
  const canWrite = useAuthStore((state) => state.hasPermission("printing:write"));
  const canAdmin = useAuthStore((state) => state.hasPermission("printing:admin"));
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [file, setFile] = useState<File | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [printerForm, setPrinterForm] = useState(EMPTY_PRINTER);
  const [jobPrinters, setJobPrinters] = useState<Record<string, string>>({});
  // Mentors may only submit for teams they belong to; the backend enforces
  // this too (assert_team_access), this keeps the choice list honest.
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
  const { data: jobs, isLoading } = useQuery<PrintJob[]>({
    queryKey: ["print-jobs", eventId],
    queryFn: async () => (await api.get("/printing/jobs", { params: { event_id: eventId } })).data,
    refetchInterval: PRINT_REFRESH_MS,
  });
  // Everyone with printing:read sees the printer status; connection details
  // are only returned to printing:admin.
  const { data: printers } = useQuery<PrinterInfo[]>({
    queryKey: ["printers"],
    queryFn: async () => (await api.get("/printing/printers")).data,
    refetchInterval: 15_000,
  });
  const teamName = (teamId: string) => registrations?.find((r) => r.team_id === teamId)?.team_name ?? "";
  const invalidateJobs = () => queryClient.invalidateQueries({ queryKey: ["print-jobs", eventId] });

  const createJob = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("no file");
      const { data } = await api.post<PrintJobCreated>("/printing/jobs", {
        team_id: form.team_id,
        season_id: event?.season_id,
        event_id: eventId,
        file_name: file.name,
        material: form.material,
        color: form.color || null,
        estimated_grams: form.estimated_grams ? Number(form.estimated_grams) : null,
        estimated_minutes: form.estimated_minutes ? Number(form.estimated_minutes) : null,
        notes: form.notes || null,
        quota_override: canAdmin && form.quota_override,
      });
      try {
        await uploadPrintFile(data.id, file);
      } catch (error) {
        // The job exists but has no file: withdraw it so it does not block the quota.
        await api.put(`/printing/jobs/${data.id}/cancel`).catch(() => undefined);
        throw error;
      }
      return data;
    },
    onSuccess: (data) => {
      invalidateJobs();
      setNotice(data.quota_warning);
      setForm(EMPTY_FORM);
      setFile(null);
      setOpen(false);
    },
  });
  const createPrinter = useMutation({
    mutationFn: () => api.post("/printing/printers", {
      ...printerForm,
      api_url: printerForm.api_url || null,
      api_key: printerForm.api_key || null,
      device_id: printerForm.device_id || null,
    }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["printers"] }); setPrinterForm(EMPTY_PRINTER); },
  });
  const changeJob = useMutation({
    mutationFn: ({ id, action, reason }: { id: string; action: "approve" | "queue" | "reject" | "cancel"; reason?: string }) => {
      if (action === "approve") return api.put(`/printing/jobs/${id}/approve`);
      if (action === "reject") return api.put(`/printing/jobs/${id}/reject`, { reason });
      if (action === "cancel") return api.put(`/printing/jobs/${id}/cancel`);
      return api.patch(`/printing/jobs/${id}`, { status: "queued", printer_id: jobPrinters[id] });
    },
    onSuccess: invalidateJobs,
    onError: (error) => setNotice(apiError(error)),
  });
  const reject = (id: string) => {
    const reason = window.prompt("Begründung für die Ablehnung");
    if (reason?.trim()) changeJob.mutate({ id, action: "reject", reason: reason.trim() });
  };
  const isGeneric = printerForm.printer_type === "generic";

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <Printer className="w-6 h-6" />
          3D-Druck
        </h1>
        <div className="flex flex-wrap items-center gap-2">
          {canAdmin && event?.season_id && <PrintingExportButtons seasonId={event.season_id} seasonYear={event.slug} />}
          {canWrite && <button onClick={() => setOpen(true)} className="btn-primary">+ Druckauftrag</button>}
        </div>
      </div>

      {notice && (
        <div role="status" className="mb-4 flex items-start gap-2 rounded-lg border border-yellow-300 bg-yellow-50 p-3 text-sm text-yellow-900 dark:border-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-100">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="flex-1">{notice}</span>
          <button className="text-xs underline" onClick={() => setNotice(null)}>Schließen</button>
        </div>
      )}

      {!!printers?.length && (
        <section className="mb-6" aria-label="Druckerstatus">
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {printers.filter((printer) => printer.is_active).map((printer) => (
              <div key={printer.id} className="card p-3 text-sm">
                <p className="font-semibold text-gray-900 dark:text-white">{printer.name}</p>
                <p className={printer.is_online ? "text-green-600" : "text-gray-500"}>
                  {printer.printer_type === "generic"
                    ? "manuell"
                    : printer.is_online
                      ? PRINTER_STATE_LABEL[printer.current_state ?? ""] ?? "online"
                      : "offline"}
                  {" · "}{PRINTER_TYPE_LABEL[printer.printer_type] ?? printer.printer_type}
                </p>
                {printer.status_message && printer.current_state === "failed" && <p className="text-xs text-red-600">{printer.status_message}</p>}
              </div>
            ))}
          </div>
        </section>
      )}

      {isLoading && <p className="text-gray-500">Laden...</p>}

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Datei</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Team</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Material</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Status</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Gramm</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Fortschritt</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Aktion</th>
            </tr>
          </thead>
          <tbody className="divide-y dark:divide-gray-800">
            {jobs?.map((job) => (
              <tr key={job.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">
                  <EventLink to={`/printing/jobs/${job.id}`} className="text-primary-700 hover:underline dark:text-primary-300">{job.file_name}</EventLink>
                  {!job.file_url && <span className="ml-2 badge-gray">ohne Datei</span>}
                </td>
                <td className="px-4 py-3 text-gray-500">{teamName(job.team_id)}</td>
                <td className="px-4 py-3 text-gray-500">{job.material}</td>
                <td className="px-4 py-3">
                  <span className={STATUS_BADGE[job.status] ?? "badge-gray"}>{STATUS_LABEL[job.status] ?? job.status}</span>
                  {job.status === "rejected" && job.rejection_reason && <p className="mt-1 text-xs text-red-600">{job.rejection_reason}</p>}
                </td>
                <td className="px-4 py-3 text-right text-gray-500">
                  {job.actual_grams ?? job.estimated_grams ?? "—"}g
                </td>
                <td className="px-4 py-3 text-gray-500">
                  {job.status === "printing" && job.progress != null
                    ? `${job.progress.toFixed(0)}% · noch ${formatDuration(job.remaining_seconds)}`
                    : job.error_message ?? job.status_message ?? "—"}
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-2">
                    {canAdmin && job.status === "pending" && (
                      <>
                        <button className="btn-secondary" onClick={() => changeJob.mutate({ id: job.id, action: "approve" })}>Freigeben</button>
                        <button className="btn-secondary" onClick={() => reject(job.id)}>Ablehnen</button>
                      </>
                    )}
                    {canAdmin && job.status === "approved" && (
                      <>
                        <select className="input" aria-label="Drucker wählen" value={jobPrinters[job.id] ?? ""} onChange={(e) => setJobPrinters((current) => ({ ...current, [job.id]: e.target.value }))}>
                          <option value="">Drucker</option>
                          {printers?.filter((printer) => printer.is_active).map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}
                        </select>
                        <button className="btn-secondary" disabled={!jobPrinters[job.id]} onClick={() => changeJob.mutate({ id: job.id, action: "queue" })}>Einreihen</button>
                      </>
                    )}
                    {!canAdmin && canWrite && job.status === "pending" && (
                      <button className="btn-secondary" onClick={() => changeJob.mutate({ id: job.id, action: "cancel" })}>Zurückziehen</button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {jobs?.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                  Noch keine Druckaufträge
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {canAdmin && (
        <section className="card mt-6 p-5">
          <h2 className="mb-4 text-lg font-semibold">Drucker-Adapter</h2>
          <form className="grid gap-2 md:grid-cols-6" onSubmit={(e) => { e.preventDefault(); createPrinter.mutate(); }}>
            <input required className="input" placeholder="Name" value={printerForm.name} onChange={(e) => setPrinterForm({ ...printerForm, name: e.target.value })} />
            <select className="input" aria-label="Druckertyp" value={printerForm.printer_type} onChange={(e) => setPrinterForm({ ...printerForm, printer_type: e.target.value })}>
              {Object.entries(PRINTER_TYPE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            <input required={!isGeneric} disabled={isGeneric} className="input" placeholder="URL / Host" value={printerForm.api_url} onChange={(e) => setPrinterForm({ ...printerForm, api_url: e.target.value })} />
            <input disabled={printerForm.printer_type !== "bambu"} className="input" placeholder="Bambu Seriennummer" value={printerForm.device_id} onChange={(e) => setPrinterForm({ ...printerForm, device_id: e.target.value })} />
            <input required={!isGeneric} disabled={isGeneric} type="password" autoComplete="new-password" className="input" placeholder="API-Key / Access Code" value={printerForm.api_key} onChange={(e) => setPrinterForm({ ...printerForm, api_key: e.target.value })} />
            <button className="btn-primary" disabled={createPrinter.isPending}>{isGeneric ? "Anlegen" : "Verbinden"}</button>
          </form>
        </section>
      )}
      <Modal open={open} title="Druckauftrag erstellen" onClose={() => setOpen(false)}>
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); createJob.mutate(); }}>
          <label className="block text-sm font-medium">Team *
            <select className="input mt-1 w-full" required value={form.team_id} onChange={(e) => setForm((current) => ({ ...current, team_id: e.target.value }))}>
              <option value="">Bitte wählen</option>
              {registrations
                ?.filter((registration) => canAdmin || myTeams?.some((team) => team.id === registration.team_id))
                .map((registration) => <option key={registration.id} value={registration.team_id}>{registration.team_name}</option>)}
            </select>
          </label>
          <label className="block text-sm font-medium">Datei * <span className="font-normal text-gray-500">(STL, 3MF, OBJ, G-Code)</span>
            <input className="input mt-1 w-full" type="file" accept={PRINT_FILE_ACCEPT} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <div className="grid grid-cols-2 gap-4">
            <label className="block text-sm font-medium">Material
              <select className="input mt-1 w-full" value={form.material} onChange={(e) => setForm((current) => ({ ...current, material: e.target.value }))}>
                {["PLA", "PETG", "ABS", "TPU"].map((material) => <option key={material}>{material}</option>)}
              </select>
            </label>
            <label className="block text-sm font-medium">Farbe
              <input className="input mt-1 w-full" value={form.color} onChange={(e) => setForm((current) => ({ ...current, color: e.target.value }))} />
            </label>
            <label className="block text-sm font-medium">Geschätzte Gramm
              <input className="input mt-1 w-full" type="number" min={0} step={0.1} value={form.estimated_grams} onChange={(e) => setForm((current) => ({ ...current, estimated_grams: e.target.value }))} />
            </label>
            <label className="block text-sm font-medium">Geschätzte Minuten
              <input className="input mt-1 w-full" type="number" min={0} step={1} value={form.estimated_minutes} onChange={(e) => setForm((current) => ({ ...current, estimated_minutes: e.target.value }))} />
            </label>
          </div>
          <label className="block text-sm font-medium">Hinweise
            <textarea className="input mt-1 w-full" rows={2} value={form.notes} onChange={(e) => setForm((current) => ({ ...current, notes: e.target.value }))} placeholder="z.B. 0.2 mm Layer Height" />
          </label>
          {canAdmin && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.quota_override} onChange={(e) => setForm((current) => ({ ...current, quota_override: e.target.checked }))} />
              Kontingent überschreiben (Admin)
            </label>
          )}
          {createJob.isError && <p className="text-sm text-red-600">{apiError(createJob.error, "Druckauftrag konnte nicht angelegt werden.")}</p>}
          <div className="flex justify-end gap-3">
            <button type="button" className="btn-secondary" onClick={() => setOpen(false)}>Abbrechen</button>
            <button type="submit" className="btn-primary" disabled={!event || !form.team_id || !file || createJob.isPending}>Erstellen</button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

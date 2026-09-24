import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { Printer, ArrowLeft, Users, Clock, CheckCircle2, Download, Upload, XCircle, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";
import { EventLink } from "@/components/EventLink";
import { useAuthStore } from "@/store/authStore";
import {
  NEXT_STATUSES,
  PRINT_FILE_ACCEPT,
  PRINT_REFRESH_MS,
  STATUS_BADGE,
  STATUS_LABEL,
  apiError,
  downloadPrintFile,
  formatBytes,
  formatDuration,
  uploadPrintFile,
  type FilamentSpool,
  type PrintJob,
  type PrintJobStatus,
  type PrinterInfo,
} from "@/lib/printing";

function fmtDate(v?: string | null) {
  return v ? new Date(v).toLocaleString("de-DE") : "—";
}

function spoolLabel(spool: FilamentSpool) {
  return [spool.material, spool.color, spool.brand].filter(Boolean).join(" · ") + ` (${Math.round(spool.remaining_grams)} g)`;
}

export default function PrintJobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const canAdmin = useAuthStore((s) => s.hasPermission("printing:admin"));
  const canWrite = useAuthStore((s) => s.hasPermission("printing:write"));
  const [message, setMessage] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [printerId, setPrinterId] = useState("");
  const [completion, setCompletion] = useState<{ grams: string; minutes: string; spool: string } | null>(null);

  const { data: job, isLoading, isError } = useQuery<PrintJob>({
    queryKey: ["print-job", id],
    queryFn: async () => (await api.get(`/printing/jobs/${id}`)).data,
    enabled: !!id,
    refetchInterval: PRINT_REFRESH_MS,
  });
  const { data: printers } = useQuery<PrinterInfo[]>({
    queryKey: ["printers"],
    queryFn: async () => (await api.get("/printing/printers")).data,
  });
  const { data: spools } = useQuery<FilamentSpool[]>({
    queryKey: ["spools"],
    queryFn: async () => (await api.get("/printing/spools")).data,
    enabled: canAdmin,
  });
  const { data: teams } = useQuery<{ id: string; name: string }[]>({
    queryKey: ["teams"],
    queryFn: async () => (await api.get("/teams")).data,
  });

  const printer = printers?.find((p) => p.id === job?.printer_id);
  const spool = spools?.find((s) => s.id === job?.spool_id);
  const team = teams?.find((t) => t.id === job?.team_id);

  const onSuccess = () => {
    setMessage(null);
    qc.invalidateQueries({ queryKey: ["print-job", id] });
    qc.invalidateQueries({ queryKey: ["print-jobs"] });
    qc.invalidateQueries({ queryKey: ["spools"] });
  };
  const onError = (e: unknown) => setMessage(apiError(e));
  const approveM = useMutation({ mutationFn: () => api.put(`/printing/jobs/${id}/approve`), onSuccess, onError });
  const rejectM = useMutation({
    mutationFn: () => api.put(`/printing/jobs/${id}/reject`, { reason: rejectReason.trim() }),
    onSuccess: () => { setRejectReason(""); onSuccess(); },
    onError,
  });
  const cancelM = useMutation({ mutationFn: () => api.put(`/printing/jobs/${id}/cancel`), onSuccess, onError });
  const patchM = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.patch(`/printing/jobs/${id}`, body),
    onSuccess: () => { setCompletion(null); onSuccess(); },
    onError,
  });
  const uploadM = useMutation({ mutationFn: (file: File) => uploadPrintFile(id!, file), onSuccess, onError });
  const downloadM = useMutation({ mutationFn: () => downloadPrintFile(job!), onError });

  if (isLoading) {
    return <div className="p-6 text-gray-500">Laden...</div>;
  }

  if (isError || !job) {
    return (
      <div className="p-6">
        <EventLink to="/printing" className="btn-secondary text-sm mb-6">
          <ArrowLeft className="w-4 h-4" /> Zurück zu 3D-Druck
        </EventLink>
        <div className="card p-8 text-center text-gray-400">Druckauftrag nicht gefunden.</div>
      </div>
    );
  }

  const status = job.status as PrintJobStatus;
  const canReplaceFile = canAdmin ? !["printing", "completed", "cancelled", "rejected"].includes(status) : canWrite && status === "pending";
  const canCancel = canAdmin ? NEXT_STATUSES[status].includes("cancelled") : canWrite && status === "pending";
  const openCompletion = () => setCompletion({
    grams: job.actual_grams?.toString() ?? job.estimated_grams?.toString() ?? "",
    minutes: job.actual_minutes?.toString() ?? "",
    spool: job.spool_id ?? "",
  });
  const submitCompletion = () => {
    if (!completion) return;
    patchM.mutate({
      ...(status === "completed" ? {} : { status: "completed" }),
      actual_grams: completion.grams ? Number(completion.grams) : null,
      actual_minutes: completion.minutes ? Number(completion.minutes) : null,
      spool_id: completion.spool || null,
    });
  };

  const details: [string, string][] = [
    ["Material", job.material],
    ["Farbe", job.color ?? "—"],
    ["Priorität", String(job.priority)],
    ["Gramm (geschätzt)", job.estimated_grams != null ? `${job.estimated_grams} g` : "—"],
    ["Gramm (tatsächlich)", job.actual_grams != null ? `${job.actual_grams} g` : "—"],
    ["Minuten (geschätzt)", job.estimated_minutes != null ? `${job.estimated_minutes}` : "—"],
    ["Minuten (tatsächlich)", job.actual_minutes != null ? `${job.actual_minutes}` : "—"],
    ["Drucker", printer?.name ?? "—"],
    ["Filament-Spule", spool ? spoolLabel(spool) : job.spool_id ? "zugewiesen" : "—"],
    ["Datei", job.file_url ? formatBytes(job.file_size_bytes) : "keine Datei"],
  ];

  const timeline: [string, string | null][] = [
    ["Erstellt", job.created_at],
    ["Genehmigt", job.approved_at],
    ["Gestartet", job.started_at],
    ["Abgeschlossen", job.completed_at],
  ];

  return (
    <div className="p-6 space-y-6">
      <EventLink to="/printing" className="btn-secondary text-sm">
        <ArrowLeft className="w-4 h-4" /> Zurück zu 3D-Druck
      </EventLink>

      {message && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-200">{message}</p>}

      {/* Header */}
      <div className="card p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
              <Printer className="w-6 h-6" />
              {job.file_name}
            </h1>
            {team && (
              <EventLink to={`/teams/${team.id}`} className="text-sm text-primary-600 dark:text-primary-400 hover:underline flex items-center gap-1 mt-1">
                <Users className="w-3.5 h-3.5" /> {team.name}
              </EventLink>
            )}
          </div>
          <span className={STATUS_BADGE[status] ?? "badge-gray"}>
            {STATUS_LABEL[status] ?? job.status}
          </span>
        </div>

        {status === "printing" && (
          <div className="mt-4">
            <div className="flex justify-between text-sm text-gray-600 dark:text-gray-400">
              <span>{job.progress != null ? `${job.progress.toFixed(0)} %` : "läuft"}</span>
              <span>Restzeit: {formatDuration(job.remaining_seconds)}</span>
            </div>
            <div className="mt-1 h-2 rounded bg-gray-200 dark:bg-gray-700" role="progressbar" aria-valuenow={job.progress ?? 0} aria-valuemin={0} aria-valuemax={100}>
              <div className="h-2 rounded bg-primary-500" style={{ width: `${Math.min(100, job.progress ?? 0)}%` }} />
            </div>
          </div>
        )}
        {job.error_message && (
          <p className="mt-4 flex items-center gap-2 text-sm text-red-600"><AlertTriangle className="w-4 h-4" /> {job.error_message}</p>
        )}
        {status === "rejected" && job.rejection_reason && (
          <p className="mt-4 text-sm text-red-600"><strong>Ablehnungsgrund:</strong> {job.rejection_reason}</p>
        )}
        {job.quota_override && <p className="mt-2 text-xs text-yellow-700 dark:text-yellow-300">Über dem Kontingent eingereicht (Admin-Override).</p>}

        <dl className="mt-4 grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-4 text-sm">
          {details.map(([label, val]) => (
            <div key={label}>
              <dt className="text-gray-500">{label}</dt>
              <dd className="text-gray-900 dark:text-white">{val}</dd>
            </div>
          ))}
        </dl>

        <div className="mt-4 flex flex-wrap gap-3 border-t pt-3">
          {job.file_url && (
            <button className="btn-secondary text-sm" disabled={downloadM.isPending} onClick={() => downloadM.mutate()}>
              <Download className="w-4 h-4" /> Datei herunterladen
            </button>
          )}
          {canReplaceFile && (
            <label className="btn-secondary text-sm cursor-pointer">
              <Upload className="w-4 h-4" /> {job.file_url ? "Datei ersetzen" : "Datei hochladen"}
              <input type="file" className="sr-only" accept={PRINT_FILE_ACCEPT} disabled={uploadM.isPending} onChange={(e) => { const file = e.target.files?.[0]; if (file) uploadM.mutate(file); e.target.value = ""; }} />
            </label>
          )}
          {canCancel && (
            <button className="btn-secondary text-sm" disabled={cancelM.isPending} onClick={() => { if (window.confirm("Druckauftrag abbrechen?")) cancelM.mutate(); }}>
              <XCircle className="w-4 h-4" /> {canAdmin ? "Abbrechen" : "Zurückziehen"}
            </button>
          )}
        </div>

        {job.notes && (
          <p className="mt-4 text-sm text-gray-600 dark:text-gray-400 border-t pt-3">{job.notes}</p>
        )}
      </div>

      {/* Admin actions */}
      {canAdmin && (
        <section className="card p-6 space-y-4 border-primary-200 dark:border-primary-900">
          <h2 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-primary-500" /> Verwaltung
          </h2>
          <div className="flex flex-wrap items-end gap-3">
            {status === "pending" && (
              <button disabled={approveM.isPending} onClick={() => approveM.mutate()} className="btn-primary text-sm disabled:opacity-40">
                <CheckCircle2 className="w-4 h-4" /> Genehmigen
              </button>
            )}
            {(status === "approved" || status === "failed") && (
              <>
                <label className="text-sm">Drucker
                  <select className="input mt-1 block" value={printerId || job.printer_id || ""} onChange={(e) => setPrinterId(e.target.value)}>
                    <option value="">Bitte wählen</option>
                    {printers?.filter((p) => p.is_active).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </label>
                <button className="btn-primary text-sm" disabled={!(printerId || job.printer_id) || patchM.isPending} onClick={() => patchM.mutate({ status: "queued", printer_id: printerId || job.printer_id })}>
                  Einreihen
                </button>
              </>
            )}
            {status === "queued" && (
              <button className="btn-secondary text-sm" disabled={patchM.isPending} onClick={() => patchM.mutate({ status: "printing" })}>Druck gestartet</button>
            )}
            {(status === "queued" || status === "printing") && (
              <button className="btn-secondary text-sm" disabled={patchM.isPending} onClick={() => patchM.mutate({ status: "failed" })}>Fehlgeschlagen</button>
            )}
            {(NEXT_STATUSES[status].includes("completed") || status === "completed") && !completion && (
              <button className="btn-secondary text-sm" onClick={openCompletion}>{status === "completed" ? "Verbrauch bearbeiten" : "Als fertig markieren"}</button>
            )}
          </div>

          {completion && (
            <form className="grid gap-3 sm:grid-cols-4 items-end" onSubmit={(e) => { e.preventDefault(); submitCompletion(); }}>
              <label className="text-sm">Verbrauch (g)
                <input className="input mt-1 w-full" type="number" min={0} step={0.1} value={completion.grams} onChange={(e) => setCompletion({ ...completion, grams: e.target.value })} />
              </label>
              <label className="text-sm">Druckzeit (min)
                <input className="input mt-1 w-full" type="number" min={0} step={1} value={completion.minutes} onChange={(e) => setCompletion({ ...completion, minutes: e.target.value })} />
              </label>
              <label className="text-sm">Spule
                <select className="input mt-1 w-full" value={completion.spool} onChange={(e) => setCompletion({ ...completion, spool: e.target.value })}>
                  <option value="">Keine</option>
                  {spools?.map((s) => <option key={s.id} value={s.id}>{spoolLabel(s)}</option>)}
                </select>
              </label>
              <div className="flex gap-2">
                <button type="submit" className="btn-primary text-sm" disabled={patchM.isPending}>Speichern</button>
                <button type="button" className="btn-secondary text-sm" onClick={() => setCompletion(null)}>Abbrechen</button>
              </div>
            </form>
          )}

          {(status === "pending" || status === "approved") && (
            <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); rejectM.mutate(); }}>
              <label className="text-sm flex-1 min-w-[16rem]">Ablehnungsgrund
                <input className="input mt-1 w-full" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} placeholder="z.B. Modell zu groß für das Druckbett" />
              </label>
              <button type="submit" className="btn-secondary text-sm" disabled={!rejectReason.trim() || rejectM.isPending}>Ablehnen</button>
            </form>
          )}
        </section>
      )}

      {/* Timeline */}
      <section className="card p-6">
        <h2 className="font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <Clock className="w-4 h-4" /> Verlauf
        </h2>
        <ul className="space-y-3 text-sm">
          {timeline.map(([label, val]) => (
            <li key={label} className="flex items-center gap-3">
              <span className={`w-2 h-2 rounded-full ${val ? "bg-primary-500" : "bg-gray-300 dark:bg-gray-700"}`} />
              <span className="text-gray-500 w-40">{label}</span>
              <span className="text-gray-900 dark:text-white">{fmtDate(val)}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

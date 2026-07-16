import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, Link } from "react-router-dom";
import { Printer, ArrowLeft, Users, Clock, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

const JOB_STATUS = ["pending", "approved", "queued", "printing", "completed", "failed", "cancelled"];

const STATUS_BADGE: Record<string, string> = {
  pending: "badge-gray",
  approved: "badge-blue",
  queued: "badge-blue",
  printing: "badge-yellow",
  completed: "badge-green",
  failed: "badge-red",
  cancelled: "badge-gray",
};

const STATUS_LABEL: Record<string, string> = {
  pending: "Ausstehend",
  approved: "Genehmigt",
  queued: "In Warteschlange",
  printing: "Druckt",
  completed: "Fertig",
  failed: "Fehlgeschlagen",
  cancelled: "Abgebrochen",
};

function fmtDate(v?: string | null) {
  return v ? new Date(v).toLocaleString("de-DE") : "—";
}

export default function PrintJobDetailPage() {
  const { id } = useParams<{ id: string }>();

  // No single-job GET endpoint exists — derive from the jobs list.
  const { data: jobs, isLoading, isError } = useQuery({
    queryKey: ["print-jobs"],
    queryFn: async () => (await api.get("/printing/jobs")).data,
  });

  const { data: printers } = useQuery({
    queryKey: ["printers"],
    queryFn: async () => (await api.get("/printing/printers")).data,
  });

  const { data: teams } = useQuery({
    queryKey: ["teams"],
    queryFn: async () => (await api.get("/teams")).data,
  });

  const qc = useQueryClient();
  const isAdmin = useAuthStore((s) => s.hasRole("admin"));

  const job = jobs?.find((j: any) => j.id === id);
  const printer = printers?.find((p: any) => p.id === job?.printer_id);
  const team = teams?.find((t: any) => t.id === job?.team_id);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["print-jobs"] });
  const onError = (e: any) => alert(e?.response?.data?.detail ?? "Aktion fehlgeschlagen.");
  const approveM = useMutation({
    mutationFn: () => api.put(`/printing/jobs/${id}/approve`),
    onSuccess: invalidate, onError,
  });
  const statusM = useMutation({
    mutationFn: (status: string) => api.patch(`/printing/jobs/${id}`, { status }),
    onSuccess: invalidate, onError,
  });

  if (isLoading) {
    return <div className="p-6 text-gray-500">Laden...</div>;
  }

  if (isError || !job) {
    return (
      <div className="p-6">
        <Link to="/printing" className="btn-secondary text-sm mb-6">
          <ArrowLeft className="w-4 h-4" /> Zurück zu 3D-Druck
        </Link>
        <div className="card p-8 text-center text-gray-400">Druckauftrag nicht gefunden.</div>
      </div>
    );
  }

  const details: [string, string][] = [
    ["Material", job.material],
    ["Farbe", job.color ?? "—"],
    ["Priorität", String(job.priority)],
    ["Gramm (geschätzt)", job.estimated_grams != null ? `${job.estimated_grams} g` : "—"],
    ["Gramm (tatsächlich)", job.actual_grams != null ? `${job.actual_grams} g` : "—"],
    ["Minuten (geschätzt)", job.estimated_minutes != null ? `${job.estimated_minutes}` : "—"],
    ["Minuten (tatsächlich)", job.actual_minutes != null ? `${job.actual_minutes}` : "—"],
    ["Drucker", printer?.name ?? "—"],
  ];

  const timeline: [string, string | null][] = [
    ["Erstellt", job.created_at],
    ["Genehmigt", job.approved_at],
    ["Gestartet", job.started_at],
    ["Abgeschlossen", job.completed_at],
  ];

  return (
    <div className="p-6 space-y-6">
      <Link to="/printing" className="btn-secondary text-sm">
        <ArrowLeft className="w-4 h-4" /> Zurück zu 3D-Druck
      </Link>

      {/* Header */}
      <div className="card p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
              <Printer className="w-6 h-6" />
              {job.file_name}
            </h1>
            {team && (
              <Link to={`/teams/${team.id}`} className="text-sm text-primary-600 dark:text-primary-400 hover:underline flex items-center gap-1 mt-1">
                <Users className="w-3.5 h-3.5" /> {team.name}
              </Link>
            )}
          </div>
          <span className={STATUS_BADGE[job.status] ?? "badge-gray"}>
            {STATUS_LABEL[job.status] ?? job.status}
          </span>
        </div>

        <dl className="mt-4 grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-4 text-sm">
          {details.map(([label, val]) => (
            <div key={label}>
              <dt className="text-gray-500">{label}</dt>
              <dd className="text-gray-900 dark:text-white">{val}</dd>
            </div>
          ))}
        </dl>

        {job.notes && (
          <p className="mt-4 text-sm text-gray-600 dark:text-gray-400 border-t pt-3">{job.notes}</p>
        )}
      </div>

      {/* Admin actions */}
      {isAdmin && (
        <section className="card p-6 space-y-4 border-primary-200 dark:border-primary-900">
          <h2 className="font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-primary-500" /> Verwaltung (Admin)
          </h2>
          <div className="flex flex-wrap items-center gap-3">
            {job.status === "pending" && (
              <button
                disabled={approveM.isPending}
                onClick={() => approveM.mutate()}
                className="btn-primary text-sm disabled:opacity-40"
              >
                <CheckCircle2 className="w-4 h-4" /> Genehmigen
              </button>
            )}
            <div className="flex items-center gap-2">
              <span className="label mb-0">Status</span>
              <select
                className="input"
                value={job.status}
                onChange={(e) => statusM.mutate(e.target.value)}
                disabled={statusM.isPending}
              >
                {JOB_STATUS.map((s) => (
                  <option key={s} value={s}>{STATUS_LABEL[s] ?? s}</option>
                ))}
              </select>
            </div>
          </div>
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

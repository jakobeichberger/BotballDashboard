import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Printer } from "lucide-react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

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
  const qc = useQueryClient();
  const isAdmin = useAuthStore((s) => s.hasRole("admin"));
  const isMentor = useAuthStore((s) => s.hasRole("mentor"));
  const canCreate = isAdmin || isMentor;

  const [showForm, setShowForm] = useState(false);
  const [teamId, setTeamId] = useState("");
  const [fileName, setFileName] = useState("");
  const [material, setMaterial] = useState("PLA");
  const [color, setColor] = useState("");
  const [grams, setGrams] = useState("");

  const { data: jobs, isLoading } = useQuery({
    queryKey: ["print-jobs"],
    queryFn: async () => (await api.get("/printing/jobs")).data,
  });
  const { data: teams } = useQuery({
    queryKey: ["teams"],
    queryFn: async () => (await api.get("/teams")).data,
  });
  const { data: myTeams } = useQuery({
    queryKey: ["teams-mine"],
    queryFn: async () => (await api.get("/teams/mine")).data,
    enabled: canCreate && !isAdmin,
  });
  const { data: activeSeason } = useQuery({
    queryKey: ["season-active"],
    queryFn: async () => (await api.get("/seasons/active")).data,
    enabled: canCreate,
  });

  const createTeams = isAdmin ? teams : myTeams;

  const createM = useMutation({
    mutationFn: () =>
      api.post("/printing/jobs", {
        season_id: activeSeason?.id,
        team_id: teamId,
        file_name: fileName,
        material,
        color: color || null,
        estimated_grams: grams === "" ? null : Number(grams),
      }),
    onSuccess: () => {
      setShowForm(false); setTeamId(""); setFileName(""); setColor(""); setGrams("");
      qc.invalidateQueries({ queryKey: ["print-jobs"] });
    },
    onError: (e: any) => alert(e?.response?.data?.detail ?? "Anlegen fehlgeschlagen."),
  });

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <Printer className="w-6 h-6" />
          3D-Druck
        </h1>
        {canCreate && (
          <button className="btn-primary" onClick={() => setShowForm((v) => !v)}>
            {showForm ? "Abbrechen" : "+ Druckauftrag"}
          </button>
        )}
      </div>

      {canCreate && showForm && (
        <div className="card p-5 mb-6 space-y-4">
          {!activeSeason && (
            <p className="text-sm text-red-600">Keine aktive Saison — bitte zuerst eine Saison aktivieren.</p>
          )}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <label className="label">Team</label>
              <select className="input" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
                <option value="">— Team wählen —</option>
                {createTeams?.map((t: any) => (<option key={t.id} value={t.id}>{t.name}</option>))}
              </select>
            </div>
            <div>
              <label className="label">Datei</label>
              <input className="input" value={fileName} onChange={(e) => setFileName(e.target.value)} placeholder="bauteil.3mf" />
            </div>
            <div>
              <label className="label">Material</label>
              <select className="input" value={material} onChange={(e) => setMaterial(e.target.value)}>
                <option value="PLA">PLA</option>
                <option value="PETG">PETG</option>
              </select>
            </div>
            <div>
              <label className="label">Farbe</label>
              <input className="input" value={color} onChange={(e) => setColor(e.target.value)} placeholder="z. B. Schwarz" />
            </div>
            <div>
              <label className="label">Gramm (geschätzt)</label>
              <input type="number" min={0} className="input" value={grams} onChange={(e) => setGrams(e.target.value)} />
            </div>
          </div>
          <div className="flex justify-end">
            <button
              className="btn-primary disabled:opacity-40"
              disabled={!activeSeason || !teamId || !fileName || createM.isPending}
              onClick={() => createM.mutate()}
            >
              Druckauftrag einreichen
            </button>
          </div>
        </div>
      )}

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
                <td className="px-4 py-3 font-medium">
                  <Link to={`/printing/jobs/${job.id}`} className="text-primary-600 dark:text-primary-400 hover:underline">
                    {job.file_name}
                  </Link>
                </td>
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
    </div>
  );
}

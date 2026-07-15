import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Users, Grid3x3 } from "lucide-react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

export default function TeamsPage() {
  const qc = useQueryClient();
  const isAdmin = useAuthStore((s) => s.hasRole("admin"));
  const [show, setShow] = useState(false);
  const [form, setForm] = useState<any>({ name: "", team_number: "", school: "", city: "", country: "DE", competition_level_id: "", notes: "" });

  const { data: teams, isLoading } = useQuery({
    queryKey: ["teams"],
    queryFn: async () => (await api.get("/teams")).data,
  });
  const { data: levels } = useQuery({
    queryKey: ["competition-levels"],
    queryFn: async () => (await api.get("/seasons/competition-levels/all")).data,
    enabled: isAdmin,
  });

  const createM = useMutation({
    mutationFn: () => api.post("/teams", {
      ...form,
      team_number: form.team_number || null,
      school: form.school || null,
      city: form.city || null,
      competition_level_id: form.competition_level_id || null,
      notes: form.notes || null,
    }),
    onSuccess: () => {
      setShow(false);
      setForm({ name: "", team_number: "", school: "", city: "", country: "DE", competition_level_id: "", notes: "" });
      qc.invalidateQueries({ queryKey: ["teams"] });
    },
    onError: (e: any) => alert(e?.response?.data?.detail ?? "Anlegen fehlgeschlagen."),
  });

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <Users className="w-6 h-6" />
          Teams
        </h1>
        <div className="flex items-center gap-2">
          <Link to="/teams/matrix" className="btn-secondary">
            <Grid3x3 className="w-4 h-4" /> Saison-Zuweisung
          </Link>
          {isAdmin && (
            <button className="btn-primary" onClick={() => setShow((v) => !v)}>
              {show ? "Abbrechen" : "+ Team hinzufügen"}
            </button>
          )}
        </div>
      </div>

      {isAdmin && show && (
        <div className="card p-5 mb-6 space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[["name", "Name"], ["team_number", "Team-Nr."], ["school", "Schule"], ["city", "Ort"], ["country", "Land"]].map(([key, label]) => (
              <div key={key}>
                <label className="label">{label}</label>
                <input className="input" value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
              </div>
            ))}
            <div>
              <label className="label">Wettbewerbsstufe</label>
              <select className="input" value={form.competition_level_id} onChange={(e) => setForm({ ...form, competition_level_id: e.target.value })}>
                <option value="">— keine —</option>
                {levels?.map((l: any) => (<option key={l.id} value={l.id}>{l.name}</option>))}
              </select>
            </div>
          </div>
          <div>
            <label className="label">Notizen</label>
            <textarea className="input min-h-[4rem]" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          </div>
          <div className="flex justify-end">
            <button className="btn-primary disabled:opacity-40" disabled={!form.name || createM.isPending} onClick={() => createM.mutate()}>
              Team anlegen
            </button>
          </div>
        </div>
      )}

      {isLoading && <p className="text-gray-500">Laden...</p>}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {teams?.map((team: any) => (
          <Link
            key={team.id}
            to={`/teams/${team.id}`}
            className="card p-4 block hover:shadow-md hover:border-primary-300 dark:hover:border-primary-700 transition-all"
          >
            <div className="flex items-start justify-between">
              <div>
                <h3 className="font-semibold text-gray-900 dark:text-white">{team.name}</h3>
                {team.team_number && (<span className="text-xs text-gray-500">#{team.team_number}</span>)}
              </div>
              <span className={team.is_active ? "badge-green" : "badge-gray"}>
                {team.is_active ? "Aktiv" : "Inaktiv"}
              </span>
            </div>
            {team.school && (<p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{team.school}</p>)}
            {team.city && (<p className="text-sm text-gray-500 mt-0.5">{team.city}, {team.country}</p>)}
          </Link>
        ))}
        {teams?.length === 0 && (
          <div className="col-span-3 text-center py-12 text-gray-400">Noch keine Teams angelegt</div>
        )}
      </div>
    </div>
  );
}

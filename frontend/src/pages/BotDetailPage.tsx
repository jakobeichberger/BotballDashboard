import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, Link, useNavigate } from "react-router-dom";
import { Bot as BotIcon, ArrowLeft, Users, Pencil, Trash2, Save, X, Upload } from "lucide-react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import BotImage from "@/components/BotImage";

export default function BotDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const isAdmin = useAuthStore((s) => s.hasRole("admin"));
  const isMentor = useAuthStore((s) => s.hasRole("mentor"));

  const { data: bot, isLoading, isError } = useQuery({
    queryKey: ["bot", id],
    queryFn: async () => (await api.get(`/bots/${id}`)).data,
    enabled: !!id,
  });
  const { data: teams } = useQuery({
    queryKey: ["teams"],
    queryFn: async () => (await api.get("/teams")).data,
  });
  const { data: seasons } = useQuery({
    queryKey: ["seasons"],
    queryFn: async () => (await api.get("/seasons")).data,
  });
  const { data: myTeams } = useQuery({
    queryKey: ["teams-mine"],
    queryFn: async () => (await api.get("/teams/mine")).data,
    enabled: isMentor && !isAdmin,
  });

  const team = teams?.find((t: any) => t.id === bot?.team_id);
  const seasonName = seasons?.find((s: any) => s.id === bot?.season_id)?.name;
  const isMyTeamBot = !!myTeams?.some((t: any) => t.id === bot?.team_id);
  // External bots (no team) are organizer-only; own-team bots also allow mentors.
  const canManage = isAdmin || (isMentor && isMyTeamBot);

  const refresh = () => { qc.invalidateQueries({ queryKey: ["bot", id] }); qc.invalidateQueries({ queryKey: ["bots"] }); };
  const onError = (e: any) => alert(e?.response?.data?.detail ?? "Aktion fehlgeschlagen.");

  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<any>({});
  const startEdit = () => {
    setForm({
      name: bot.name, season_id: bot.season_id ?? "", description: bot.description ?? "",
      functionality: bot.functionality ?? "", drive_type: bot.drive_type ?? "", sensors: bot.sensors ?? "",
    });
    setEditing(true);
  };
  const updateM = useMutation({
    mutationFn: () => api.patch(`/bots/${id}`, { ...form, season_id: form.season_id || null }),
    onSuccess: () => { setEditing(false); refresh(); },
    onError,
  });
  const deleteM = useMutation({
    mutationFn: () => api.delete(`/bots/${id}`),
    onSuccess: () => navigate("/bots"),
    onError,
  });

  const [file, setFile] = useState<File | null>(null);
  const uploadM = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      fd.append("file", file as File);
      return api.post(`/bots/${id}/image`, fd);
    },
    onSuccess: () => { setFile(null); refresh(); },
    onError,
  });

  if (isLoading) return <div className="p-6 text-gray-500">Laden...</div>;
  if (isError || !bot) {
    return (
      <div className="p-6">
        <Link to="/bots" className="btn-secondary text-sm mb-6"><ArrowLeft className="w-4 h-4" /> Zurück zur Galerie</Link>
        <div className="card p-8 text-center text-gray-400">Bot nicht gefunden.</div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <Link to="/bots" className="btn-secondary text-sm"><ArrowLeft className="w-4 h-4" /> Zurück zur Galerie</Link>
        {canManage && !editing && (
          <div className="flex items-center gap-2">
            <button onClick={startEdit} className="btn-secondary text-sm"><Pencil className="w-4 h-4" /> Bearbeiten</button>
            <button onClick={() => { if (confirm(`Bot \"${bot.name}\" wirklich löschen?`)) deleteM.mutate(); }}
                    className="btn-danger text-sm"><Trash2 className="w-4 h-4" /> Löschen</button>
          </div>
        )}
      </div>

      <div className="card overflow-hidden">
        <BotImage botId={bot.id} imageName={bot.image_name} className="h-64 w-full" />
        <div className="p-6">
          {editing ? (
            <div className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <div><label className="label">Name</label><input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
                <div>
                  <label className="label">Saison</label>
                  <select className="input" value={form.season_id} onChange={(e) => setForm({ ...form, season_id: e.target.value })}>
                    <option value="">— keine —</option>
                    {seasons?.map((s: any) => (<option key={s.id} value={s.id}>{s.name}</option>))}
                  </select>
                </div>
                <div><label className="label">Antrieb</label><input className="input" value={form.drive_type} onChange={(e) => setForm({ ...form, drive_type: e.target.value })} /></div>
                <div className="sm:col-span-2 lg:col-span-3"><label className="label">Sensorik</label><input className="input" value={form.sensors} onChange={(e) => setForm({ ...form, sensors: e.target.value })} /></div>
              </div>
              <div><label className="label">Kurzbeschreibung</label><input className="input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
              <div><label className="label">Funktionsweise</label><textarea className="input min-h-[8rem]" value={form.functionality} onChange={(e) => setForm({ ...form, functionality: e.target.value })} /></div>
              <div className="flex items-center gap-2">
                <button className="btn-primary text-sm disabled:opacity-40" disabled={!form.name || updateM.isPending} onClick={() => updateM.mutate()}><Save className="w-4 h-4" /> Speichern</button>
                <button className="btn-secondary text-sm" onClick={() => setEditing(false)}><X className="w-4 h-4" /> Abbrechen</button>
              </div>
            </div>
          ) : (
            <>
              <div className="flex items-start justify-between gap-4">
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
                  <BotIcon className="w-6 h-6" /> {bot.name}
                </h1>
                <span className={bot.team_id ? "badge-blue" : "badge-gray"}>{bot.team_id ? "Eigenes Team" : "Externes Team"}</span>
              </div>
              <dl className="mt-4 grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-4 text-sm">
                <div>
                  <dt className="text-gray-500">Team</dt>
                  <dd>
                    {team ? (
                      <Link to={`/teams/${team.id}`} className="text-primary-600 dark:text-primary-400 hover:underline flex items-center gap-1">
                        <Users className="w-3.5 h-3.5" /> {team.name}
                      </Link>
                    ) : (<span className="text-gray-900 dark:text-white">{bot.external_team_name ?? "—"}</span>)}
                  </dd>
                </div>
                <div><dt className="text-gray-500">Saison</dt><dd className="text-gray-900 dark:text-white">{seasonName ?? "—"}</dd></div>
                <div><dt className="text-gray-500">Antrieb</dt><dd className="text-gray-900 dark:text-white">{bot.drive_type ?? "—"}</dd></div>
                <div><dt className="text-gray-500">Sensorik</dt><dd className="text-gray-900 dark:text-white">{bot.sensors ?? "—"}</dd></div>
              </dl>
              {bot.description && <p className="mt-4 text-sm text-gray-600 dark:text-gray-400 border-t pt-3">{bot.description}</p>}
            </>
          )}
        </div>
      </div>

      {/* Functionality */}
      {!editing && (
        <section className="card p-6">
          <h2 className="font-semibold text-gray-900 dark:text-white mb-2">Funktionsweise</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 whitespace-pre-line">
            {bot.functionality || "Keine Beschreibung der Funktionsweise vorhanden."}
          </p>
        </section>
      )}

      {/* Image upload */}
      {canManage && (
        <section className="card p-4 flex flex-wrap items-center justify-between gap-3">
          <div className="text-sm">
            <div className="font-medium text-gray-900 dark:text-white">{bot.image_name ?? "Kein Bild hochgeladen"}</div>
            <div className="text-gray-500 text-xs">PNG, JPEG, GIF oder WebP</div>
          </div>
          <div className="flex items-center gap-2">
            <input type="file" accept="image/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                   className="text-xs text-gray-500 file:mr-2 file:btn file:btn-secondary file:text-xs" />
            <button disabled={!file || uploadM.isPending} onClick={() => uploadM.mutate()} className="btn-primary text-sm disabled:opacity-40">
              <Upload className="w-4 h-4" /> Bild hochladen
            </button>
          </div>
        </section>
      )}
    </div>
  );
}

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Bot as BotIcon } from "lucide-react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import BotImage from "@/components/BotImage";

type Owner = "team" | "external";

export default function BotsPage() {
  const qc = useQueryClient();
  const isAdmin = useAuthStore((s) => s.hasRole("admin"));
  const isMentor = useAuthStore((s) => s.hasRole("mentor"));
  const canCreate = isAdmin || isMentor;

  const [seasonFilter, setSeasonFilter] = useState("");
  const [scope, setScope] = useState<"" | "own" | "external">("");

  const { data: bots, isLoading } = useQuery({
    queryKey: ["bots", seasonFilter, scope],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (seasonFilter) params.set("season_id", seasonFilter);
      if (scope === "external") params.set("external", "true");
      if (scope === "own") params.set("external", "false");
      const qs = params.toString();
      return (await api.get(`/bots${qs ? `?${qs}` : ""}`)).data;
    },
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
    enabled: canCreate && !isAdmin,
  });

  const teamName = (tid: string | null) => teams?.find((t: any) => t.id === tid)?.name ?? tid;
  const seasonName = (sid: string | null) => seasons?.find((s: any) => s.id === sid)?.name;
  const createTeams = isAdmin ? teams : myTeams;

  // ── create form ────────────────────────────────────────────────────────
  const [show, setShow] = useState(false);
  const [owner, setOwner] = useState<Owner>("team");
  const [form, setForm] = useState<any>({
    name: "", team_id: "", external_team_name: "", season_id: "",
    description: "", functionality: "", drive_type: "", sensors: "",
  });

  const createM = useMutation({
    mutationFn: () =>
      api.post("/bots", {
        name: form.name,
        team_id: owner === "team" ? form.team_id : null,
        external_team_name: owner === "external" ? form.external_team_name : null,
        season_id: form.season_id || null,
        description: form.description || null,
        functionality: form.functionality || null,
        drive_type: form.drive_type || null,
        sensors: form.sensors || null,
      }),
    onSuccess: () => {
      setShow(false);
      setForm({ name: "", team_id: "", external_team_name: "", season_id: "", description: "", functionality: "", drive_type: "", sensors: "" });
      qc.invalidateQueries({ queryKey: ["bots"] });
    },
    onError: (e: any) => alert(e?.response?.data?.detail ?? "Anlegen fehlgeschlagen."),
  });

  const ownerValid = owner === "team" ? !!form.team_id : !!form.external_team_name;

  return (
    <div className="p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <BotIcon className="w-6 h-6" /> Bot-Galerie
        </h1>
        <div className="flex flex-wrap items-center gap-2">
          <select aria-label="Saison filtern" className="input text-sm w-44" value={seasonFilter} onChange={(e) => setSeasonFilter(e.target.value)}>
            <option value="">Alle Saisons</option>
            {seasons?.map((s: any) => (<option key={s.id} value={s.id}>{s.name}</option>))}
          </select>
          <select aria-label="Teams filtern" className="input text-sm w-40" value={scope} onChange={(e) => setScope(e.target.value as any)}>
            <option value="">Alle Teams</option>
            <option value="own">Eigene Teams</option>
            <option value="external">Externe Teams</option>
          </select>
          {canCreate && (
            <button className="btn-primary" onClick={() => setShow((v) => !v)}>{show ? "Abbrechen" : "+ Bot anlegen"}</button>
          )}
        </div>
      </div>

      {canCreate && show && (
        <div className="card p-5 mb-6 space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <label className="label">Name</label>
              <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="z. B. RoboLion X1" />
            </div>
            {isAdmin && (
              <div>
                <label className="label">Zugehörigkeit</label>
                <select className="input" value={owner} onChange={(e) => setOwner(e.target.value as Owner)}>
                  <option value="team">Eigenes Team</option>
                  <option value="external">Externes Team</option>
                </select>
              </div>
            )}
            {owner === "team" ? (
              <div>
                <label className="label">Team</label>
                <select className="input" value={form.team_id} onChange={(e) => setForm({ ...form, team_id: e.target.value })}>
                  <option value="">— Team wählen —</option>
                  {createTeams?.map((t: any) => (<option key={t.id} value={t.id}>{t.name}</option>))}
                </select>
              </div>
            ) : (
              <div>
                <label className="label">Externes Team</label>
                <input className="input" value={form.external_team_name} onChange={(e) => setForm({ ...form, external_team_name: e.target.value })} placeholder="z. B. Team Zürich" />
              </div>
            )}
            <div>
              <label className="label">Saison</label>
              <select className="input" value={form.season_id} onChange={(e) => setForm({ ...form, season_id: e.target.value })}>
                <option value="">— keine —</option>
                {seasons?.map((s: any) => (<option key={s.id} value={s.id}>{s.name}</option>))}
              </select>
            </div>
            <div>
              <label className="label">Antrieb</label>
              <input className="input" value={form.drive_type} onChange={(e) => setForm({ ...form, drive_type: e.target.value })} placeholder="z. B. Differential" />
            </div>
            <div>
              <label className="label">Sensorik</label>
              <input className="input" value={form.sensors} onChange={(e) => setForm({ ...form, sensors: e.target.value })} placeholder="z. B. 2x IR, Kamera" />
            </div>
          </div>
          <div>
            <label className="label">Kurzbeschreibung</label>
            <input className="input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
          <div>
            <label className="label">Funktionsweise</label>
            <textarea className="input min-h-[6rem]" value={form.functionality} onChange={(e) => setForm({ ...form, functionality: e.target.value })}
                      placeholder="Wie funktioniert der Roboter? Aufbau, Antrieb, Strategie …" />
          </div>
          <div className="flex justify-end">
            <button className="btn-primary disabled:opacity-40" disabled={!form.name || !ownerValid || createM.isPending} onClick={() => createM.mutate()}>
              Bot anlegen
            </button>
          </div>
          <p className="text-xs text-gray-400">Bild kann nach dem Anlegen auf der Detailseite hochgeladen werden.</p>
        </div>
      )}

      {isLoading && <p className="text-gray-500">Laden...</p>}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {bots?.map((bot: any) => (
          <Link key={bot.id} to={`/bots/${bot.id}`}
                className="card block overflow-hidden hover:shadow-md hover:border-primary-300 dark:hover:border-primary-700 transition-all">
            <BotImage botId={bot.id} imageName={bot.image_name} className="h-40 w-full" />
            <div className="p-4">
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-semibold text-gray-900 dark:text-white">{bot.name}</h3>
                <span className={bot.team_id ? "badge-blue" : "badge-gray"}>{bot.team_id ? "Eigenes" : "Extern"}</span>
              </div>
              <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                {bot.team_id ? teamName(bot.team_id) : bot.external_team_name}
              </p>
              {bot.season_id && <p className="text-xs text-gray-400 mt-0.5">{seasonName(bot.season_id)}</p>}
              {bot.description && (
                <p className="text-sm text-gray-500 mt-2 line-clamp-2">{bot.description}</p>
              )}
            </div>
          </Link>
        ))}
        {bots?.length === 0 && (
          <div className="col-span-3 text-center py-12 text-gray-400">Noch keine Bots in der Galerie</div>
        )}
      </div>
    </div>
  );
}

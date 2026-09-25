import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Bot as BotIcon } from "lucide-react";
import { api } from "@/lib/api";
import { EventLink } from "@/components/EventLink";
import { useAuthStore } from "@/store/authStore";
import BotImage from "@/components/BotImage";
import { toast } from "@/lib/toast";

type Owner = "team" | "external";

export default function BotsPage() {
  const { t } = useTranslation("bots");
  const qc = useQueryClient();
  const isAdmin = useAuthStore((s) => s.hasPermission("teams:admin"));
  const isMentor = useAuthStore((s) => s.hasPermission("teams:write"));
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

  const teamName = (tid: string | null) => teams?.find((team: any) => team.id === tid)?.name ?? tid;
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
    onError: (e: unknown) => toast.apiError(e, t("createFailed")),
  });

  const ownerValid = owner === "team" ? !!form.team_id : !!form.external_team_name;

  return (
    <div className="p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <h1 className="text-2xl font-bold text-fg flex items-center gap-2">
          <BotIcon className="w-6 h-6" /> {t("title")}
        </h1>
        <div className="flex flex-wrap items-center gap-2">
          <select aria-label={t("filter.season")} className="input text-sm w-44" value={seasonFilter} onChange={(e) => setSeasonFilter(e.target.value)}>
            <option value="">{t("filter.allSeasons")}</option>
            {seasons?.map((s: any) => (<option key={s.id} value={s.id}>{s.name}</option>))}
          </select>
          <select aria-label={t("filter.teams")} className="input text-sm w-40" value={scope} onChange={(e) => setScope(e.target.value as any)}>
            <option value="">{t("filter.allTeams")}</option>
            <option value="own">{t("filter.ownTeams")}</option>
            <option value="external">{t("filter.externalTeams")}</option>
          </select>
          {canCreate && (
            <button className="btn-primary" onClick={() => setShow((v) => !v)}>{show ? t("common:cancel") : t("add")}</button>
          )}
        </div>
      </div>

      {canCreate && show && (
        <div className="card p-5 mb-6 space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <label htmlFor="botspage-f1" className="label">{t("common:name")}</label>
              <input id="botspage-f1" className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder={t("form.namePlaceholder")} />
            </div>
            {isAdmin && (
              <div>
                <label htmlFor="botspage-f2" className="label">{t("form.owner")}</label>
                <select id="botspage-f2" className="input" value={owner} onChange={(e) => setOwner(e.target.value as Owner)}>
                  <option value="team">{t("form.ownTeam")}</option>
                  <option value="external">{t("form.externalTeam")}</option>
                </select>
              </div>
            )}
            {owner === "team" ? (
              <div>
                <label htmlFor="botspage-f3" className="label">{t("form.team")}</label>
                <select id="botspage-f3" className="input" value={form.team_id} onChange={(e) => setForm({ ...form, team_id: e.target.value })}>
                  <option value="">{t("form.chooseTeam")}</option>
                  {createTeams?.map((team: any) => (<option key={team.id} value={team.id}>{team.name}</option>))}
                </select>
              </div>
            ) : (
              <div>
                <label htmlFor="botspage-f4" className="label">{t("form.externalTeam")}</label>
                <input id="botspage-f4" className="input" value={form.external_team_name} onChange={(e) => setForm({ ...form, external_team_name: e.target.value })} placeholder={t("form.externalPlaceholder")} />
              </div>
            )}
            <div>
              <label htmlFor="botspage-f5" className="label">{t("form.season")}</label>
              <select id="botspage-f5" className="input" value={form.season_id} onChange={(e) => setForm({ ...form, season_id: e.target.value })}>
                <option value="">{t("form.noSeason")}</option>
                {seasons?.map((s: any) => (<option key={s.id} value={s.id}>{s.name}</option>))}
              </select>
            </div>
            <div>
              <label htmlFor="botspage-f6" className="label">{t("form.drive")}</label>
              <input id="botspage-f6" className="input" value={form.drive_type} onChange={(e) => setForm({ ...form, drive_type: e.target.value })} placeholder={t("form.drivePlaceholder")} />
            </div>
            <div>
              <label htmlFor="botspage-f7" className="label">{t("form.sensors")}</label>
              <input id="botspage-f7" className="input" value={form.sensors} onChange={(e) => setForm({ ...form, sensors: e.target.value })} placeholder={t("form.sensorsPlaceholder")} />
            </div>
          </div>
          <div>
            <label htmlFor="botspage-f8" className="label">{t("form.description")}</label>
            <input id="botspage-f8" className="input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
          <div>
            <label htmlFor="botspage-f9" className="label">{t("form.functionality")}</label>
            <textarea id="botspage-f9" className="input min-h-[6rem]" value={form.functionality} onChange={(e) => setForm({ ...form, functionality: e.target.value })}
                      placeholder={t("form.functionalityPlaceholder")} />
          </div>
          <div className="flex justify-end">
            <button className="btn-primary disabled:opacity-40" disabled={!form.name || !ownerValid || createM.isPending} onClick={() => createM.mutate()}>
              {t("form.create")}
            </button>
          </div>
          <p className="text-xs text-leise">{t("form.imageHint")}</p>
        </div>
      )}

      {isLoading && <p className="text-leise">{t("common:loading")}</p>}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {bots?.map((bot: any) => (
          <EventLink key={bot.id} to={`/bots/${bot.id}`}
                className="card block overflow-hidden hover:shadow-md hover:border-primary/40 transition-all">
            <BotImage botId={bot.id} imageName={bot.image_name} className="h-40 w-full" />
            <div className="p-4">
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-semibold text-fg">{bot.name}</h3>
                <span className={bot.team_id ? "badge-blue" : "badge-gray"}>{bot.team_id ? t("own") : t("external")}</span>
              </div>
              <p className="text-sm text-leise mt-1">
                {bot.team_id ? teamName(bot.team_id) : bot.external_team_name}
              </p>
              {bot.season_id && <p className="text-xs text-leise mt-0.5">{seasonName(bot.season_id)}</p>}
              {bot.description && (
                <p className="text-sm text-leise mt-2 line-clamp-2">{bot.description}</p>
              )}
            </div>
          </EventLink>
        ))}
        {bots?.length === 0 && (
          <div className="col-span-3 text-center py-12 text-leise">{t("empty")}</div>
        )}
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Settings } from "lucide-react";
import { api } from "@/lib/api";
import { useEvent } from "@/hooks/useEvents";
import { MODULE_LABELS, useEventModules, type ModuleKey } from "@/hooks/useEventModules";
import { useAuthStore } from "@/store/authStore";
import type { ScoringSchema } from "@/api/types";
import SchemaEditor from "@/modules/scoring/sheet/SchemaEditor";
import SeasonRulesEditor from "@/modules/scoring/extras/SeasonRulesEditor";
import QualificationPanel from "@/modules/scoring/extras/QualificationPanel";
import { localized } from "@/i18n/config";
import PhaseManager from "@/components/events/PhaseManager";
import RegistrationManager from "@/components/events/RegistrationManager";
import EventBracketWeights from "@/components/events/EventBracketWeights";

const MODULE_ORDER = Object.keys(MODULE_LABELS) as ModuleKey[];
const BASE_MODULES: ModuleKey[] = ["seeding", "paper", "printing", "bots"];

/** Modules a new event of `season` starts with (mirrors backend modules_for_season). */
function defaultModules(season?: Record<string, unknown>): string[] {
  if (!season) return BASE_MODULES;
  return MODULE_ORDER.filter((key) => {
    const flag = MODULE_LABELS[key].seasonFlag;
    return flag ? !!season[flag] : BASE_MODULES.includes(key);
  });
}

const EVENT_STATUSES = ["draft", "published", "live", "completed", "archived"];
const PUBLIC_FLAGS = ["public_scoreboard", "public_schedule", "public_results", "public_announcements"] as const;

export default function EventSetupPage() {
  const { t } = useTranslation("events");
  const { eventId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: event } = useEvent(eventId);
  const modules = useEventModules(eventId);
  const canPublishAnnouncements = useAuthStore((state) => state.hasPermission("dashboard:write"));
  const canAdminEvent = useAuthStore((state) => state.hasPermission("events:admin"));
  const seasons = useQuery<any[]>({ queryKey: ["seasons"], queryFn: async () => (await api.get("/seasons")).data });
  const schema = useQuery<ScoringSchema>({ queryKey: ["event-schema", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/scoring-schema`)).data, enabled: !!eventId, retry: false });
  const announcements = useQuery<any[]>({ queryKey: ["announcements", eventId], queryFn: async () => (await api.get("/dashboard/announcements", { params: { season_id: event?.season_id } })).data.filter((item: any) => item.event_id === eventId), enabled: !!eventId && !!event });
  const [form, setForm] = useState({ season_id: "", name: "", slug: "", timezone: "Europe/Vienna", venue: "", status: "draft", table_count: 1, active_modules: BASE_MODULES as string[], public_scoreboard: false, public_schedule: false, public_results: false, public_announcements: false });
  const [newSeason, setNewSeason] = useState({ name: "", year: new Date().getFullYear() });
  const [announcement, setAnnouncement] = useState({ title: "", body: "" });
  const [message, setMessage] = useState("");
  useEffect(() => { if (event) setForm((current) => ({ ...current, ...event, venue: event.venue ?? "" })); }, [event]);
  const saveEvent = useMutation({ mutationFn: async () => eventId ? api.patch(`/v1/events/${eventId}`, form) : api.post("/v1/events", form), onSuccess: ({ data }) => { queryClient.invalidateQueries({ queryKey: ["events"] }); queryClient.invalidateQueries({ queryKey: ["event-modules"] }); setMessage(t("setup.saved")); if (!eventId) navigate(`/events/${data.id}/settings`, { replace: true }); }, onError: (error: any) => setMessage(error.response?.data?.detail ?? t("setup.saveFailed")) });
  const createSeason = useMutation({ mutationFn: async () => api.post("/seasons", { ...newSeason, is_active: true, create_default_event: false }), onSuccess: ({ data }) => { queryClient.invalidateQueries({ queryKey: ["seasons"] }); setForm((current) => ({ ...current, season_id: data.id })); setMessage(t("setup.seasonCreated")); } });
  const publishAnnouncement = useMutation({ mutationFn: async () => { const created = await api.post("/dashboard/announcements", { ...announcement, season_id: event?.season_id, event_id: eventId, audience: "all" }); return api.put(`/dashboard/announcements/${created.data.id}/publish`); }, onSuccess: () => { setAnnouncement({ title: "", body: "" }); queryClient.invalidateQueries({ queryKey: ["announcements", eventId] }); } });
  return (
    <div className="mx-auto max-w-6xl p-4 md:p-6"><h1 className="mb-6 flex items-center gap-2 text-2xl font-bold"><Settings />{eventId ? t("setup.title") : t("setup.firstEvent")}</h1>
      <form className="card grid gap-4 p-5 md:grid-cols-2" onSubmit={(e) => { e.preventDefault(); saveEvent.mutate(); }}>
        {!eventId && seasons.data?.length === 0 && <fieldset className="grid gap-3 rounded-lg border p-4 md:col-span-2 md:grid-cols-[1fr_8rem_auto]"><legend className="px-2 font-semibold">{t("setup.firstSeason")}</legend><input required className="input" placeholder={t("setup.seasonName")} value={newSeason.name} onChange={(e) => setNewSeason({ ...newSeason, name: e.target.value })} /><input required className="input" type="number" min={2020} max={2100} value={newSeason.year} onChange={(e) => setNewSeason({ ...newSeason, year: Number(e.target.value) })} /><button type="button" className="btn-secondary" disabled={!newSeason.name || createSeason.isPending} onClick={() => createSeason.mutate()}>{t("setup.createSeason")}</button></fieldset>}
        {!eventId && <label className="text-sm font-medium">{t("setup.season")}<select required className="input mt-1 w-full" value={form.season_id} onChange={(e) => setForm({ ...form, season_id: e.target.value, active_modules: defaultModules(seasons.data?.find((item) => item.id === e.target.value)) })}><option value="">{t("setup.chooseSeason")}</option>{seasons.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
        <label className="text-sm font-medium">{t("common:name")}<input required className="input mt-1 w-full" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        <label className="text-sm font-medium">{t("setup.slug")}<input required className="input mt-1 w-full" value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") })} /></label>
        <label className="text-sm font-medium">{t("setup.timezone")}<input required className="input mt-1 w-full" value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} /></label>
        <label className="text-sm font-medium">{t("setup.venue")}<input className="input mt-1 w-full" value={form.venue} onChange={(e) => setForm({ ...form, venue: e.target.value })} /></label>
        <label className="text-sm font-medium">{t("common:status")}<select className="input mt-1 w-full" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>{EVENT_STATUSES.map((status) => <option key={status} value={status}>{t(`eventStatus.${status}`)}</option>)}</select></label>
        <label className="text-sm font-medium">{t("setup.tables")}<input type="number" min={1} className="input mt-1 w-full" value={form.table_count} onChange={(e) => setForm({ ...form, table_count: Number(e.target.value) })} /></label>
        <ModuleToggles
          value={form.active_modules}
          seasonFlags={eventId ? modules.data?.season_flags : seasons.data?.find((item) => item.id === form.season_id)}
          onChange={(active_modules) => setForm({ ...form, active_modules })}
        />
        <fieldset className="md:col-span-2"><legend className="mb-2 font-medium">{t("setup.public")}</legend><div className="flex flex-wrap gap-4">{PUBLIC_FLAGS.map((key) => <label key={key} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.checked })} />{t(`setup.publicFlag.${key}`)}</label>)}</div></fieldset>
        <div className="md:col-span-2"><button className="btn-primary" disabled={saveEvent.isPending}>{t("setup.save")}</button></div>
      </form>
      {message && <p role="status" className="my-4 rounded-lg bg-gray-100 p-3 dark:bg-gray-800">{message}</p>}
      {eventId && <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <PhaseManager eventId={eventId} />
        <RegistrationManager eventId={eventId} />
        <SchemaEditor eventId={eventId} schema={schema.data} onMessage={setMessage} />
        {event?.season_id && <SeasonRulesEditor seasonId={event.season_id} onMessage={setMessage} />}
        {canAdminEvent && <EventBracketWeights eventId={eventId} />}
        {event?.season_id && <QualificationPanel eventId={eventId} seasonId={event.season_id} onMessage={setMessage} />}
        {canPublishAnnouncements && <section className="card p-5 lg:col-span-2"><h2 className="mb-3 text-lg font-semibold">{t("setup.announcements")}</h2><div className="mb-4 space-y-2">{announcements.data?.map((item) => <article key={item.id} className="rounded border p-3"><h3 className="font-semibold">{item.title}</h3><p className="text-sm text-gray-600 dark:text-gray-300">{item.body}</p></article>)}</div><form className="grid gap-2 md:grid-cols-[1fr_2fr_auto]" onSubmit={(e) => { e.preventDefault(); publishAnnouncement.mutate(); }}><input required className="input" placeholder={t("setup.announcementTitle")} value={announcement.title} onChange={(e) => setAnnouncement({ ...announcement, title: e.target.value })} /><textarea required className="input" placeholder={t("setup.announcementBody")} value={announcement.body} onChange={(e) => setAnnouncement({ ...announcement, body: e.target.value })} /><button className="btn-primary" disabled={publishAnnouncement.isPending}>{t("setup.publish")}</button></form></section>}
      </div>}
    </div>
  );
}

/**
 * Per-event module switches. A module the season has switched off (Saison-
 * Einstellungen) can be selected but stays inactive until the season allows it.
 */
function ModuleToggles({ value, seasonFlags, onChange }: { value: string[]; seasonFlags?: Record<string, unknown>; onChange: (modules: string[]) => void }) {
  const { t } = useTranslation("events");
  return (
    <fieldset className="md:col-span-2">
      <legend className="mb-2 font-medium">{t("setup.modules")}</legend>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {MODULE_ORDER.map((key) => {
          const { seasonFlag } = MODULE_LABELS[key];
          const blocked = !!seasonFlag && !!seasonFlags && !seasonFlags[seasonFlag];
          const checked = value.includes(key);
          return (
            <label key={key} className="flex items-start gap-2 rounded-lg border p-2 text-sm dark:border-gray-700">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={checked}
                onChange={(e) => onChange(e.target.checked ? MODULE_ORDER.filter((item) => item === key || value.includes(item)) : value.filter((item) => item !== key))}
              />
              <span>
                <span className="font-medium">{localized(MODULE_LABELS[key])}</span>
                {blocked && <span className="block text-xs text-amber-700 dark:text-amber-400">{t("setup.moduleBlocked")}{checked ? t("setup.moduleStaysInactive") : ""}</span>}
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

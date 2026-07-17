import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { Save, Trophy } from "lucide-react";
import { api } from "@/lib/api";
import { useOnlineStatus } from "@/hooks/useOnlineStatus";
import { useAuthStore } from "@/store/authStore";
import type { EventRegistration, RankingEntry, ScheduledMatch, ScoringField, ScoringSchema } from "@/api/types";

export default function EventScoringPage() {
  const { t } = useTranslation("events");
  const { eventId = "" } = useParams();
  const online = useOnlineStatus();
  const canWrite = useAuthStore((state) => state.hasPermission("scoring:write"));
  const queryClient = useQueryClient();
  const [teamId, setTeamId] = useState("");
  const [scheduledMatchId, setScheduledMatchId] = useState("");
  const [values, setValues] = useState<Record<string, number | boolean>>({});
  const [message, setMessage] = useState("");
  const registrations = useQuery<EventRegistration[]>({ queryKey: ["event-registrations", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/registrations`)).data });
  const schedule = useQuery<ScheduledMatch[]>({ queryKey: ["event-schedule", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/schedule`)).data });
  const schema = useQuery<ScoringSchema>({ queryKey: ["event-schema", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/scoring-schema`)).data, retry: false });
  const ranking = useQuery<RankingEntry[]>({ queryKey: ["event-ranking", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/ranking`)).data, refetchInterval: 10_000 });
  const total = useMemo(() => schema.data?.fields.reduce((sum, field) => sum + (Number(values[field.key] ?? 0) * field.multiplier), 0) ?? 0, [schema.data, values]);
  const save = useMutation({
    mutationFn: async () => api.post(`/v1/events/${eventId}/matches`, { team_id: teamId, scheduled_match_id: scheduledMatchId || null, raw_scores: values, idempotency_key: crypto.randomUUID() }),
    onSuccess: () => { setMessage(t("scoreSaved")); setValues({}); queryClient.invalidateQueries({ queryKey: ["event-ranking", eventId] }); },
    onError: (error: { response?: { data?: { detail?: string } } }) => setMessage(error.response?.data?.detail ?? t("saveFailed")),
  });
  const sections = useMemo(() => {
    const grouped = new Map<string, ScoringField[]>();
    for (const field of schema.data?.fields ?? []) { const section = field.section || t("scoring"); grouped.set(section, [...(grouped.get(section) ?? []), field]); }
    return grouped;
  }, [schema.data?.fields, t]);

  if (schema.isError) return <div className="p-6"><div className="card p-8 text-center">{t("noSchema")}</div></div>;
  return (
    <div className="mx-auto max-w-3xl p-4 md:p-6">
      <h1 className="mb-6 flex items-center gap-2 text-2xl font-bold"><Trophy className="text-yellow-500" />{t("mobileScoring")}</h1>
      {!online && <p role="alert" className="mb-4 rounded-lg bg-amber-100 p-3 text-amber-900">{t("offlineReadOnly")}</p>}
      {!canWrite && <p className="mb-4 rounded-lg bg-gray-100 p-3 dark:bg-gray-800">{t("readOnlyPermission")}</p>}
      <form className="space-y-5" onSubmit={(event) => { event.preventDefault(); setMessage(""); save.mutate(); }}>
        <div className="card grid gap-4 p-4 md:grid-cols-2">
          <label className="text-sm font-medium">{t("team")}<select required disabled={!canWrite || !online} className="input mt-1 w-full" value={teamId} onChange={(event) => setTeamId(event.target.value)}><option value="">{t("chooseTeam")}</option>{registrations.data?.map((item) => <option key={item.id} value={item.team_id}>{item.seed_number ? `#${item.seed_number} · ` : ""}{item.team_name}{item.team_number ? ` (${item.team_number})` : ""}</option>)}</select></label>
          <label className="text-sm font-medium">{t("scheduledMatch")}<select disabled={!canWrite || !online} className="input mt-1 w-full" value={scheduledMatchId} onChange={(event) => setScheduledMatchId(event.target.value)}><option value="">{t("withoutMatch")}</option>{schedule.data?.map((item) => <option key={item.id} value={item.id}>{item.code} · {t("table", { number: item.table_number ?? "–" })}</option>)}</select></label>
        </div>
        {[...sections].map(([section, fields]) => <fieldset disabled={!canWrite || !online} key={section} className="card p-4"><legend className="px-2 font-semibold">{section}</legend><div className="grid gap-4 sm:grid-cols-2">{fields.map((field) => <label key={field.key} className="text-sm font-medium">{field.label} <span className="text-xs text-gray-500">× {field.multiplier}</span>{field.type === "boolean" ? <input className="ml-3 h-5 w-5 align-middle" type="checkbox" checked={Boolean(values[field.key])} onChange={(event) => setValues((current) => ({ ...current, [field.key]: event.target.checked }))} /> : <input className="input mt-1 w-full text-lg" type="number" inputMode="decimal" required={field.required} min={field.min_value ?? undefined} max={field.max_value ?? undefined} value={String(values[field.key] ?? "")} onChange={(event) => setValues((current) => ({ ...current, [field.key]: Number(event.target.value) }))} />}</label>)}</div></fieldset>)}
        <div className="sticky bottom-0 card flex items-center justify-between gap-4 border-primary-200 p-4"><div><p className="text-sm text-gray-500">{t("calculatedTotal")}</p><p className="text-3xl font-bold">{total.toFixed(2)}</p></div><button className="btn-primary flex min-h-12 items-center gap-2" disabled={!canWrite || !online || save.isPending || !teamId}><Save />{t("saveOfficial")}</button></div>
        <p className="text-sm text-gray-500">{t("officialHint")}</p>{message && <p role="status" className="rounded-lg bg-gray-100 p-3 text-sm dark:bg-gray-800">{message}</p>}
      </form>
      <section className="mt-8"><h2 className="mb-3 text-xl font-semibold">{t("currentRanking")}</h2><div className="card overflow-x-auto"><table className="w-full text-sm"><thead className="bg-gray-100 dark:bg-gray-800"><tr><th className="p-3 text-left">#</th><th className="p-3 text-left">{t("team")}</th><th className="p-3 text-right">Seed</th><th className="p-3 text-right">Best</th></tr></thead><tbody>{ranking.data?.map((item) => <tr key={item.team_id} className="border-t dark:border-gray-800"><td className="p-3 font-bold">{item.rank}</td><td className="p-3 font-mono text-xs">{item.team_name ?? item.team_id}</td><td className="p-3 text-right">{item.seed_score.toFixed(2)}</td><td className="p-3 text-right">{item.best_score.toFixed(2)}</td></tr>)}</tbody></table></div></section>
    </div>
  );
}

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { Save, Trophy } from "lucide-react";
import { api } from "@/lib/api";
import { useEvent } from "@/hooks/useEvents";
import { useOnlineStatus } from "@/hooks/useOnlineStatus";
import { useAuthStore } from "@/store/authStore";
import type { EventRegistration, RankingEntry, ScheduledMatch, ScoringSchema } from "@/api/types";
import { computeSheet, normalize, type RawScores } from "@/modules/scoring/sheet/calculator";
import SheetForm from "@/modules/scoring/sheet/SheetForm";
import { LOSE_ROUND_REASONS, type HeadToHeadOutcome, type LoseRoundReason, type RuleSet } from "@/modules/scoring/extras/types";

export default function EventScoringPage() {
  const { t } = useTranslation("events");
  const { eventId = "" } = useParams();
  const online = useOnlineStatus();
  const canWrite = useAuthStore((state) => state.hasPermission("scoring:write"));
  const queryClient = useQueryClient();
  const { data: event } = useEvent(eventId);
  const [teamId, setTeamId] = useState("");
  const [scheduledMatchId, setScheduledMatchId] = useState("");
  const [values, setValues] = useState<RawScores>({});
  const [roundLost, setRoundLost] = useState(false);
  const [roundLostReason, setRoundLostReason] = useState<LoseRoundReason>("never_left_start_box");
  const [endContact, setEndContact] = useState(false);
  const [tiebreak, setTiebreak] = useState<Record<string, number | boolean>>({});
  const [message, setMessage] = useState("");
  const registrations = useQuery<EventRegistration[]>({ queryKey: ["event-registrations", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/registrations`)).data });
  const schedule = useQuery<ScheduledMatch[]>({ queryKey: ["event-schedule", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/schedule`)).data });
  const schema = useQuery<ScoringSchema>({ queryKey: ["event-schema", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/scoring-schema`)).data, retry: false });
  const ranking = useQuery<RankingEntry[]>({ queryKey: ["event-ranking", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/ranking`)).data, refetchInterval: 10_000 });
  const rules = useQuery<RuleSet>({ queryKey: ["scoring-rules", event?.season_id], queryFn: async () => (await api.get(`/scoring/seasons/${event?.season_id}/rules`)).data, enabled: !!event?.season_id });
  const outcome = useQuery<HeadToHeadOutcome>({ queryKey: ["h2h-outcome", scheduledMatchId], queryFn: async () => (await api.get(`/scoring/scheduled-matches/${scheduledMatchId}/outcome`)).data, enabled: !!scheduledMatchId });

  const definition = useMemo(() => normalize(schema.data?.fields, schema.data?.definition), [schema.data]);
  const sheet = useMemo(() => computeSheet(values, definition), [values, definition]);
  const total = roundLost ? 0 : sheet.total;
  const entryCriteria = (rules.data?.tiebreakers ?? []).filter((criterion) => criterion.source === "entry");
  const selectedMatch = schedule.data?.find((item) => item.id === scheduledMatchId);
  const headToHead = (selectedMatch?.participants.filter((p) => p.team_id).length ?? 0) > 1;
  const teamName = (id: string | null) => registrations.data?.find((item) => item.team_id === id)?.team_name ?? id ?? "";

  const reset = () => { setValues({}); setRoundLost(false); setEndContact(false); setTiebreak({}); };
  const save = useMutation({
    mutationFn: async () => api.post(`/v1/events/${eventId}/matches`, {
      team_id: teamId,
      scheduled_match_id: scheduledMatchId || null,
      raw_scores: values,
      round_lost: roundLost,
      round_lost_reason: roundLost ? roundLostReason : null,
      end_contact: endContact,
      tiebreak_values: tiebreak,
      idempotency_key: crypto.randomUUID(),
    }),
    onSuccess: () => {
      setMessage(t("scoreSaved"));
      reset();
      queryClient.invalidateQueries({ queryKey: ["event-ranking", eventId] });
      queryClient.invalidateQueries({ queryKey: ["h2h-outcome", scheduledMatchId] });
    },
    onError: (error: { response?: { data?: { detail?: string } } }) => setMessage(typeof error.response?.data?.detail === "string" ? error.response.data.detail : t("saveFailed")),
  });

  if (schema.isError) return <div className="p-6"><div className="card p-8 text-center">{t("noSchema")}</div></div>;
  const disabled = !canWrite || !online;
  return (
    <div className="mx-auto max-w-3xl p-4 md:p-6">
      <h1 className="mb-6 flex items-center gap-2 text-2xl font-bold"><Trophy className="text-yellow-500" />{t("mobileScoring")}</h1>
      {!online && <p role="alert" className="mb-4 rounded-lg bg-amber-100 p-3 text-amber-900">{t("offlineReadOnly")}</p>}
      {!canWrite && <p className="mb-4 rounded-lg bg-gray-100 p-3 dark:bg-gray-800">{t("readOnlyPermission")}</p>}
      <form className="space-y-5" onSubmit={(e) => { e.preventDefault(); setMessage(""); save.mutate(); }}>
        <div className="card grid gap-4 p-4 md:grid-cols-2">
          <label className="text-sm font-medium">{t("team")}<select required disabled={disabled} className="input mt-1 w-full" value={teamId} onChange={(e) => setTeamId(e.target.value)}><option value="">{t("chooseTeam")}</option>{registrations.data?.map((item) => <option key={item.id} value={item.team_id}>{item.seed_number ? `#${item.seed_number} · ` : ""}{item.team_name}{item.team_number ? ` (${item.team_number})` : ""}</option>)}</select></label>
          <label className="text-sm font-medium">{t("scheduledMatch")}<select disabled={disabled} className="input mt-1 w-full" value={scheduledMatchId} onChange={(e) => setScheduledMatchId(e.target.value)}><option value="">{t("withoutMatch")}</option>{schedule.data?.map((item) => <option key={item.id} value={item.id}>{item.code} · {t("table", { number: item.table_number ?? "–" })}</option>)}</select></label>
        </div>
        {definition && <SheetForm definition={definition} values={values} disabled={disabled} onChange={(key, value) => setValues((current) => ({ ...current, [key]: value }))} />}

        <fieldset disabled={disabled} className="card space-y-3 p-4">
          <legend className="px-2 font-semibold">{t("specialRules")}</legend>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={roundLost} onChange={(e) => setRoundLost(e.target.checked)} />{t("roundLost")}</label>
            {roundLost && <label className="text-sm">{t("roundLostReason")} <select className="input ml-1 inline-block w-auto" value={roundLostReason} onChange={(e) => setRoundLostReason(e.target.value as LoseRoundReason)}>{LOSE_ROUND_REASONS.map((reason) => <option key={reason} value={reason}>{t(`reason_${reason}`)}</option>)}</select></label>}
          </div>
          {headToHead && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={endContact} onChange={(e) => setEndContact(e.target.checked)} />{t("endContact", { percent: rules.data?.end_contact_bonus_percent ?? 25 })}</label>}
          {headToHead && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(tiebreak.replayed)} onChange={(e) => setTiebreak((current) => ({ ...current, replayed: e.target.checked }))} />{t("replayed")}</label>}
          {entryCriteria.length > 0 && (
            <div>
              <p className="text-sm font-medium">{t("tiebreakers")}</p>
              <p className="mb-2 text-xs text-gray-500">{t("tiebreakersHint")}</p>
              <div className="grid gap-3 sm:grid-cols-2">
                {entryCriteria.map((criterion) => <label key={criterion.key} className="text-sm">{criterion.label}{criterion.direction === "min" ? " ↓" : ""}<input className="input mt-1 w-full" type="number" step="any" value={typeof tiebreak[criterion.key] === "number" ? String(tiebreak[criterion.key]) : ""} onChange={(e) => setTiebreak((current) => ({ ...current, [criterion.key]: Number(e.target.value) }))} /></label>)}
              </div>
            </div>
          )}
        </fieldset>

        {scheduledMatchId && outcome.data && <OutcomeCard outcome={outcome.data} teamName={teamName} />}

        <div className="sticky bottom-0 card flex items-center justify-between gap-4 border-primary-200 p-4"><div><p className="text-sm text-gray-500">{t("calculatedTotal")}</p><p className="text-3xl font-bold">{total.toFixed(2)}</p></div><button className="btn-primary flex min-h-12 items-center gap-2" disabled={disabled || save.isPending || !teamId || sheet.errors.length > 0}><Save />{t("saveOfficial")}</button></div>
        <p className="text-sm text-gray-500">{t("officialHint")}</p>{message && <p role="status" className="rounded-lg bg-gray-100 p-3 text-sm dark:bg-gray-800">{message}</p>}
      </form>
      <section className="mt-8"><h2 className="mb-3 text-xl font-semibold">{t("currentRanking")}</h2><div className="card overflow-x-auto"><table className="w-full text-sm"><thead className="bg-gray-100 dark:bg-gray-800"><tr><th className="p-3 text-left">#</th><th className="p-3 text-left">{t("team")}</th><th className="p-3 text-right">Seed</th><th className="p-3 text-right">Best</th><th className="p-3 text-left">{t("tiebreaker")}</th></tr></thead><tbody>{ranking.data?.map((item) => <tr key={`${item.team_id}-${item.rank}`} className="border-t dark:border-gray-800"><td className="p-3 font-bold">{item.rank}</td><td className="p-3 font-mono text-xs">{item.team_name ?? teamName(item.team_id)}</td><td className="p-3 text-right">{item.seed_score.toFixed(2)}</td><td className="p-3 text-right">{item.best_score.toFixed(2)}</td><td className="p-3 text-xs text-gray-500">{item.tiebreaker ?? ""}</td></tr>)}</tbody></table></div></section>
    </div>
  );
}

function OutcomeCard({ outcome, teamName }: { outcome: HeadToHeadOutcome; teamName: (id: string | null) => string }) {
  const { t } = useTranslation("events");
  const headline = outcome.reason === "incomplete" ? t("outcomeIncomplete") : outcome.replay ? t("outcomeReplay") : t("outcomeWinner", { team: teamName(outcome.winner) });
  const reason = outcome.reason === "incomplete" ? "" : outcome.reason === "tiebreaker" ? t("reason_tiebreaker", { label: outcome.decided_by }) : t(`reason_${outcome.reason}`);
  return (
    <section className="card p-4" aria-live="polite">
      <h2 className="font-semibold">{t("outcome")}</h2>
      <p className="text-lg">{headline}{reason && <span className="ml-2 text-sm text-gray-500">({reason})</span>}</p>
      <ul className="mt-2 text-sm">
        {outcome.sides.map((side) => <li key={side.match_id}>{side.team_name ?? side.team_id}: <strong>{side.total_score}</strong>{side.bonus_score > 0 && <span className="text-gray-500"> – {t("bonus", { bonus: side.bonus_score })}</span>}{side.round_lost && <span className="ml-1 badge-yellow">{t("reason_round_lost")}</span>}{side.is_disqualified && <span className="ml-1 badge-red">DQ</span>}</li>)}
      </ul>
    </section>
  );
}

import { useMemo, useRef, useState, type TouchEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";
import { ChevronLeft, ChevronRight, Save, Trophy } from "lucide-react";
import { api, isQueuedResponse } from "@/lib/api";
import { formatScore } from "@/i18n/format";
import { useEvent } from "@/hooks/useEvents";
import { useOnlineStatus } from "@/hooks/useOnlineStatus";
import { useAuthStore } from "@/store/authStore";
import PendingScores from "@/components/PendingScores";
import ScoreConfirmDialog from "@/components/ScoreConfirmDialog";
import Freshness from "@/components/Freshness";
import { pollWhileOffline, useLiveUpdates } from "@/hooks/useLiveUpdates";
import { apiErrorMessage, errorStatus } from "@/lib/errors";
import { confirmAction } from "@/lib/confirm";
import { toast } from "@/lib/toast";
import { playsMatches, useSeasonCategories } from "@/lib/categories";
import { useQueuedNotice } from "@/hooks/useQueuedNotice";
import type { EventRegistration, RankingEntry, ScheduledMatch, ScoringSchema } from "@/api/types";
import { computeSheet, normalize, type RawScores } from "@/modules/scoring/sheet/calculator";
import SheetForm from "@/modules/scoring/sheet/SheetForm";
import PartsChallengePanel from "@/modules/scoring/extras/PartsChallengePanel";
import TimeoutCardsPanel from "@/modules/scoring/extras/TimeoutCardsPanel";
import { LOSE_ROUND_REASONS, type HeadToHeadOutcome, type LoseRoundReason, type RuleSet } from "@/modules/scoring/extras/types";

// Horizontal swipe distance (px) that switches to the neighbouring match.
const SWIPE_THRESHOLD = 60;

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
  // Result of the last save, shown in the sticky bar next to the button (in view on a phone).
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  // "Saved offline" stays only while the entry is still waiting in the queue.
  const queuedNotice = useQueuedNotice();
  const [confirming, setConfirming] = useState(false);
  const touchStart = useRef<{ x: number; y: number } | null>(null);
  const registrations = useQuery<EventRegistration[]>({ queryKey: ["event-registrations", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/registrations`)).data });
  const schedule = useQuery<ScheduledMatch[]>({ queryKey: ["event-schedule", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/schedule`)).data });
  const schema = useQuery<ScoringSchema>({ queryKey: ["event-schema", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/scoring-schema`)).data, retry: false });
  // Live updates invalidate the ranking; polling only while the stream is down.
  const { live } = useLiveUpdates(eventId);
  const ranking = useQuery<RankingEntry[]>({ queryKey: ["event-ranking", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/ranking`)).data, refetchInterval: pollWhileOffline(live) });
  const rules = useQuery<RuleSet>({ queryKey: ["scoring-rules", event?.season_id], queryFn: async () => (await api.get(`/scoring/seasons/${event?.season_id}/rules`)).data, enabled: !!event?.season_id });
  const registry = useSeasonCategories(event?.season_id);
  // Aerial and JBC teams play no matches: they are not offered (the API refuses them too).
  const matchTeams = (registrations.data ?? []).filter((item) => playsMatches(registry.kindOf(item.category)));
  const outcome = useQuery<HeadToHeadOutcome>({ queryKey: ["h2h-outcome", scheduledMatchId], queryFn: async () => (await api.get(`/scoring/scheduled-matches/${scheduledMatchId}/outcome`)).data, enabled: !!scheduledMatchId });

  const definition = useMemo(() => normalize(schema.data?.fields, schema.data?.definition), [schema.data]);
  const sheet = useMemo(() => computeSheet(values, definition), [values, definition]);
  const total = roundLost ? 0 : sheet.total;
  const entryCriteria = (rules.data?.tiebreakers ?? []).filter((criterion) => criterion.source === "entry");
  // Matches in the order they are played; cancelled ones cannot be scored.
  const matches = useMemo(() => [...(schedule.data ?? [])]
    .filter((item) => item.status !== "cancelled")
    .sort((a, b) => (a.scheduled_at ?? "").localeCompare(b.scheduled_at ?? "") || a.sequence_number - b.sequence_number), [schedule.data]);
  const matchIndex = matches.findIndex((item) => item.id === scheduledMatchId);
  const currentMatch = matchIndex >= 0 ? matches[matchIndex] : undefined;
  const selectedMatch = currentMatch;
  const headToHead = (selectedMatch?.participants.filter((p) => p.team_id).length ?? 0) > 1;
  // The team's recorded runs, to point out a second score for the same scheduled match.
  const teamMatches = useQuery<{ id: string; scheduled_match_id: string | null; is_practice: boolean; total_score: number }[]>({
    queryKey: ["event-team-matches", eventId, teamId],
    queryFn: async () => (await api.get(`/v1/events/${eventId}/matches`, { params: { team_id: teamId } })).data,
    enabled: !!teamId && !!scheduledMatchId && online,
  });
  const existingScore = scheduledMatchId ? teamMatches.data?.find((item) => item.scheduled_match_id === scheduledMatchId && !item.is_practice) : undefined;
  const teamName = (id: string | null) => registrations.data?.find((item) => item.team_id === id)?.team_name ?? id ?? "";

  const teamLabel = (id: string) => {
    const registration = registrations.data?.find((item) => item.team_id === id);
    return registration ? `${registration.team_name}${registration.team_number ? ` (${registration.team_number})` : ""}` : id;
  };

  const reset = () => { setValues({}); setRoundLost(false); setEndContact(false); setTiebreak({}); };
  // Anything entered for the current match that switching would throw away.
  const dirty = Object.keys(values).length > 0 || roundLost || endContact || Object.keys(tiebreak).length > 0;
  const selectMatch = async (id: string) => {
    if (id === scheduledMatchId) return;
    if (dirty && !(await confirmAction({ message: t("discardEntries"), confirmLabel: t("discardEntriesConfirm"), tone: "danger" }))) return;
    setScheduledMatchId(id);
    setMessage(null);
    const match = matches.find((item) => item.id === id);
    const participants = (match?.participants ?? []).map((item) => item.team_id).filter((item): item is string => !!item);
    if (participants.length && !participants.includes(teamId)) setTeamId(participants[0]);
    reset();
  };
  const step = (delta: number) => {
    if (!matches.length) return;
    const next = matchIndex < 0 ? (delta > 0 ? 0 : matches.length - 1) : matchIndex + delta;
    if (next >= 0 && next < matches.length) void selectMatch(matches[next].id);
  };
  const onTouchStart = (event: TouchEvent) => {
    const touch = event.touches[0];
    touchStart.current = { x: touch.clientX, y: touch.clientY };
  };
  const onTouchEnd = (event: TouchEvent) => {
    const start = touchStart.current;
    touchStart.current = null;
    if (!start || confirming) return;
    const touch = event.changedTouches[0];
    const dx = touch.clientX - start.x;
    const dy = touch.clientY - start.y;
    if (Math.abs(dx) > SWIPE_THRESHOLD && Math.abs(dx) > Math.abs(dy) * 1.5) step(dx < 0 ? 1 : -1);
  };
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
    }, { offlineLabel: [teamLabel(teamId), currentMatch?.code, t("pointsShort", { points: formatScore(total) })].filter(Boolean).join(" · ") }),
    onSuccess: ({ data }) => {
      setConfirming(false);
      if (isQueuedResponse(data)) {
        setMessage(null);
        queuedNotice.show(data.idempotency_key);
      } else {
        const text = t("scoreSavedFor", { team: teamLabel(teamId), points: formatScore(total) });
        setMessage({ tone: "success", text });
        toast.success(text);
      }
      reset();
      queryClient.invalidateQueries({ queryKey: ["event-ranking", eventId] });
      queryClient.invalidateQueries({ queryKey: ["h2h-outcome", scheduledMatchId] });
      queryClient.invalidateQueries({ queryKey: ["event-team-matches", eventId] });
    },
    onError: (error: unknown) => { setConfirming(false); setMessage({ tone: "error", text: apiErrorMessage(error, t("saveFailed")) }); },
  });

  if (schema.isLoading) return <div className="p-6 text-leise" role="status">{t("common:loadingEllipsis")}</div>;
  // 404 = no schema for this event (an empty state); anything else is an error.
  if (schema.isError && errorStatus(schema.error) === 404) return <div className="p-6"><div className="card p-8 text-center">{t("noSchema")}</div></div>;
  if (schema.isError) {
    return (
      <div className="p-6">
        <div role="alert" className="card space-y-4 p-8 text-center">
          <p>{apiErrorMessage(schema.error, t("schemaLoadFailed"))}</p>
          <button type="button" className="btn-secondary min-h-11" onClick={() => void schema.refetch()}>{t("common:retry")}</button>
        </div>
      </div>
    );
  }
  // Offline entries are queued on the device and synced later (lib/offlineQueue).
  const disabled = !canWrite;
  return (
    <div className="mx-auto max-w-3xl p-4 md:p-6">
      <header className="page-header">
        <div className="min-w-0">
          <h1 className="page-title flex items-center gap-2"><Trophy className="h-7 w-7 shrink-0 text-akzent" aria-hidden="true" />{t("mobileScoring")}</h1>
          <p className="page-subtitle">{t("mobileScoringSubtitle")}</p>
        </div>
      </header>
      {!online && <p role="alert" className="mb-4 rounded-lg bg-warning/10 p-3 text-warning">{t("offlineScoring")}</p>}
      {!canWrite && <p className="mb-4 rounded-lg bg-flaeche-2 p-3">{t("readOnlyPermission")}</p>}
      <div className="mb-5"><PendingScores filter={(entry) => entry.eventId === eventId} /></div>
      <form className="space-y-5" onSubmit={(e) => { e.preventDefault(); setMessage(null); setConfirming(true); }}>
        {matches.length > 0 && (
          // Swiping switches matches only on this bar, never while typing in the form.
          <nav aria-label={t("scheduledMatch")} className="card flex touch-pan-y items-center justify-between gap-2 p-2" onTouchStart={onTouchStart} onTouchEnd={onTouchEnd}>
            <button type="button" className="btn-secondary min-h-12 min-w-12 justify-center" onClick={() => step(-1)} disabled={matchIndex === 0} aria-label={t("previousMatch")}><ChevronLeft aria-hidden="true" /></button>
            <div className="min-w-0 text-center">
              <p className="truncate font-semibold">{currentMatch ? `${currentMatch.code} · ${t("table", { number: currentMatch.table_number ?? "–" })}` : t("withoutMatch")}</p>
              <p className="text-xs text-leise">{currentMatch ? t("matchPosition", { current: matchIndex + 1, total: matches.length }) : t("swipeHint")}</p>
            </div>
            <button type="button" className="btn-secondary min-h-12 min-w-12 justify-center" onClick={() => step(1)} disabled={matchIndex === matches.length - 1} aria-label={t("nextMatch")}><ChevronRight aria-hidden="true" /></button>
          </nav>
        )}
        <div className="card grid gap-4 p-4 md:grid-cols-2">
          <label className="text-sm font-medium">{t("team")}<select required disabled={disabled} className="input mt-1 w-full" value={teamId} onChange={(e) => setTeamId(e.target.value)}><option value="">{t("chooseTeam")}</option>{matchTeams.map((item) => <option key={item.id} value={item.team_id}>{item.seed_number ? `#${item.seed_number} · ` : ""}{item.team_name}{item.team_number ? ` (${item.team_number})` : ""}</option>)}</select></label>
          <label className="text-sm font-medium">{t("scheduledMatch")}<select disabled={disabled} className="input mt-1 w-full" value={scheduledMatchId} onChange={(e) => void selectMatch(e.target.value)}><option value="">{t("withoutMatch")}</option>{matches.map((item) => <option key={item.id} value={item.id}>{item.code} · {t("table", { number: item.table_number ?? "–" })}</option>)}</select></label>
        </div>
        {definition && <SheetForm definition={definition} values={values} disabled={disabled} onChange={(key, value) => setValues((current) => {
          const next = { ...current };
          if (value === null) delete next[key];
          else next[key] = value;
          return next;
        })} />}

        <fieldset disabled={disabled} className="card space-y-3 p-4">
          <legend className="px-2 font-semibold">{t("specialRules")}</legend>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex min-h-11 cursor-pointer items-center gap-3 pr-2 text-sm"><input type="checkbox" className="h-6 w-6 shrink-0" checked={roundLost} onChange={(e) => setRoundLost(e.target.checked)} />{t("roundLost")}</label>
            {roundLost && <label className="text-sm">{t("roundLostReason")} <select className="input ml-1 inline-block w-auto" value={roundLostReason} onChange={(e) => setRoundLostReason(e.target.value as LoseRoundReason)}>{LOSE_ROUND_REASONS.map((reason) => <option key={reason} value={reason}>{t(`reason_${reason}`)}</option>)}</select></label>}
          </div>
          {headToHead && <label className="flex min-h-11 cursor-pointer items-center gap-3 text-sm"><input type="checkbox" className="h-6 w-6 shrink-0" checked={endContact} onChange={(e) => setEndContact(e.target.checked)} />{t("endContact", { percent: rules.data?.end_contact_bonus_percent ?? 25 })}</label>}
          {headToHead && <label className="flex min-h-11 cursor-pointer items-center gap-3 text-sm"><input type="checkbox" className="h-6 w-6 shrink-0" checked={Boolean(tiebreak.replayed)} onChange={(e) => setTiebreak((current) => ({ ...current, replayed: e.target.checked }))} />{t("replayed")}</label>}
          {entryCriteria.length > 0 && (
            <div>
              <p className="text-sm font-medium">{t("tiebreakers")}</p>
              <p className="mb-2 text-xs text-leise">{t("tiebreakersHint")}</p>
              <div className="grid gap-3 sm:grid-cols-2">
                {entryCriteria.map((criterion) => <label key={criterion.key} className="text-sm">{criterion.label}{criterion.direction === "min" ? " ↓" : ""}<input className="input mt-1 w-full" type="number" step="any" value={typeof tiebreak[criterion.key] === "number" ? String(tiebreak[criterion.key]) : ""} onChange={(e) => setTiebreak((current) => ({ ...current, [criterion.key]: Number(e.target.value) }))} /></label>)}
              </div>
            </div>
          )}
        </fieldset>

        {scheduledMatchId && outcome.data?.sides && <OutcomeCard outcome={outcome.data} teamName={teamName} />}

        <div className="sticky bottom-0 card space-y-3 border-primary/30 p-4">
          {/* The save result sits in the sticky bar, so it is in view on a phone. */}
          {message && <p role={message.tone === "error" ? "alert" : "status"} className={message.tone === "error" ? "rounded-lg bg-danger/[0.07] p-2 text-sm text-danger" : "rounded-lg bg-success/10 p-2 text-sm text-success"}>{message.text}</p>}
          {queuedNotice.visible && <p role="status" className="rounded-lg bg-warning/10 p-2 text-sm text-warning">{t("scoreQueued")}</p>}
          <div className="flex items-center justify-between gap-4"><div><p className="text-sm text-leise">{t("calculatedTotal")}</p><p className="text-3xl font-bold">{formatScore(total)}</p></div><button className="btn-primary flex min-h-12 items-center gap-2" disabled={disabled || save.isPending || !teamId || sheet.errors.length > 0}><Save />{t("reviewScore")}</button></div>
        </div>
        <p className="text-sm text-leise">{t("officialHint")}</p>
      </form>
      <ScoreConfirmDialog
        open={confirming}
        title={t("saveOfficial")}
        context={[
          [t("team"), teamLabel(teamId)],
          [t("scheduledMatch"), currentMatch ? `${currentMatch.code} · ${t("table", { number: currentMatch.table_number ?? "–" })}` : t("withoutMatch")],
          ...(roundLost ? [[t("specialRules"), t("roundLost")] as [string, string]] : []),
        ]}
        fields={schema.data?.fields ?? []}
        values={values as Record<string, number | boolean | undefined>}
        total={total}
        offline={!online}
        pending={save.isPending}
        // A head-to-head match may be replayed (the latest score counts); a
        // seeding match already scored would count twice and is refused.
        warning={existingScore ? t(headToHead ? "replayMatchScore" : "duplicateMatchScore", { team: teamLabel(teamId), points: formatScore(existingScore.total_score) }) : undefined}
        blocked={!!existingScore && !headToHead}
        onConfirm={() => save.mutate()}
        onCancel={() => setConfirming(false)}
      />
      <div className="mt-8"><PartsChallengePanel eventId={eventId} matches={matches} registrations={matchTeams} /></div>
      <div className="mt-8"><TimeoutCardsPanel eventId={eventId} registrations={matchTeams} /></div>
      <section className="mt-8"><h2 className="mb-3 text-xl font-semibold">{t("currentRanking")}</h2><Freshness query={ranking} live={live} className="mb-3" /><div className="card table-scroll"><table className="w-full text-sm"><thead className="bg-flaeche-2"><tr><th className="p-3 text-left">#</th><th className="p-3 text-left">{t("team")}</th><th className="p-3 text-right">{t("seed")}</th><th className="p-3 text-right">{t("best")}</th><th className="p-3 text-left">{t("tiebreaker")}</th></tr></thead><tbody>{ranking.data?.map((item) => <tr key={`${item.team_id}-${item.rank}`} className="border-t"><td className="p-3 font-bold">{item.rank}</td><td className="p-3 font-mono text-xs">{item.team_name ?? teamName(item.team_id)}</td><td className="p-3 text-right">{formatScore(item.seed_score)}</td><td className="p-3 text-right">{formatScore(item.best_score)}</td><td className="p-3 text-xs text-leise">{item.tiebreaker ?? ""}</td></tr>)}</tbody></table></div></section>
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
      <p className="text-lg">{headline}{reason && <span className="ml-2 text-sm text-leise">({reason})</span>}</p>
      <ul className="mt-2 text-sm">
        {outcome.sides.map((side) => <li key={side.match_id}>{side.team_name ?? side.team_id}: <strong>{side.total_score}</strong>{side.bonus_score > 0 && <span className="text-leise"> – {t("bonus", { bonus: side.bonus_score })}</span>}{side.round_lost && <span className="ml-1 badge-yellow">{t("reason_round_lost")}</span>}{side.is_disqualified && <span className="ml-1 badge-red" title={t("disqualified")}>{t("dqShort")}</span>}</li>)}
      </ul>
    </section>
  );
}

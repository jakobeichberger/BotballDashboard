import { useId, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Trans, useTranslation } from "react-i18next";
import { ClipboardList, ArrowLeft, Check, Trash2, Save, Dumbbell, Trophy, Pencil, X, Flag, Minus, Plus } from "lucide-react";
import { api, isQueuedResponse } from "@/lib/api";
import { EventLink } from "@/components/EventLink";
import PendingScores from "@/components/PendingScores";
import ScoreConfirmDialog from "@/components/ScoreConfirmDialog";
import { useOnlineStatus } from "@/hooks/useOnlineStatus";
import { useAuthStore } from "@/store/authStore";
import { useScoringScope } from "@/hooks/useScoringScope";
import clsx from "clsx";
import { computeSheet, normalize } from "@/modules/scoring/sheet/calculator";
import { sheetMessages } from "@/modules/scoring/sheet/issues";
import { playsMatches, useSeasonCategories } from "@/lib/categories";
import { useQueuedNotice } from "@/hooks/useQueuedNotice";
import type { EventRegistration } from "@/api/types";
import ChecklistConfirmDialog from "@/modules/scoring/extras/ChecklistConfirmDialog";
import MatchPenaltyDialog, { PenaltyBadges, type PenaltyMatch } from "@/modules/scoring/extras/MatchPenaltyDialog";
import type { RuleSet } from "@/modules/scoring/extras/types";
import { formatNumber } from "@/i18n/format";
import { apiErrorMessage } from "@/lib/errors";
import { toast } from "@/lib/toast";
import { confirmAction } from "@/lib/confirm";

interface Field {
  key: string;
  label: string;
  multiplier: number;
  min_value?: number | null;
  max_value: number | null;
  type: "count" | "boolean";
}

type Mode = "contest" | "practice";

interface TeamOption {
  id: string;
  name: string;
}

/** The round as typed: digits only, so "1", backspace, "2" gives 2 (not 12). */
function parseRound(text: string): number | null {
  if (!/^\d+$/.test(text)) return null;
  const value = Number(text);
  return value >= 1 ? value : null;
}

export default function ScoreEntryPage() {
  const { t } = useTranslation("scoring");
  const qc = useQueryClient();
  const canEnter = useAuthStore((s) => s.hasPermission("scoring:write"));
  const canManageAll = useAuthStore((s) => s.hasPermission("scoring:admin")); // any team + confirm/delete

  const [mode, setMode] = useState<Mode>("contest");
  const isPractice = mode === "practice";
  const online = useOnlineStatus();
  const [confirming, setConfirming] = useState(false);
  // Confirmation of the last save, next to the save button (plus a toast).
  const [notice, setNotice] = useState("");
  // "Saved offline" only while the entry is still in the offline queue.
  const queuedNotice = useQueuedNotice();

  // Scores are entered for the event of the current route; without one the
  // backend falls back to the season's default event.
  const { eventId, seasonId: sid, season, isLoading: scopeLoading } = useScoringScope();
  const eventQuery = eventId ? `?event_id=${eventId}` : "";

  const registry = useSeasonCategories(sid);
  // Under an event: the teams registered for it whose category plays matches
  // (Aerial and JBC teams are not offered; the API refuses them as well).
  const { data: registrations } = useQuery<EventRegistration[]>({
    queryKey: ["event-registrations", eventId],
    queryFn: async () => (await api.get(`/v1/events/${eventId}/registrations`)).data,
    enabled: !!eventId,
  });
  const { data: allTeams } = useQuery<TeamOption[]>({
    queryKey: ["teams"],
    queryFn: async () => (await api.get("/teams")).data,
    enabled: !eventId,
  });
  const { data: myTeams } = useQuery<TeamOption[]>({
    queryKey: ["teams-mine"],
    queryFn: async () => (await api.get("/teams/mine")).data,
    enabled: canEnter && !canManageAll,
  });
  const schemaQuery = useQuery({
    queryKey: ["scoring-schema", sid, eventId],
    queryFn: async () => (await api.get(`/scoring/seasons/${sid}/schema${eventQuery}`)).data,
    enabled: !!sid,
  });
  const schema = schemaQuery.data;
  // Only the runs of the current mode (official or practice): the other half
  // of a long event list is never shown on this page.
  const { data: matches } = useQuery({
    queryKey: ["matches", sid, eventId, isPractice],
    queryFn: async () =>
      (await api.get(`/scoring/seasons/${sid}/matches${eventQuery}`, { params: { is_practice: isPractice } })).data,
    enabled: !!sid,
  });

  const eventTeams: TeamOption[] | undefined = registrations
    ?.filter((registration) => playsMatches(registry.kindOf(registration.category)))
    .map((registration) => ({ id: registration.team_id, name: registration.team_name }));
  const candidates = eventId ? eventTeams : allTeams;
  const entryTeams = canManageAll || eventId ? candidates?.filter((team) => canManageAll || myTeams?.some((own) => own.id === team.id)) : myTeams;
  const teamName = (tid: string) =>
    registrations?.find((registration) => registration.team_id === tid)?.team_name ??
    allTeams?.find((team) => team.id === tid)?.name ??
    myTeams?.find((team) => team.id === tid)?.name ??
    tid;

  const [teamId, setTeamId] = useState("");
  const [roundText, setRoundText] = useState("1");
  const round = parseRound(roundText);
  const [scores, setScores] = useState<Record<string, number>>({});
  const setScore = (key: string, value: number | null) =>
    setScores((current) => {
      const next = { ...current };
      if (value === null) delete next[key];
      else next[key] = value;
      return next;
    });

  const { data: rules } = useQuery<RuleSet>({
    queryKey: ["scoring-rules", sid],
    queryFn: async () => (await api.get(`/scoring/seasons/${sid}/rules`)).data,
    enabled: !!sid,
  });

  const fields: Field[] = schema?.fields ?? [];
  // Same calculation as the backend (area multipliers, either-or, sides A/B).
  const sheet = computeSheet(scores, normalize(schema?.fields, schema?.definition));
  const preview = sheet.total;
  const problems = sheetMessages(sheet, t);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["matches", sid, eventId] });
  const onError = (e: unknown) => toast.apiError(e, t("common:actionFailed"));
  const formId = useId();

  const [editingId, setEditingId] = useState<string | null>(null);
  const rawFromScores = () => Object.fromEntries(fields.map((f) => [f.key, Number(scores[f.key] || 0)]));
  const resetForm = () => { setScores({}); setEditingId(null); };

  const saveM = useMutation({
    // Resolves to what happened: updated, queued offline (with its key) or saved.
    mutationFn: async (): Promise<{ kind: "updated" } | { kind: "queued"; key: string } | { kind: "saved"; text: string }> => {
      if (editingId) {
        await api.patch(`/scoring/matches/${editingId}`, { raw_scores: rawFromScores() });
        return { kind: "updated" };
      }
      const text = t(isPractice ? "entry.savedPractice" : "entry.saved", { team: teamName(teamId), round, points: preview });
      const { data } = await api.post<unknown>(
        `/scoring/seasons/${sid}/matches`,
        {
          ...(eventId ? { event_id: eventId } : {}),
          team_id: teamId,
          round_number: round,
          is_practice: isPractice,
          raw_scores: rawFromScores(),
          idempotency_key: crypto.randomUUID(),
        },
        { offlineLabel: t(isPractice ? "entry.offlineLabelPractice" : "entry.offlineLabel", { team: teamName(teamId), round, points: preview }) },
      );
      return isQueuedResponse(data) ? { kind: "queued", key: data.idempotency_key } : { kind: "saved", text };
    },
    onSuccess: (result) => {
      setConfirming(false);
      if (result.kind === "queued") {
        setNotice("");
        queuedNotice.show(result.key);
      } else {
        const text = result.kind === "saved" ? result.text : t("entry.updated");
        setNotice(text);
        toast.success(text);
      }
      // A new run moves on to the team's next round.
      if (result.kind !== "updated" && round !== null) setRoundText(String(round + 1));
      resetForm();
      invalidate();
    },
    onError: (e) => { setConfirming(false); onError(e); },
  });
  // Official (non-practice) entries get a summary to confirm before they are sent.
  const submit = () => {
    setNotice("");
    if (!editingId && !isPractice) setConfirming(true);
    else saveM.mutate();
  };

  const startEdit = (m: any) => {
    setNotice("");
    setEditingId(m.id);
    setTeamId(m.team_id);
    setRoundText(String(m.round_number));
    setScores({ ...m.raw_scores });
  };
  const checklist = rules?.referee_checklist ?? [];
  const [checklistMatchId, setChecklistMatchId] = useState<string | null>(null);
  const [confirmError, setConfirmError] = useState("");
  const confirmM = useMutation({
    mutationFn: ({ mid, items }: { mid: string; items?: Record<string, boolean> }) =>
      api.put(`/scoring/matches/${mid}/confirm`, items ? { checklist: items } : undefined),
    onSuccess: () => { setChecklistMatchId(null); setConfirmError(""); invalidate(); },
    onError: (e: any) => {
      if (checklistMatchId) setConfirmError(apiErrorMessage(e, t("entry.confirmFailed")));
      else onError(e);
    },
  });
  // With a referee checklist configured the juror ticks it before confirming.
  const startConfirm = (mid: string) => (checklist.length ? setChecklistMatchId(mid) : confirmM.mutate({ mid }));
  // Cards and DQ are referee decisions (scoring:admin), see MatchPenaltyDialog.
  const [penaltyMatch, setPenaltyMatch] = useState<(PenaltyMatch & { team_id: string; round_number: number }) | null>(null);
  const deleteM = useMutation({
    mutationFn: (mid: string) => api.delete(`/scoring/matches/${mid}`),
    onSuccess: invalidate, onError,
  });
  // Deleting a score cannot be undone: always ask, naming team and round.
  const askDelete = async (m: any) => {
    const confirmed = await confirmAction({
      message: t("entry.confirmDelete", { team: teamName(m.team_id), round: m.round_number, points: m.total_score }),
      tone: "danger",
    });
    if (confirmed) deleteM.mutate(m.id);
  };

  const visibleMatches = (matches ?? [])
    .filter((m: any) => !!m.is_practice === isPractice)
    .filter((m: any) => canManageAll || myTeams?.some((t: any) => t.id === m.team_id))
    .sort((a: any, b: any) => a.round_number - b.round_number);

  // The team's next free round (of the current mode), preselected with the team.
  const nextRound = (tid: string) =>
    visibleMatches.filter((m: any) => m.team_id === tid).reduce((highest: number, m: any) => Math.max(highest, m.round_number), 0) + 1;
  const chooseTeam = (tid: string) => {
    setTeamId(tid);
    setNotice("");
    if (tid) setRoundText(String(nextRound(tid)));
  };
  const stepRound = (delta: number) => setRoundText(String(Math.max(1, (round ?? 1) + delta)));
  // A second official score for a recorded round would count as an extra run:
  // the API refuses it (409 duplicate_round), the form says so up front.
  const duplicate: any = !editingId && !isPractice && teamId && round !== null
    ? visibleMatches.find((m: any) => m.team_id === teamId && m.round_number === round)
    : undefined;
  const duplicateText = duplicate ? t("entry.duplicateRound", { team: teamName(teamId), round, points: duplicate.total_score }) : "";
  const correctDuplicate = () => { setConfirming(false); startEdit(duplicate); };

  // Practice progress summary (per selected team, or across visible practice runs)
  const practiceScores = visibleMatches.map((m: any) => m.total_score);
  const practiceBest = practiceScores.length ? Math.max(...practiceScores) : null;
  const practiceAvg = practiceScores.length
    ? formatNumber(practiceScores.reduce((a: number, b: number) => a + b, 0) / practiceScores.length, {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
      })
    : null;

  if (!canEnter) {
    return (
      <div className="p-6">
        <div className="card p-8 text-center text-leise">{t("entry.noPermission")}</div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <EventLink to="/scoreboard" className="btn-secondary text-sm">
        <ArrowLeft className="w-4 h-4" /> {t("backToScoreboard")}
      </EventLink>

      <div className="page-header mb-0!">
        <div className="min-w-0">
          <h1 className="page-title flex items-center gap-2">
            <ClipboardList className="h-7 w-7 shrink-0 text-akzent" aria-hidden="true" /> {t("entry.title")}
          </h1>
          <p className="page-subtitle">{t("entry.subtitle")}</p>
        </div>
        {/* Mode toggle */}
        <div className="inline-flex rounded-lg border border-rand overflow-hidden">
          {([
            ["contest", t("entry.contest"), Trophy],
            ["practice", t("entry.practice"), Dumbbell],
          ] as [Mode, string, any][]).map(([m, label, Icon]) => (
            <button
              key={m}
              type="button"
              aria-pressed={mode === m}
              onClick={() => setMode(m)}
              className={clsx(
                "flex min-h-11 items-center gap-2 px-4 py-2 text-sm font-medium transition-colors",
                mode === m
                  ? "bg-primary text-white"
                  : "bg-flaeche text-leise hover:bg-flaeche-2"
              )}
            >
              <Icon className="w-4 h-4" /> {label}
            </button>
          ))}
        </div>
      </div>

      {isPractice && (
        <p className="text-sm text-leise">
          <Trans t={t} i18nKey="entry.practiceHint" components={{ strong: <strong /> }} />
        </p>
      )}

      {!online && (
        <p role="alert" className="rounded-lg bg-warning/10 p-3 text-sm text-warning">
          {t("entry.offline")}
        </p>
      )}
      {sid && <PendingScores filter={(entry) => entry.url === `/scoring/seasons/${sid}/matches` && (entry.eventId ?? undefined) === eventId && !!entry.body.is_practice === isPractice} />}
      {queuedNotice.visible && <p role="status" className="rounded-lg bg-warning/10 p-3 text-sm text-warning">{t("events:scoreQueued")}</p>}

      {!season && scopeLoading && <p role="status" className="text-sm text-leise">{t("common:loadingEllipsis")}</p>}
      {!season && !scopeLoading && <p className="text-danger text-sm">{t("entry.noSeason")}</p>}
      {season && schemaQuery.isLoading && <p role="status" className="text-sm text-leise">{t("common:loadingEllipsis")}</p>}
      {season && schemaQuery.isError && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg bg-danger/[0.07] p-3 text-sm text-danger">
          {apiErrorMessage(schemaQuery.error, t("entry.schemaLoadFailed"))}
          <button type="button" className="btn-secondary min-h-11" onClick={() => void schemaQuery.refetch()}>{t("common:retry")}</button>
        </div>
      )}
      {season && schemaQuery.isSuccess && !schema?.fields?.length && (
        <p className="text-warning text-sm">{t("entry.noSchema")}</p>
      )}

      {/* Entry form */}
      {season && schema?.fields?.length > 0 && (
        <div className="card p-6 space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <label className="label" htmlFor={`${formId}-team`}>{t("scouting.team")}</label>
              <select id={`${formId}-team`} className="input" value={teamId} disabled={!!editingId} onChange={(e) => chooseTeam(e.target.value)}>
                <option value="">{t("entry.chooseTeam")}</option>
                {entryTeams?.map((team) => (<option key={team.id} value={team.id}>{team.name}</option>))}
              </select>
              {eventId && entryTeams?.length === 0 && <p className="mt-1 text-xs text-leise">{t("entry.noEventTeams")}</p>}
            </div>
            <div>
              <label className="label" htmlFor={`${formId}-round`}>{isPractice ? t("entry.runNumber") : t("scouting.roundLabel")}</label>
              {/* Text + inputMode: the value can be cleared and retyped on a phone; the steppers are thumb-sized. */}
              <div className="flex items-center gap-2">
                <button type="button" className="btn-secondary h-11 w-11 shrink-0 justify-center p-0" aria-label={t("entry.decreaseRound")} disabled={!!editingId || (round ?? 1) <= 1} onClick={() => stepRound(-1)}><Minus className="h-5 w-5" aria-hidden="true" /></button>
                <input id={`${formId}-round`} type="text" inputMode="numeric" pattern="[0-9]*" autoComplete="off" className="input text-center text-lg" value={roundText} disabled={!!editingId}
                       aria-invalid={round === null} onChange={(e) => setRoundText(e.target.value.replace(/\D/g, ""))} />
                <button type="button" className="btn-secondary h-11 w-11 shrink-0 justify-center p-0" aria-label={t("entry.increaseRound")} disabled={!!editingId} onClick={() => stepRound(1)}><Plus className="h-5 w-5" aria-hidden="true" /></button>
              </div>
              {round === null && <p role="alert" className="mt-1 text-xs text-danger">{t("entry.roundInvalid")}</p>}
            </div>
            <div className="flex items-end">
              <div className="text-sm">
                <div className="text-leise">{t("entry.preview")}</div>
                <div className="text-2xl font-bold text-akzent">{preview}</div>
                {problems.length > 0 && <ul role="alert" className="text-xs text-danger">{problems.map((problem) => <li key={problem}>{problem}</li>)}</ul>}
              </div>
            </div>
          </div>
          {duplicate && (
            <div role="alert" className="rounded-lg bg-danger/[0.07] p-3 text-sm text-danger">
              <p>{duplicateText}</p>
              {canManageAll && <button type="button" className="btn-secondary mt-2 min-h-11" onClick={correctDuplicate}><Pencil className="h-4 w-4" aria-hidden="true" /> {t("entry.correctExisting")}</button>}
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 border-t pt-4">
            {fields.map((f) => (
              <div key={f.key}>
                {f.type === "boolean" ? (
                  <p className="label" id={`${formId}-${f.key}-label`}>{f.label} <span className="text-leise">(×{f.multiplier})</span></p>
                ) : (
                  <label className="label" htmlFor={`${formId}-${f.key}`}>{f.label} <span className="text-leise">(×{f.multiplier})</span></label>
                )}
                {f.type === "boolean" ? (
                  <label className="inline-flex min-h-11 cursor-pointer items-center gap-3 pr-2 text-sm">
                    <input type="checkbox" className="h-6 w-6 shrink-0" aria-describedby={`${formId}-${f.key}-label`} checked={!!scores[f.key]}
                           onChange={(e) => setScore(f.key, e.target.checked ? 1 : 0)} />
                    {t("entry.achieved")}
                  </label>
                ) : (
                  // Clearable (empty = not entered), with thumb-sized steppers for counting.
                  <div className="flex items-center gap-2">
                    <button type="button" className="btn-secondary h-11 w-11 shrink-0 justify-center p-0" aria-label={t("sheet.decrease", { label: f.label })}
                            disabled={(scores[f.key] ?? 0) <= (f.min_value ?? 0)} onClick={() => setScore(f.key, Math.max(f.min_value ?? 0, (scores[f.key] ?? 0) - 1))}><Minus className="h-5 w-5" aria-hidden="true" /></button>
                    <input id={`${formId}-${f.key}`} type="number" inputMode="numeric" min={f.min_value ?? 0} max={f.max_value ?? undefined} className="input text-lg"
                           value={scores[f.key] ?? ""}
                           onChange={(e) => setScore(f.key, e.target.value === "" ? null : Number(e.target.value))} />
                    <button type="button" className="btn-secondary h-11 w-11 shrink-0 justify-center p-0" aria-label={t("sheet.increase", { label: f.label })}
                            disabled={f.max_value !== null && (scores[f.key] ?? 0) >= f.max_value} onClick={() => setScore(f.key, (scores[f.key] ?? 0) + 1)}><Plus className="h-5 w-5" aria-hidden="true" /></button>
                  </div>
                )}
              </div>
            ))}
          </div>

          {notice && <p role="status" className="rounded-lg bg-success/10 p-3 text-sm text-success">{notice}</p>}
          <div className="flex justify-end gap-2">
            {editingId && (
              <button type="button" className="btn-secondary" onClick={resetForm}><X className="w-4 h-4" /> {t("common:cancel")}</button>
            )}
            <button type="button" className="btn-primary disabled:opacity-40" disabled={!teamId || saveM.isPending || round === null || sheet.errors.length > 0 || !!duplicate}
                    onClick={submit}>
              <Save className="w-4 h-4" /> {editingId ? t("entry.saveChanges") : (isPractice ? t("entry.savePractice") : t("entry.checkAndSave"))}
            </button>
          </div>
          {editingId && <p className="text-xs text-leise">{t("entry.editHint")}</p>}
          {!editingId && !isPractice && !canManageAll && (
            <p className="text-xs text-leise">{t("entry.juryHint")}</p>
          )}
        </div>
      )}

      <ScoreConfirmDialog
        open={confirming}
        context={[[t("scouting.team"), teamName(teamId)], [t("scouting.roundLabel"), String(round ?? "")]]}
        fields={fields}
        values={scores}
        total={preview}
        offline={!online}
        pending={saveM.isPending}
        warning={duplicateText || undefined}
        blocked={!!duplicate}
        action={duplicate && canManageAll ? <button type="button" className="btn-secondary min-h-11" onClick={correctDuplicate}>{t("entry.correctExisting")}</button> : undefined}
        onConfirm={() => saveM.mutate()}
        onCancel={() => setConfirming(false)}
      />

      {/* Practice progress summary */}
      {isPractice && practiceScores.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="card p-4"><div className="text-leise text-sm">{t("entry.best")}</div><div className="text-2xl font-bold text-akzent">{practiceBest}</div></div>
          <div className="card p-4"><div className="text-leise text-sm">{t("entry.average")}</div><div className="text-2xl font-bold text-fg">{practiceAvg}</div></div>
          <div className="card p-4"><div className="text-leise text-sm">{t("scouting.runs")}</div><div className="text-2xl font-bold text-fg">{practiceScores.length}</div></div>
        </div>
      )}

      {/* Matches list */}
      <section className="card overflow-hidden">
        <h2 className="px-4 py-3 border-b font-semibold text-fg">
          {t(isPractice ? "entry.practiceRuns" : "entry.recorded", { count: visibleMatches.length })}
        </h2>
        <div className="table-scroll">
        <table className="w-full text-sm">
          <thead className="bg-flaeche-2">
            <tr>
              <th className="px-4 py-3 text-left font-semibold">{t("scouting.team")}</th>
              <th className="px-4 py-3 text-right font-semibold">{isPractice ? t("entry.run") : t("scouting.roundLabel")}</th>
              <th className="px-4 py-3 text-right font-semibold">{t("scouting.points")}</th>
              {!isPractice && <th className="px-4 py-3 text-left font-semibold">{t("common:status")}</th>}
              {canManageAll && <th className="px-4 py-3 text-right font-semibold">{t("common:actions")}</th>}
            </tr>
          </thead>
          <tbody className="divide-y">
            {visibleMatches.map((m: any) => (
              <tr key={m.id} className="hover:bg-flaeche-2">
                <td className="px-4 py-3 text-fg">{teamName(m.team_id)}</td>
                <td className="px-4 py-3 text-right text-leise">{m.round_number}</td>
                <td className="px-4 py-3 text-right font-semibold">{m.total_score}</td>
                {!isPractice && (
                  <td className="px-4 py-3">
                    <span className={m.confirmed_by ? "badge-green" : "badge-yellow"}>
                      {m.confirmed_by ? t("entry.confirmed") : t("entry.open")}
                    </span>
                    <PenaltyBadges match={m} />
                  </td>
                )}
                {canManageAll && (
                  <td className="px-4 py-1 text-right">
                    {/* 44px targets; delete sits apart from confirm behind a divider and asks first. */}
                    <div className="inline-flex items-center gap-1">
                      <button type="button" onClick={() => startEdit(m)} disabled={!online}
                              className="grid h-11 w-11 place-items-center rounded-lg text-leise hover:bg-flaeche-2 disabled:opacity-40"
                              title={t("common:edit")} aria-label={t("entry.editFor", { team: teamName(m.team_id), round: m.round_number })}><Pencil className="w-4 h-4" aria-hidden="true" /></button>
                      {!isPractice && (
                        <button type="button" onClick={() => setPenaltyMatch(m)} disabled={!online}
                                className="grid h-11 w-11 place-items-center rounded-lg text-warning hover:bg-warning/10 disabled:opacity-40"
                                title={t("penalty.open")} aria-label={t("penalty.openFor", { team: teamName(m.team_id), round: m.round_number })}><Flag className="w-4 h-4" aria-hidden="true" /></button>
                      )}
                      {!isPractice && !m.confirmed_by && (
                        <button type="button" onClick={() => startConfirm(m.id)} disabled={confirmM.isPending}
                                className="grid h-11 w-11 place-items-center rounded-lg text-success hover:bg-success/10 disabled:opacity-40"
                                title={t("entry.confirm")} aria-label={t("entry.confirmFor", { team: teamName(m.team_id), round: m.round_number })}><Check className="w-4 h-4" aria-hidden="true" /></button>
                      )}
                      <span className="mx-1 h-6 w-px bg-gray-200 dark:bg-gray-700" aria-hidden="true" />
                      <button type="button" onClick={() => void askDelete(m)} disabled={deleteM.isPending}
                              className="grid h-11 w-11 place-items-center rounded-lg text-danger hover:bg-danger/10 disabled:opacity-40"
                              title={t("common:delete")} aria-label={t("entry.deleteFor", { team: teamName(m.team_id), round: m.round_number })}><Trash2 className="w-4 h-4" aria-hidden="true" /></button>
                    </div>
                  </td>
                )}
              </tr>
            ))}
            {visibleMatches.length === 0 && (
              <tr><td colSpan={(isPractice ? 3 : 4) + (canManageAll ? 1 : 0)} className="px-4 py-8 text-center text-leise">
                {isPractice ? t("entry.noPracticeRuns") : t("entry.noScores")}
              </td></tr>
            )}
          </tbody>
        </table>
        </div>
      </section>
      <MatchPenaltyDialog
        match={penaltyMatch}
        title={penaltyMatch ? t("penalty.title", { team: teamName(penaltyMatch.team_id), round: penaltyMatch.round_number }) : ""}
        onClose={() => setPenaltyMatch(null)}
        onSaved={invalidate}
      />
      <ChecklistConfirmDialog
        open={!!checklistMatchId}
        items={checklist}
        pending={confirmM.isPending}
        error={confirmError}
        onCancel={() => { setChecklistMatchId(null); setConfirmError(""); }}
        onConfirm={(items) => checklistMatchId && confirmM.mutate({ mid: checklistMatchId, items })}
      />
    </div>
  );
}

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Trans, useTranslation } from "react-i18next";
import { ClipboardList, ArrowLeft, Check, Trash2, Save, Dumbbell, Trophy, Pencil, X, Flag } from "lucide-react";
import { api, isQueuedResponse } from "@/lib/api";
import { EventLink } from "@/components/EventLink";
import PendingScores from "@/components/PendingScores";
import ScoreConfirmDialog from "@/components/ScoreConfirmDialog";
import { useOnlineStatus } from "@/hooks/useOnlineStatus";
import { useAuthStore } from "@/store/authStore";
import { useScoringScope } from "@/hooks/useScoringScope";
import clsx from "clsx";
import { computeSheet, normalize } from "@/modules/scoring/sheet/calculator";
import ChecklistConfirmDialog from "@/modules/scoring/extras/ChecklistConfirmDialog";
import MatchPenaltyDialog, { PenaltyBadges, type PenaltyMatch } from "@/modules/scoring/extras/MatchPenaltyDialog";
import type { RuleSet } from "@/modules/scoring/extras/types";
import { formatNumber } from "@/i18n/format";

interface Field {
  key: string;
  label: string;
  multiplier: number;
  max_value: number | null;
  type: "count" | "boolean";
}

type Mode = "contest" | "practice";

export default function ScoreEntryPage() {
  const { t } = useTranslation("scoring");
  const qc = useQueryClient();
  const canEnter = useAuthStore((s) => s.hasPermission("scoring:write"));
  const canManageAll = useAuthStore((s) => s.hasPermission("scoring:admin")); // any team + confirm/delete

  const [mode, setMode] = useState<Mode>("contest");
  const isPractice = mode === "practice";
  const online = useOnlineStatus();
  const [confirming, setConfirming] = useState(false);
  const [notice, setNotice] = useState("");

  // Scores are entered for the event of the current route; without one the
  // backend falls back to the season's default event.
  const { eventId, seasonId: sid, season } = useScoringScope();
  const eventQuery = eventId ? `?event_id=${eventId}` : "";

  const { data: allTeams } = useQuery({
    queryKey: ["teams"],
    queryFn: async () => (await api.get("/teams")).data,
  });
  const { data: myTeams } = useQuery({
    queryKey: ["teams-mine"],
    queryFn: async () => (await api.get("/teams/mine")).data,
    enabled: canEnter && !canManageAll,
  });
  const { data: schema } = useQuery({
    queryKey: ["scoring-schema", sid, eventId],
    queryFn: async () => (await api.get(`/scoring/seasons/${sid}/schema${eventQuery}`)).data,
    enabled: !!sid,
  });
  const { data: matches } = useQuery({
    queryKey: ["matches", sid, eventId],
    queryFn: async () => (await api.get(`/scoring/seasons/${sid}/matches${eventQuery}`)).data,
    enabled: !!sid,
  });

  const entryTeams = canManageAll ? allTeams : myTeams;
  const teamName = (tid: string) => allTeams?.find((team: any) => team.id === tid)?.name ?? tid;

  const [teamId, setTeamId] = useState("");
  const [round, setRound] = useState(1);
  const [scores, setScores] = useState<Record<string, number>>({});

  const { data: rules } = useQuery<RuleSet>({
    queryKey: ["scoring-rules", sid],
    queryFn: async () => (await api.get(`/scoring/seasons/${sid}/rules`)).data,
    enabled: !!sid,
  });

  const fields: Field[] = schema?.fields ?? [];
  // Same calculation as the backend (area multipliers, either-or, sides A/B).
  const sheet = computeSheet(scores, normalize(schema?.fields, schema?.definition));
  const preview = sheet.total;

  const invalidate = () => qc.invalidateQueries({ queryKey: ["matches", sid, eventId] });
  const onError = (e: any) => alert(e?.response?.data?.detail ?? t("common:actionFailed"));

  const [editingId, setEditingId] = useState<string | null>(null);
  const rawFromScores = () => Object.fromEntries(fields.map((f) => [f.key, Number(scores[f.key] || 0)]));
  const resetForm = () => { setScores({}); setEditingId(null); };

  const saveM = useMutation({
    // Resolves to whether the entry went to the offline queue instead of the server.
    mutationFn: async (): Promise<boolean> => {
      if (editingId) {
        await api.patch(`/scoring/matches/${editingId}`, { raw_scores: rawFromScores() });
        return false;
      }
      const { data } = await api.post(
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
      return isQueuedResponse(data);
    },
    onSuccess: (queued) => {
      setConfirming(false);
      setNotice(queued ? t("events:scoreQueued") : "");
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
    setEditingId(m.id);
    setTeamId(m.team_id);
    setRound(m.round_number);
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
      if (checklistMatchId) setConfirmError(e?.response?.data?.detail ?? t("entry.confirmFailed"));
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

  const visibleMatches = (matches ?? [])
    .filter((m: any) => !!m.is_practice === isPractice)
    .filter((m: any) => canManageAll || myTeams?.some((t: any) => t.id === m.team_id))
    .sort((a: any, b: any) => a.round_number - b.round_number);

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
        <div className="card p-8 text-center text-gray-400">{t("entry.noPermission")}</div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <EventLink to="/scoreboard" className="btn-secondary text-sm">
        <ArrowLeft className="w-4 h-4" /> {t("backToScoreboard")}
      </EventLink>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <ClipboardList className="w-6 h-6" /> {t("entry.title")}
        </h1>
        {/* Mode toggle */}
        <div className="inline-flex rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          {([
            ["contest", t("entry.contest"), Trophy],
            ["practice", t("entry.practice"), Dumbbell],
          ] as [Mode, string, any][]).map(([m, label, Icon]) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={clsx(
                "flex items-center gap-2 px-4 py-2 text-sm font-medium transition-colors",
                mode === m
                  ? "bg-primary-600 text-white"
                  : "bg-white dark:bg-gray-900 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
              )}
            >
              <Icon className="w-4 h-4" /> {label}
            </button>
          ))}
        </div>
      </div>

      {isPractice && (
        <p className="text-sm text-gray-500">
          <Trans t={t} i18nKey="entry.practiceHint" components={{ strong: <strong /> }} />
        </p>
      )}

      {!online && (
        <p role="alert" className="rounded-lg bg-amber-100 p-3 text-sm text-amber-900">
          {t("entry.offline")}
        </p>
      )}
      {sid && <PendingScores filter={(entry) => entry.url === `/scoring/seasons/${sid}/matches` && (entry.eventId ?? undefined) === eventId && !!entry.body.is_practice === isPractice} />}
      {notice && <p role="status" className="rounded-lg bg-gray-100 p-3 text-sm dark:bg-gray-800">{notice}</p>}

      {!season && <p className="text-red-600 text-sm">{t("entry.noSeason")}</p>}
      {season && !schema && (
        <p className="text-yellow-600 text-sm">{t("entry.noSchema")}</p>
      )}

      {/* Entry form */}
      {season && schema && (
        <div className="card p-6 space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <label className="label">{t("scouting.team")}</label>
              <select className="input" value={teamId} disabled={!!editingId} onChange={(e) => setTeamId(e.target.value)}>
                <option value="">{t("entry.chooseTeam")}</option>
                {entryTeams?.map((team: any) => (<option key={team.id} value={team.id}>{team.name}</option>))}
              </select>
            </div>
            <div>
              <label className="label">{isPractice ? t("entry.runNumber") : t("scouting.roundLabel")}</label>
              <input type="number" min={1} className="input" value={round} disabled={!!editingId}
                     onChange={(e) => setRound(Number(e.target.value) || 1)} />
            </div>
            <div className="flex items-end">
              <div className="text-sm">
                <div className="text-gray-500">{t("entry.preview")}</div>
                <div className="text-2xl font-bold text-primary-600 dark:text-primary-400">{preview}</div>
                {sheet.errors.length > 0 && <div role="alert" className="text-xs text-red-600">{sheet.errors[0]}</div>}
              </div>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 border-t pt-4">
            {fields.map((f) => (
              <div key={f.key}>
                <label className="label">{f.label} <span className="text-gray-400">(×{f.multiplier})</span></label>
                {f.type === "boolean" ? (
                  <label className="inline-flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={!!scores[f.key]}
                           onChange={(e) => setScores({ ...scores, [f.key]: e.target.checked ? 1 : 0 })} />
                    {t("entry.achieved")}
                  </label>
                ) : (
                  <input type="number" min={0} max={f.max_value ?? undefined} className="input"
                         value={scores[f.key] ?? ""}
                         onChange={(e) => setScores({ ...scores, [f.key]: Number(e.target.value) })} />
                )}
              </div>
            ))}
          </div>

          <div className="flex justify-end gap-2">
            {editingId && (
              <button className="btn-secondary" onClick={resetForm}><X className="w-4 h-4" /> {t("common:cancel")}</button>
            )}
            <button className="btn-primary disabled:opacity-40" disabled={!teamId || saveM.isPending}
                    onClick={submit}>
              <Save className="w-4 h-4" /> {editingId ? t("entry.saveChanges") : (isPractice ? t("entry.savePractice") : t("entry.checkAndSave"))}
            </button>
          </div>
          {editingId && <p className="text-xs text-gray-400">{t("entry.editHint")}</p>}
          {!editingId && !isPractice && !canManageAll && (
            <p className="text-xs text-gray-400">{t("entry.juryHint")}</p>
          )}
        </div>
      )}

      <ScoreConfirmDialog
        open={confirming}
        context={[[t("scouting.team"), teamName(teamId)], [t("scouting.roundLabel"), String(round)]]}
        fields={fields}
        values={scores}
        total={preview}
        offline={!online}
        pending={saveM.isPending}
        onConfirm={() => saveM.mutate()}
        onCancel={() => setConfirming(false)}
      />

      {/* Practice progress summary */}
      {isPractice && practiceScores.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="card p-4"><div className="text-gray-500 text-sm">{t("entry.best")}</div><div className="text-2xl font-bold text-primary-600 dark:text-primary-400">{practiceBest}</div></div>
          <div className="card p-4"><div className="text-gray-500 text-sm">{t("entry.average")}</div><div className="text-2xl font-bold text-gray-900 dark:text-white">{practiceAvg}</div></div>
          <div className="card p-4"><div className="text-gray-500 text-sm">{t("scouting.runs")}</div><div className="text-2xl font-bold text-gray-900 dark:text-white">{practiceScores.length}</div></div>
        </div>
      )}

      {/* Matches list */}
      <section className="card overflow-hidden">
        <h2 className="px-4 py-3 border-b font-semibold text-gray-900 dark:text-white">
          {t(isPractice ? "entry.practiceRuns" : "entry.recorded", { count: visibleMatches.length })}
        </h2>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">{t("scouting.team")}</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">{isPractice ? t("entry.run") : t("scouting.roundLabel")}</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">{t("scouting.points")}</th>
              {!isPractice && <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">{t("common:status")}</th>}
              {canManageAll && <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">{t("common:actions")}</th>}
            </tr>
          </thead>
          <tbody className="divide-y dark:divide-gray-800">
            {visibleMatches.map((m: any) => (
              <tr key={m.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <td className="px-4 py-3 text-gray-900 dark:text-white">{teamName(m.team_id)}</td>
                <td className="px-4 py-3 text-right text-gray-500">{m.round_number}</td>
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
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex items-center gap-1">
                      <button onClick={() => startEdit(m)} disabled={!online}
                              className="p-1 rounded text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
                              title={t("common:edit")}><Pencil className="w-4 h-4" /></button>
                      {!isPractice && (
                        <button onClick={() => setPenaltyMatch(m)} disabled={!online}
                                className="p-1 rounded text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-900/30 disabled:opacity-40"
                                title={t("penalty.open")} aria-label={t("penalty.openFor", { team: teamName(m.team_id), round: m.round_number })}><Flag className="w-4 h-4" /></button>
                      )}
                      {!isPractice && !m.confirmed_by && (
                        <button onClick={() => startConfirm(m.id)} disabled={confirmM.isPending}
                                className="p-1 rounded text-green-600 hover:bg-green-50 dark:hover:bg-green-900/30 disabled:opacity-40"
                                title={t("entry.confirm")}><Check className="w-4 h-4" /></button>
                      )}
                      <button onClick={() => deleteM.mutate(m.id)} disabled={deleteM.isPending}
                              className="p-1 rounded text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 disabled:opacity-40"
                              title={t("common:delete")}><Trash2 className="w-4 h-4" /></button>
                    </div>
                  </td>
                )}
              </tr>
            ))}
            {visibleMatches.length === 0 && (
              <tr><td colSpan={(isPractice ? 3 : 4) + (canManageAll ? 1 : 0)} className="px-4 py-8 text-center text-gray-400">
                {isPractice ? t("entry.noPracticeRuns") : t("entry.noScores")}
              </td></tr>
            )}
          </tbody>
        </table>
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

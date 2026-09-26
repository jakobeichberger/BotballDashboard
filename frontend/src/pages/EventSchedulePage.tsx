import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router";
import { useTranslation } from "react-i18next";
import { CalendarDays, ListOrdered, WandSparkles } from "lucide-react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import BracketView from "@/components/BracketView";
import AllianceStandings from "@/components/events/AllianceStandings";
import type { BracketPhase, EventPhase, ScheduledMatch } from "@/api/types";
import { phaseLabel } from "@/api/analytics";
import { formatDateTime } from "@/i18n/format";
import { apiErrorMessage } from "@/lib/errors";

const MATCH_STATUSES = ["scheduled", "called", "running", "completed", "cancelled"];

type MatchEdit = {
  scheduled_at?: string;
  table_number?: number;
  status?: string;
};

function toLocalDateTimeInput(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return localDate.toISOString().slice(0, 16);
}

export default function EventSchedulePage() {
  const { t } = useTranslation("events");
  const { eventId = "" } = useParams();
  const queryClient = useQueryClient();
  const canManage = useAuthStore((state) => state.hasPermission("events:admin"));
  const canEdit = useAuthStore((state) => state.hasPermission("events:write"));
  const canScore = useAuthStore((state) => state.hasPermission("scoring:admin"));
  const [phaseId, setPhaseId] = useState("");
  const [notice, setNotice] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [error, setError] = useState("");
  const [edits, setEdits] = useState<Record<string, MatchEdit>>({});

  const phases = useQuery<EventPhase[]>({
    queryKey: ["event-phases", eventId],
    queryFn: async () => (await api.get(`/v1/events/${eventId}/phases`)).data,
  });
  const schedule = useQuery<ScheduledMatch[]>({
    queryKey: ["event-schedule", eventId],
    queryFn: async () => (await api.get(`/v1/events/${eventId}/schedule`)).data,
    refetchInterval: 15_000,
  });
  const bracket = useQuery<BracketPhase[]>({
    queryKey: ["event-bracket", eventId],
    queryFn: async () => (await api.get(`/v1/events/${eventId}/bracket`)).data,
    refetchInterval: 15_000,
  });
  const refreshSchedule = () => {
    queryClient.invalidateQueries({ queryKey: ["event-schedule", eventId] });
    queryClient.invalidateQueries({ queryKey: ["event-bracket", eventId] });
  };
  const assignSeeds = useMutation({
    mutationFn: async () =>
      api.post(`/v1/events/${eventId}/registrations/seeds-from-seeding`, {}),
    onSuccess: (response) => {
      setError("");
      setNotice(t("schedulePage.seedsTaken", { count: response.data.length }));
      queryClient.invalidateQueries({ queryKey: ["event-registrations", eventId] });
    },
    onError: (reason: any) =>
      setError(apiErrorMessage(reason, t("schedulePage.seedsFailed"))),
  });
  const recordResult = useMutation({
    mutationFn: async ({ match, teamId }: { match: ScheduledMatch; teamId: string }) =>
      api.post(`/v1/events/${eventId}/schedule/${match.id}/result`, {
        winner_team_id: teamId,
        expected_version: match.version,
      }),
    onSuccess: () => {
      setError("");
      refreshSchedule();
    },
    onError: (reason: any) =>
      setError(apiErrorMessage(reason, t("schedulePage.resultFailed"))),
  });
  const generate = useMutation({
    mutationFn: async () =>
      api.post(`/v1/events/${eventId}/schedule/generate`, {
        phase_id: phaseId,
        starts_at: new Date(startsAt).toISOString(),
        slot_minutes: 10,
      }),
    onSuccess: () => {
      setError("");
      refreshSchedule();
    },
    onError: (reason: any) =>
      setError(apiErrorMessage(reason, t("schedulePage.generateFailed"))),
  });
  const updateMatch = useMutation({
    mutationFn: async (match: ScheduledMatch) =>
      api.patch(`/v1/events/${eventId}/schedule/${match.id}`, {
        ...edits[match.id],
        expected_version: match.version,
      }),
    onSuccess: (_response, match) => {
      setError("");
      setEdits((current) => {
        const next = { ...current };
        delete next[match.id];
        return next;
      });
      queryClient.invalidateQueries({ queryKey: ["event-schedule", eventId] });
    },
    onError: (reason: any) =>
      setError(
        apiErrorMessage(reason, t("schedulePage.updateFailed")),
      ),
  });

  const phaseMap = new Map(phases.data?.map((phase) => [phase.id, phase.name]));

  return (
    <div className="mx-auto max-w-7xl p-4 md:p-6">
      <div className="page-header">
        <div className="min-w-0">
          <h1 className="page-title flex items-center gap-2">
            <CalendarDays className="h-7 w-7 shrink-0 text-akzent" aria-hidden="true" />
            {t("schedulePage.title")}
          </h1>
          <p className="page-subtitle">{t("schedulePage.subtitle")}</p>
        </div>
        {canManage && (
          <button
            type="button"
            className="btn-secondary flex items-center gap-2"
            disabled={assignSeeds.isPending}
            onClick={() => assignSeeds.mutate()}
            title={t("schedulePage.seedsHint")}
          >
            <ListOrdered className="h-4 w-4" />
            {t("schedulePage.seeds")}
          </button>
        )}
      </div>
      {notice && (
        <p role="status" className="mb-4 text-sm text-success">
          {notice}
        </p>
      )}

      {canManage && (
        <form
          className="card mb-6 grid gap-3 p-4 md:grid-cols-[1fr_1fr_auto]"
          onSubmit={(event) => {
            event.preventDefault();
            generate.mutate();
          }}
        >
          <select
            aria-label={t("schedulePage.phase")}
            className="input"
            value={phaseId}
            required
            onChange={(event) => setPhaseId(event.target.value)}
          >
            <option value="">{t("schedulePage.choosePhase")}</option>
            {phases.data?.map((phase) => (
              <option key={phase.id} value={phase.id}>
                {phase.name} · {phaseLabel(phase.phase_type)}
              </option>
            ))}
          </select>
          <input
            aria-label={t("schedulePage.startTime")}
            className="input"
            type="datetime-local"
            required
            value={startsAt}
            onChange={(event) => setStartsAt(event.target.value)}
          />
          <button
            className="btn-primary flex items-center justify-center gap-2"
            disabled={generate.isPending}
          >
            <WandSparkles className="h-4 w-4" />
            {t("schedulePage.generate")}
          </button>
          {error && (
            <p role="alert" className="text-sm text-danger md:col-span-3">
              {error}
            </p>
          )}
        </form>
      )}

      <div className="card overflow-x-auto" tabIndex={0} role="region" aria-label={t("schedulePage.title")}>
        <table className="w-full min-w-[900px] text-sm">
          <thead className="bg-flaeche-2">
            <tr>
              {[
                t("schedulePage.col.time"),
                t("schedulePage.col.code"),
                t("schedulePage.col.phase"),
                t("schedulePage.col.round"),
                t("schedulePage.col.table"),
                t("schedulePage.col.teams"),
                t("common:status"),
                ...(canEdit ? [t("schedulePage.col.action")] : []),
              ].map((label) => (
                <th key={label} className="px-4 py-3 text-left">
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y">
            {schedule.data?.map((match) => (
              <tr key={match.id}>
                <td className="whitespace-nowrap px-4 py-3">
                  {canEdit ? (
                    <input
                      aria-label={t("schedulePage.timeOf", { code: match.code })}
                      className="input w-48"
                      type="datetime-local"
                      value={toLocalDateTimeInput(
                        edits[match.id]?.scheduled_at ?? match.scheduled_at,
                      )}
                      onChange={(event) =>
                        setEdits((current) => ({
                          ...current,
                          [match.id]: {
                            ...current[match.id],
                            scheduled_at: event.target.value
                              ? new Date(event.target.value).toISOString()
                              : undefined,
                          },
                        }))
                      }
                    />
                  ) : match.scheduled_at ? (
                    formatDateTime(match.scheduled_at, { dateStyle: "short", timeStyle: "short" })
                  ) : (
                    "–"
                  )}
                </td>
                <td className="px-4 py-3 font-mono">{match.code}</td>
                <td className="px-4 py-3">{phaseMap.get(match.phase_id)}</td>
                <td className="px-4 py-3">{match.round_number}</td>
                <td className="px-4 py-3">
                  {canEdit ? (
                    <input
                      aria-label={t("schedulePage.tableOf", { code: match.code })}
                      className="input w-20"
                      type="number"
                      min={1}
                      value={edits[match.id]?.table_number ?? match.table_number ?? ""}
                      onChange={(event) =>
                        setEdits((current) => ({
                          ...current,
                          [match.id]: {
                            ...current[match.id],
                            table_number: Number(event.target.value),
                          },
                        }))
                      }
                    />
                  ) : (
                    (match.table_number ?? "–")
                  )}
                </td>
                <td className="px-4 py-3">
                  {match.participants
                    .map((participant) => participant.team_name ?? t("tbd"))
                    .join(" vs. ") || t("tbd")}
                </td>
                <td className="px-4 py-3">
                  {canEdit ? (
                    <select
                      aria-label={t("schedulePage.statusOf", { code: match.code })}
                      className="input"
                      value={edits[match.id]?.status ?? match.status}
                      onChange={(event) =>
                        setEdits((current) => ({
                          ...current,
                          [match.id]: {
                            ...current[match.id],
                            status: event.target.value,
                          },
                        }))
                      }
                    >
                      {MATCH_STATUSES.map(
                        (status) => (
                          <option key={status} value={status}>{t(`matchStatus.${status}`)}</option>
                        ),
                      )}
                    </select>
                  ) : (
                    t(`matchStatus.${match.status}`, { defaultValue: match.status })
                  )}
                </td>
                {canEdit && (
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      className="btn-secondary"
                      disabled={!edits[match.id] || updateMatch.isPending}
                      onClick={() => updateMatch.mutate(match)}
                    >
                      {t("common:save")}
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {!schedule.isLoading && !schedule.data?.length && (
          <p className="p-8 text-center text-leise">{t("schedulePage.empty")}</p>
        )}
      </div>

      {phases.data?.filter((phase) => phase.phase_type === "alliance").map((phase) => (
        <AllianceStandings key={phase.id} eventId={eventId} phase={phase} />
      ))}

      {!!bracket.data?.length && (
        <section className="card mt-6 p-4" aria-labelledby="bracket-heading">
          <h2 id="bracket-heading" className="mb-1 text-xl font-bold">
            {t("schedulePage.brackets")}
          </h2>
          {canScore && (
            <p className="mb-4 text-sm text-leise">
              {t("schedulePage.bracketHint")}
            </p>
          )}
          {!canManage && error && (
            <p role="alert" className="mb-3 text-sm text-danger">
              {error}
            </p>
          )}
          <BracketView
            phases={bracket.data}
            onPickWinner={
              canScore ? (match, teamId) => recordResult.mutate({ match, teamId }) : undefined
            }
            disabled={recordResult.isPending}
          />
        </section>
      )}
    </div>
  );
}

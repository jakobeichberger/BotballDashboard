import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { formatDateTime } from "@/i18n/format";
import { useAuthStore } from "@/store/authStore";
import type { EventRegistration } from "@/api/types";
import {
  formatAuditValue,
  revisionChanges,
  scoreRevisionKind,
  type FieldChange,
  type ResultRevision,
  type ScoreRevision,
} from "@/lib/audit";

type Tab = "scores" | "results";
const RESULT_KINDS = ["de", "aerial", "doc"] as const;

/**
 * Audit trail of an event for organizers: every score revision (including
 * deleted runs, cards and DQs) and every change of the DE, aerial and
 * documentation results, newest first.
 */
export default function EventAuditTrail({ eventId }: { eventId: string }) {
  const { t } = useTranslation("analytics");
  const canReadUsers = useAuthStore((state) => state.hasPermission("users:read"));
  const [tab, setTab] = useState<Tab>("scores");
  const [teamId, setTeamId] = useState("");
  const [kind, setKind] = useState("");
  const params = { team_id: teamId || undefined };

  const registrations = useQuery<EventRegistration[]>({ queryKey: ["event-registrations", eventId], queryFn: async () => (await api.get(`/v1/events/${eventId}/registrations`)).data, enabled: !!eventId });
  const users = useQuery<Array<{ id: string; display_name: string }>>({ queryKey: ["users"], queryFn: async () => (await api.get("/auth/users")).data, enabled: canReadUsers });
  const scores = useQuery<ScoreRevision[]>({
    queryKey: ["event-revisions", eventId, teamId],
    queryFn: async () => (await api.get(`/scoring/events/${eventId}/revisions`, { params })).data,
    enabled: !!eventId && tab === "scores",
  });
  const results = useQuery<ResultRevision[]>({
    queryKey: ["event-result-revisions", eventId, teamId, kind],
    queryFn: async () => (await api.get(`/scoring/events/${eventId}/result-revisions`, { params: { ...params, kind: kind || undefined } })).data,
    enabled: !!eventId && tab === "results",
  });

  const teamName = (id: string | null) => (id ? registrations.data?.find((item) => item.team_id === id)?.team_name ?? id.slice(0, 8) : "—");
  const userName = (id: string | null) => (id ? users.data?.find((item) => item.id === id)?.display_name ?? id.slice(0, 8) : t("audit.system"));
  const value = (v: unknown) => formatAuditValue(v, t("audit.yes"), t("audit.no"));
  const fieldLabel = (key: string) => (key.startsWith("raw_scores.") ? key.slice("raw_scores.".length) : t(`audit.field.${key}`, { defaultValue: key }));
  const changeList = (changes: FieldChange[]) =>
    changes.length ? (
      <ul className="space-y-0.5">
        {changes.map((change) => <li key={change.key}><span className="text-leise">{fieldLabel(change.key)}:</span> {value(change.before)} → <strong>{value(change.after)}</strong></li>)}
      </ul>
    ) : <span className="text-leise">{t("audit.noChange")}</span>;

  const rows = tab === "scores" ? scores : results;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <div role="tablist" aria-label={t("audit.title")} className="inline-flex overflow-hidden rounded-lg border border-rand">
          {(["scores", "results"] as Tab[]).map((key) => (
            <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => setTab(key)} className={`px-3 py-1.5 text-sm ${tab === key ? "bg-primary-600 text-white" : "bg-white hover:bg-gray-50 dark:bg-gray-900 dark:hover:bg-gray-800"}`}>
              {t(`audit.tab.${key}`)}
            </button>
          ))}
        </div>
        <select aria-label={t("audit.team")} className="input w-auto" value={teamId} onChange={(e) => setTeamId(e.target.value)}>
          <option value="">{t("audit.allTeams")}</option>
          {registrations.data?.map((item) => <option key={item.id} value={item.team_id}>{item.team_name}</option>)}
        </select>
        {tab === "results" && (
          <select aria-label={t("audit.kind")} className="input w-auto" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">{t("audit.allKinds")}</option>
            {RESULT_KINDS.map((key) => <option key={key} value={key}>{t(`audit.kindLabel.${key}`)}</option>)}
          </select>
        )}
      </div>
      {rows.isError && <p className="text-sm text-red-600">{t("audit.loadFailed")}</p>}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="text-left text-leise">
              <th scope="col" className="py-1 pr-3 font-medium">{t("audit.col.time")}</th>
              <th scope="col" className="py-1 pr-3 font-medium">{t("audit.col.team")}</th>
              <th scope="col" className="py-1 pr-3 font-medium">{t("audit.col.what")}</th>
              <th scope="col" className="py-1 pr-3 font-medium">{t("audit.col.changes")}</th>
              <th scope="col" className="py-1 font-medium">{t("audit.col.by")}</th>
            </tr>
          </thead>
          <tbody>
            {tab === "scores" && scores.data?.map((rev) => {
              const revKind = scoreRevisionKind(rev);
              return (
                <tr key={rev.id} className="border-t border-rand align-top">
                  <td className="whitespace-nowrap py-1.5 pr-3 tabular-nums">{formatDateTime(rev.created_at, { dateStyle: "short", timeStyle: "medium" })}</td>
                  <td className="py-1.5 pr-3">{teamName(rev.team_id)}</td>
                  <td className="py-1.5 pr-3">
                    <span className={revKind === "deleted" ? "badge-red" : revKind === "created" ? "badge-green" : "badge-yellow"}>{t(`audit.scoreKind.${revKind}`)}</span>
                    <span className="ml-1 text-xs text-leise">{t("audit.revision", { revision: rev.revision })}</span>
                    {rev.reason && <p className="mt-0.5 text-xs text-leise">{rev.reason}</p>}
                  </td>
                  <td className="py-1.5 pr-3">
                    {revKind === "updated" ? changeList(revisionChanges(rev.previous_value, rev.new_value)) : <span>{t("audit.total", { total: value((revKind === "deleted" ? rev.previous_value : rev.new_value)?.total_score) })}</span>}
                  </td>
                  <td className="py-1.5">{userName(rev.changed_by)}</td>
                </tr>
              );
            })}
            {tab === "results" && results.data?.map((rev) => (
              <tr key={rev.id} className="border-t border-rand align-top">
                <td className="whitespace-nowrap py-1.5 pr-3 tabular-nums">{formatDateTime(rev.created_at, { dateStyle: "short", timeStyle: "medium" })}</td>
                <td className="py-1.5 pr-3">{teamName(rev.team_id)}</td>
                <td className="py-1.5 pr-3"><span className="badge-blue">{t(`audit.kindLabel.${rev.kind}`, { defaultValue: rev.kind })}</span>{!rev.new_value && <span className="ml-1 badge-red">{t("audit.scoreKind.deleted")}</span>}</td>
                <td className="py-1.5 pr-3">{changeList(revisionChanges(rev.previous_value, rev.new_value))}</td>
                <td className="py-1.5">{userName(rev.changed_by)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.isLoading && !rows.data?.length && <p className="py-4 text-center text-sm text-leise">{t("audit.empty")}</p>}
      </div>
    </div>
  );
}

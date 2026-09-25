import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import Modal from "@/components/Modal";
import { EventLink } from "@/components/EventLink";
import { api } from "@/lib/api";
import type { Anomaly } from "@/api/analytics";
import { formatDateTime } from "@/i18n/format";

/**
 * Double-check a flagged run: raw values, revision history and the reasons it
 * was flagged, with the juror's confirm action right there.
 */
export default function MatchReviewModal({ anomaly, onClose }: { anomaly: Anomaly | null; onClose: () => void }) {
  const { t } = useTranslation("analytics");
  const qc = useQueryClient();
  const matchId = anomaly?.match_id;
  const { data: match } = useQuery({
    queryKey: ["match", matchId],
    queryFn: async () => (await api.get(`/scoring/matches/${matchId}`)).data,
    enabled: !!matchId,
  });
  const { data: revisions } = useQuery<any[]>({
    queryKey: ["match-revisions", matchId],
    queryFn: async () => (await api.get(`/scoring/matches/${matchId}/revisions`)).data,
    enabled: !!matchId,
  });
  const confirm = useMutation({
    mutationFn: () => api.put(`/scoring/matches/${matchId}/confirm`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["match", matchId] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  if (!anomaly) return null;
  const confirmed = !!match?.confirmed_at || anomaly.confirmed;
  return (
    <Modal open={!!anomaly} title={t("review.title", { team: anomaly.team_name, round: anomaly.round_number })} onClose={onClose}>
      <div className="space-y-4 text-sm">
        <ul className="space-y-1" aria-label={t("review.reasons")}>
          {anomaly.reasons.map((r, i) => (
            <li key={i} className={r.severity === "error" ? "text-red-700 dark:text-red-400" : "text-yellow-700 dark:text-yellow-400"}>
              • {r.message}
            </li>
          ))}
        </ul>
        {match && (
          <div className="table-scroll">
          <table className="w-full">
            <caption className="text-left font-medium text-fg">{t("review.values", { total: match.total_score })}</caption>
            <tbody>
              {Object.entries(match.raw_scores ?? {}).map(([key, value]) => (
                <tr key={key} className="border-t border-rand">
                  <th scope="row" className="py-1 text-left font-normal text-leise">{key}</th>
                  <td className="py-1 text-right tabular-nums">{String(value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        )}
        {revisions && revisions.length > 1 && (
          <div>
            <p className="font-medium text-fg">{t("review.changes")}</p>
            <ol className="mt-1 space-y-0.5 text-xs text-leise">
              {revisions.map((rev) => (
                <li key={rev.id}>
                  {t("review.revision", { revision: rev.revision })} {rev.previous_value?.total_score ?? "—"} → {rev.new_value?.total_score ?? "—"}
                  {rev.reason ? ` (${rev.reason})` : ""} · {formatDateTime(rev.created_at)}
                </li>
              ))}
            </ol>
          </div>
        )}
        <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3">
          {anomaly.scheduled_match_id ? (
            <EventLink to="/schedule" className="text-akzent hover:underline">{t("review.viewInSchedule")}</EventLink>
          ) : <span />}
          {confirmed ? (
            <span className="badge-green">{t("review.confirmed")}</span>
          ) : (
            <button type="button" className="btn-primary text-sm" onClick={() => confirm.mutate()} disabled={confirm.isPending}>
              <CheckCircle2 className="h-4 w-4" /> {t("review.confirm")}
            </button>
          )}
        </div>
      </div>
    </Modal>
  );
}

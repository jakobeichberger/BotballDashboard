import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import Modal from "@/components/Modal";
import { EventLink } from "@/components/EventLink";
import { api } from "@/lib/api";
import type { Anomaly } from "@/api/analytics";

/**
 * Double-check a flagged run: raw values, revision history and the reasons it
 * was flagged, with the juror's confirm action right there.
 */
export default function MatchReviewModal({ anomaly, onClose }: { anomaly: Anomaly | null; onClose: () => void }) {
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
    <Modal open={!!anomaly} title={`Lauf prüfen: ${anomaly.team_name}, Runde ${anomaly.round_number}`} onClose={onClose}>
      <div className="space-y-4 text-sm">
        <ul className="space-y-1" aria-label="Auffälligkeiten">
          {anomaly.reasons.map((r, i) => (
            <li key={i} className={r.severity === "error" ? "text-red-700 dark:text-red-400" : "text-yellow-700 dark:text-yellow-400"}>
              • {r.message}
            </li>
          ))}
        </ul>
        {match && (
          <table className="w-full">
            <caption className="text-left font-medium text-gray-700 dark:text-gray-300">Eingetragene Werte (Summe {match.total_score})</caption>
            <tbody>
              {Object.entries(match.raw_scores ?? {}).map(([key, value]) => (
                <tr key={key} className="border-t border-gray-100 dark:border-gray-800">
                  <th scope="row" className="py-1 text-left font-normal text-gray-600 dark:text-gray-400">{key}</th>
                  <td className="py-1 text-right tabular-nums">{String(value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {revisions && revisions.length > 1 && (
          <div>
            <p className="font-medium text-gray-700 dark:text-gray-300">Änderungen</p>
            <ol className="mt-1 space-y-0.5 text-xs text-gray-500">
              {revisions.map((rev) => (
                <li key={rev.id}>
                  Rev. {rev.revision}: {rev.previous_total_score ?? "—"} → {rev.new_total_score}
                  {rev.reason ? ` (${rev.reason})` : ""} · {new Date(rev.created_at).toLocaleString("de-DE")}
                </li>
              ))}
            </ol>
          </div>
        )}
        <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3 dark:border-gray-800">
          {anomaly.scheduled_match_id ? (
            <EventLink to="/schedule" className="text-primary-600 hover:underline dark:text-primary-400">Im Zeitplan ansehen</EventLink>
          ) : <span />}
          {confirmed ? (
            <span className="badge-green">Bestätigt</span>
          ) : (
            <button type="button" className="btn-primary text-sm" onClick={() => confirm.mutate()} disabled={confirm.isPending}>
              <CheckCircle2 className="h-4 w-4" /> Wert ist korrekt – bestätigen
            </button>
          )}
        </div>
      </div>
    </Modal>
  );
}

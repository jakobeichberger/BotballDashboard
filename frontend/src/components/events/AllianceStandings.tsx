import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { formatScore } from "@/i18n/format";
import type { EventPhase } from "@/api/types";

interface AllianceStanding {
  rank: number;
  team_ids: string[];
  team_names: string[];
  runs: Array<{ match_id: string; round_number: number; score: number }>;
  best_score: number;
  total_score: number;
}

/**
 * Ranking of an alliance phase: two teams play together, a run's alliance
 * score is the sum of both; alliances rank by their best run, then by the
 * total of all runs.
 */
export default function AllianceStandings({ eventId, phase }: { eventId: string; phase: EventPhase }) {
  const { t } = useTranslation("events");
  const standings = useQuery<AllianceStanding[]>({
    queryKey: ["alliance-standings", eventId, phase.id],
    queryFn: async () => (await api.get(`/v1/events/${eventId}/phases/${phase.id}/alliances`)).data,
    refetchInterval: 15_000,
  });
  const headingId = `alliances-${phase.id}`;
  return (
    <section className="card mt-6 p-4" aria-labelledby={headingId}>
      <h2 id={headingId} className="mb-1 text-xl font-bold">{t("alliances.title", { phase: phase.name })}</h2>
      <p className="mb-3 text-sm text-gray-500">{t("alliances.hint")}</p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-100 dark:bg-gray-800">
            <tr>
              <th scope="col" className="px-3 py-2 text-left">#</th>
              <th scope="col" className="px-3 py-2 text-left">{t("alliances.alliance")}</th>
              <th scope="col" className="px-3 py-2 text-left">{t("alliances.runs")}</th>
              <th scope="col" className="px-3 py-2 text-right">{t("best")}</th>
              <th scope="col" className="px-3 py-2 text-right">{t("alliances.total")}</th>
            </tr>
          </thead>
          <tbody className="divide-y dark:divide-gray-800">
            {standings.data?.map((row) => (
              <tr key={row.team_ids.join("+")}>
                <td className="px-3 py-2 font-bold">{row.rank}</td>
                <td className="px-3 py-2">{row.team_names.map((name, index) => name || row.team_ids[index]).join(" + ")}</td>
                <td className="px-3 py-2 tabular-nums text-gray-600 dark:text-gray-400">{row.runs.map((run) => formatScore(run.score)).join(" · ") || "–"}</td>
                <td className="px-3 py-2 text-right font-semibold tabular-nums">{formatScore(row.best_score)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatScore(row.total_score)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!standings.isLoading && !standings.data?.length && <p className="p-4 text-center text-sm text-gray-500">{t("alliances.empty")}</p>}
      </div>
    </section>
  );
}

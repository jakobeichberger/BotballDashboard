import { useQuery } from "@tanstack/react-query";
import { useSearchParams, Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Trophy } from "lucide-react";
import { RankingExportButtons } from "@/components/ExportButtons";

interface RankingEntry {
  rank: number;
  team_id: string;
  seed_score: number;
  best_score: number;
  average_score: number;
  rounds_played: number;
}

export default function ScoreboardPage() {
  const [params] = useSearchParams();
  const seasonId = params.get("season_id") ?? "";

  const { data: activeSeasonData } = useQuery({
    queryKey: ["seasons", "active"],
    queryFn: async () => {
      const { data } = await api.get("/seasons/active");
      return data;
    },
  });

  const sid = seasonId || activeSeasonData?.id;

  const { data: ranking, isLoading } = useQuery<RankingEntry[]>({
    queryKey: ["ranking", sid],
    queryFn: async () => {
      const { data } = await api.get(`/scoring/seasons/${sid}/ranking`);
      return data;
    },
    enabled: !!sid,
    refetchInterval: 10_000,
  });

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
          <Trophy className="w-6 h-6 text-yellow-500" />
          Rangliste
        </h1>
        <div className="flex items-center gap-3">
          {sid && activeSeasonData && (
            <RankingExportButtons seasonId={sid} seasonYear={activeSeasonData.year} />
          )}
          <Link to="/scoring/score-sheets" className="btn-secondary text-sm">
            Score-Sheets verwalten
          </Link>
        </div>
      </div>

      {isLoading && <p className="text-gray-500">Laden...</p>}

      {ranking && (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-800">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">#</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600 dark:text-gray-400">Team</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Seed-Score</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Best</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">⌀</th>
                <th className="px-4 py-3 text-right font-medium text-gray-600 dark:text-gray-400">Runden</th>
              </tr>
            </thead>
            <tbody className="divide-y dark:divide-gray-800">
              {ranking.map((entry) => (
                <tr key={entry.team_id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                  <td className="px-4 py-3 font-bold text-gray-900 dark:text-white">
                    {entry.rank <= 3 ? (
                      <span className={entry.rank === 1 ? "text-yellow-500" : entry.rank === 2 ? "text-gray-400" : "text-amber-600"}>
                        {entry.rank}
                      </span>
                    ) : (
                      entry.rank
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-900 dark:text-white font-mono text-xs">{entry.team_id.slice(0, 8)}…</td>
                  <td className="px-4 py-3 text-right font-bold">{entry.seed_score.toFixed(2)}</td>
                  <td className="px-4 py-3 text-right">{entry.best_score.toFixed(2)}</td>
                  <td className="px-4 py-3 text-right">{entry.average_score.toFixed(2)}</td>
                  <td className="px-4 py-3 text-right text-gray-500">{entry.rounds_played}</td>
                </tr>
              ))}
              {ranking.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                    Noch keine Wertungen eingetragen
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

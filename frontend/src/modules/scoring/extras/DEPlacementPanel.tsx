import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { DEPlacementEntry } from "./types";

/** DE placement per bracket; equal DE ranks ordered by the season's tie-breakers. */
export default function DEPlacementPanel({ eventId }: { eventId: string }) {
  const placement = useQuery<DEPlacementEntry[]>({ queryKey: ["de-placement", eventId], queryFn: async () => (await api.get(`/scoring/events/${eventId}/de-placement`)).data, enabled: !!eventId });
  if (!placement.data?.length) return null;
  return (
    <section className="card overflow-hidden" aria-labelledby="de-placement-title">
      <h2 id="de-placement-title" className="border-b px-4 py-3 font-semibold dark:border-gray-800">Platzierung (mit Tie-Breakern)</h2>
      <table className="w-full text-sm">
        <thead className="bg-gray-50 dark:bg-gray-800"><tr><th className="px-4 py-2 text-left">Bracket</th><th className="px-4 py-2 text-left">Platz</th><th className="px-4 py-2 text-left">Team</th><th className="px-4 py-2 text-left">DE-Rang</th><th className="px-4 py-2 text-left">Entschieden durch</th></tr></thead>
        <tbody className="divide-y dark:divide-gray-800">
          {placement.data.map((row) => <tr key={`${row.bracket}-${row.team_id}`}><td className="px-4 py-2">{row.bracket}</td><td className="px-4 py-2 font-bold">{row.placement}</td><td className="px-4 py-2">{row.team_name ?? row.team_id}</td><td className="px-4 py-2">{row.de_rank ?? "–"}</td><td className="px-4 py-2 text-xs text-gray-500">{row.decided_by ?? ""}</td></tr>)}
        </tbody>
      </table>
    </section>
  );
}

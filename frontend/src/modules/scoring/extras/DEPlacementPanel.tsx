import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import type { DEPlacementEntry } from "./types";

/** DE placement per bracket; equal DE ranks ordered by the season's tie-breakers. */
export default function DEPlacementPanel({ eventId }: { eventId: string }) {
  const { t } = useTranslation("scoring");
  const placement = useQuery<DEPlacementEntry[]>({ queryKey: ["de-placement", eventId], queryFn: async () => (await api.get(`/scoring/events/${eventId}/de-placement`)).data, enabled: !!eventId });
  if (!placement.data?.length) return null;
  return (
    <section className="card overflow-hidden" aria-labelledby="de-placement-title">
      <h2 id="de-placement-title" className="border-b px-4 py-3 font-semibold">{t("de.placement")}</h2>
      <div className="table-scroll">
      <table className="w-full text-sm">
        <thead className="bg-flaeche-2"><tr><th className="px-4 py-2 text-left">{t("de.bracket")}</th><th className="px-4 py-2 text-left">{t("de.place")}</th><th className="px-4 py-2 text-left">{t("scouting.team")}</th><th className="px-4 py-2 text-left">{t("de.rank")}</th><th className="px-4 py-2 text-left">{t("events:tiebreaker")}</th></tr></thead>
        <tbody className="divide-y">
          {placement.data.map((row) => <tr key={`${row.bracket}-${row.team_id}`}><td className="px-4 py-2">{row.bracket}</td><td className="px-4 py-2 font-bold">{row.placement}</td><td className="px-4 py-2">{row.team_name ?? row.team_id}</td><td className="px-4 py-2">{row.de_rank ?? "–"}</td><td className="px-4 py-2 text-xs text-leise">{row.decided_by ?? ""}</td></tr>)}
        </tbody>
      </table>
    </div>
    </section>
  );
}

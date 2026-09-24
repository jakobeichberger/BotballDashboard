import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Shuffle } from "lucide-react";
import { api } from "@/lib/api";
import { apiErrorMessage, type AutoAssignResult } from "./paperMeta";

/**
 * Automatic reviewer assignment for organizers: preview the plan, then
 * create it. The backend balances the reviewers' open reviews and skips
 * conflicts of interest (own team, same school).
 */
export function AutoAssignPanel({ seasonId, eventId }: { seasonId: string; eventId?: string }) {
  const qc = useQueryClient();
  const [perPaper, setPerPaper] = useState(2);
  const [result, setResult] = useState<AutoAssignResult | null>(null);
  const runM = useMutation({
    mutationFn: async (dryRun: boolean) =>
      (
        await api.post<AutoAssignResult>("/papers/auto-assign", {
          season_id: seasonId,
          event_id: eventId || null,
          reviewers_per_paper: perPaper,
          dry_run: dryRun,
        })
      ).data,
    onSuccess: (data) => {
      setResult(data);
      if (!data.dry_run) {
        qc.invalidateQueries({ queryKey: ["papers"] });
        qc.invalidateQueries({ queryKey: ["paper-workload"] });
        qc.invalidateQueries({ queryKey: ["paper-stats"] });
      }
    },
  });

  return (
    <section className="card mb-6 p-4 space-y-3" aria-labelledby="auto-assign-heading">
      <h2 id="auto-assign-heading" className="font-semibold flex items-center gap-2">
        <Shuffle className="h-4 w-4" /> Reviewer automatisch zuweisen
      </h2>
      <div className="flex flex-wrap items-end gap-3 text-sm">
        <label>Reviewer pro Paper
          <input
            className="input mt-1 block w-24"
            type="number"
            min={1}
            max={10}
            value={perPaper}
            onChange={(e) => setPerPaper(Math.max(1, Math.min(10, Number(e.target.value) || 1)))}
          />
        </label>
        <button className="btn-secondary" disabled={runM.isPending} onClick={() => runM.mutate(true)}>Vorschau</button>
        <button
          className="btn-primary"
          disabled={runM.isPending || !result?.dry_run || result.assignments.length === 0}
          onClick={() => runM.mutate(false)}
          title={result?.dry_run ? undefined : "Erst eine Vorschau erstellen"}
        >
          Zuweisen
        </button>
      </div>
      {runM.isError && <p role="alert" className="text-sm text-red-600">{apiErrorMessage(runM.error)}</p>}
      {result && (
        <div className="text-sm space-y-2">
          <p className="font-medium">
            {result.dry_run ? "Vorschau" : "Zugewiesen"}: {result.assignments.length} Zuweisung(en)
          </p>
          {result.assignments.length > 0 && (
            <ul className="list-disc pl-5 text-gray-600 dark:text-gray-400">
              {result.assignments.map((a) => (
                <li key={`${a.paper_id}-${a.reviewer_id}`}>{a.paper_title} → {a.reviewer_name}</li>
              ))}
            </ul>
          )}
          {result.unfilled.length > 0 && (
            <p role="status" className="text-yellow-800 dark:text-yellow-200">
              Nicht genug passende Reviewer für: {result.unfilled.map((u) => `${u.paper_title} (${u.missing} fehlen)`).join(", ")}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

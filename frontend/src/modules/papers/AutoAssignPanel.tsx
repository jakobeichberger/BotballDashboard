import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Shuffle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { apiErrorMessage, type AutoAssignResult } from "./paperMeta";

/**
 * Automatic reviewer assignment for organizers: preview the plan, then
 * create it. The backend balances the reviewers' open reviews and skips
 * conflicts of interest (own team, same school).
 */
export function AutoAssignPanel({ seasonId, eventId }: { seasonId: string; eventId?: string }) {
  const { t } = useTranslation("papers");
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
        <Shuffle className="h-4 w-4" /> {t("autoAssign.title")}
      </h2>
      <div className="flex flex-wrap items-end gap-3 text-sm">
        <label>{t("autoAssign.perPaper")}
          <input
            className="input mt-1 block w-24"
            type="number"
            min={1}
            max={10}
            value={perPaper}
            onChange={(e) => setPerPaper(Math.max(1, Math.min(10, Number(e.target.value) || 1)))}
          />
        </label>
        <button className="btn-secondary" disabled={runM.isPending} onClick={() => runM.mutate(true)}>{t("autoAssign.preview")}</button>
        <button
          className="btn-primary"
          disabled={runM.isPending || !result?.dry_run || result.assignments.length === 0}
          onClick={() => runM.mutate(false)}
          title={result?.dry_run ? undefined : t("autoAssign.previewFirst")}
        >
          {t("autoAssign.assign")}
        </button>
      </div>
      {runM.isError && <p role="alert" className="text-sm text-red-600">{apiErrorMessage(runM.error)}</p>}
      {result && (
        <div className="text-sm space-y-2">
          <p className="font-medium">
            {t(result.dry_run ? "autoAssign.previewResult" : "autoAssign.assignedResult", { count: result.assignments.length })}
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
              {t("autoAssign.unfilled", {
                papers: result.unfilled.map((u) => t("autoAssign.missing", { title: u.paper_title, count: u.missing })).join(", "),
              })}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

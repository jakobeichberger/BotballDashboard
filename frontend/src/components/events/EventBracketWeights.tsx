import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { RotateCcw } from "lucide-react";
import { api } from "@/lib/api";
import { CATEGORY_LABEL } from "@/lib/teams";
import BracketWeightsEditor from "@/modules/scoring/extras/BracketWeightsEditor";
import { apiErrorMessage } from "@/lib/errors";

const CATEGORIES = ["botball", "open", "aerial", "jbc"] as const;

/**
 * Bracket weights of one event and category. The game review announces them
 * per tournament; without event weights the season weights (Punkteformeln)
 * apply, and saving an empty list returns to them.
 */
export default function EventBracketWeights({ eventId }: { eventId: string }) {
  const { t } = useTranslation("events");
  const queryClient = useQueryClient();
  const [category, setCategory] = useState<string>("botball");
  const [message, setMessage] = useState("");
  const weights = useQuery<Record<string, number>>({
    queryKey: ["event-bracket-weights", eventId, category],
    queryFn: async () => (await api.get(`/v1/events/${eventId}/bracket-weights`, { params: { category } })).data,
  });
  const save = useMutation({
    mutationFn: async (next: Record<string, number>) => (await api.put(`/v1/events/${eventId}/bracket-weights`, { weights: next }, { params: { category } })).data,
    onSuccess: (_data, next) => {
      setMessage(Object.keys(next).length ? t("setup.weightsSaved") : t("setup.weightsReset"));
      queryClient.invalidateQueries({ queryKey: ["event-bracket-weights", eventId, category] });
    },
    onError: (e: any) => setMessage(apiErrorMessage(e, t("common:actionFailed"))),
  });

  return (
    <div className="space-y-2">
      <label className="flex items-center gap-2 text-sm font-medium">
        {t("setup.category")}
        <select className="input w-auto" value={category} onChange={(e) => { setCategory(e.target.value); setMessage(""); }}>
          {CATEGORIES.map((key) => <option key={key} value={key}>{CATEGORY_LABEL[key]}</option>)}
        </select>
      </label>
      <BracketWeightsEditor
        title={t("setup.bracketWeights")}
        hint={t("setup.bracketWeightsHint")}
        weights={weights.data ?? {}}
        saving={save.isPending}
        disabled={weights.isLoading}
        onSave={(next) => save.mutate(next)}
        actions={
          <button type="button" className="btn-secondary" disabled={save.isPending} onClick={() => save.mutate({})}>
            <RotateCcw className="h-4 w-4" />
            {t("setup.useSeasonWeights")}
          </button>
        }
      />
      {message && <p role="status" className="text-sm text-gray-600 dark:text-gray-300">{message}</p>}
    </div>
  );
}

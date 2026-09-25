import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Plus, Save, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { apiErrorMessage } from "@/lib/errors";
import { toast } from "@/lib/toast";
import { CATEGORY_KINDS, useSeasonCategories, type CategoryKind, type SeasonCategory } from "@/lib/categories";

interface PresetOption { id: string; label: string; category: string }

const KEY_PATTERN = /^[a-z][a-z0-9_]{0,19}$/;

/**
 * The season's category registry: key, labels (DE/EN), kind, the formula
 * preset used while no formulas are stored, aerial run counts and the
 * per-course (DE bracket) overall ranking of GCER.
 */
export default function CategoryRegistryEditor({ seasonId }: { seasonId: string }) {
  const { t } = useTranslation("settings");
  const queryClient = useQueryClient();
  const { categories, isLoading } = useSeasonCategories(seasonId);
  const reference = useQuery<{ presets?: PresetOption[] }>({ queryKey: ["formula-reference"], queryFn: async () => (await api.get("/scoring/formulas/reference")).data });
  const [rows, setRows] = useState<SeasonCategory[]>([]);
  // Start editing once the stored list (or the defaults) has loaded.
  useEffect(() => { if (!isLoading) setRows(categories.map((entry) => ({ ...entry }))); }, [seasonId, isLoading]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = useMutation({
    mutationFn: async () => (await api.put(`/seasons/${seasonId}/categories`, rows.map((row, index) => ({ ...row, sort_order: index })))).data,
    onSuccess: () => { toast.success(t("categories.saved")); queryClient.invalidateQueries({ queryKey: ["season-categories", seasonId] }); },
    onError: (error) => toast.error(apiErrorMessage(error, t("common:actionFailed"))),
  });

  const update = (index: number, patch: Partial<SeasonCategory>) => setRows((prev) => prev.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  const invalid = rows.some((row) => !KEY_PATTERN.test(row.key) || !row.label_de.trim() || !row.label_en.trim()) || new Set(rows.map((row) => row.key)).size !== rows.length;
  const number = (value: string) => (value === "" ? null : Math.max(1, Math.round(Number(value))));

  return (
    <div className="card p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">{t("categories.title")}</h3>
          <p className="text-xs text-gray-500">{t("categories.hint")}</p>
        </div>
        <button type="button" className="btn-primary text-sm" disabled={invalid || save.isPending || !rows.length} onClick={() => save.mutate()}><Save className="h-4 w-4" />{t("common:save")}</button>
      </div>
      <div className="table-scroll">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-500">
              <th className="px-2 py-1">{t("categories.key")}</th>
              <th className="px-2 py-1">{t("categories.labelDe")}</th>
              <th className="px-2 py-1">{t("categories.labelEn")}</th>
              <th className="px-2 py-1">{t("categories.kind")}</th>
              <th className="px-2 py-1">{t("categories.preset")}</th>
              <th className="px-2 py-1">{t("categories.runs")}</th>
              <th className="px-2 py-1">{t("categories.countedRuns")}</th>
              <th className="px-2 py-1">{t("categories.perCourse")}</th>
              <th className="px-2 py-1"><span className="sr-only">{t("categories.remove")}</span></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} className="align-top">
                <td className="px-2 py-1"><input aria-label={t("categories.key")} className="input w-32 font-mono text-xs" value={row.key} onChange={(e) => update(index, { key: e.target.value })} aria-invalid={!KEY_PATTERN.test(row.key)} /></td>
                <td className="px-2 py-1"><input aria-label={t("categories.labelDe")} className="input w-40" value={row.label_de} onChange={(e) => update(index, { label_de: e.target.value })} /></td>
                <td className="px-2 py-1"><input aria-label={t("categories.labelEn")} className="input w-40" value={row.label_en} onChange={(e) => update(index, { label_en: e.target.value })} /></td>
                <td className="px-2 py-1">
                  <select aria-label={t("categories.kind")} className="input w-auto" value={row.kind} onChange={(e) => update(index, { kind: e.target.value as CategoryKind, formula_preset: null })}>
                    {CATEGORY_KINDS.map((kind) => <option key={kind} value={kind}>{t(`categories.kinds.${kind}`)}</option>)}
                  </select>
                </td>
                <td className="px-2 py-1">
                  <select aria-label={t("categories.preset")} className="input w-auto" value={row.formula_preset ?? ""} onChange={(e) => update(index, { formula_preset: e.target.value || null })}>
                    <option value="">{t("categories.presetDefault")}</option>
                    {(reference.data?.presets ?? []).filter((preset) => preset.category === row.kind).map((preset) => <option key={preset.id} value={preset.id}>{preset.label}</option>)}
                  </select>
                </td>
                <td className="px-2 py-1"><input aria-label={t("categories.runs")} type="number" min={1} max={20} className="input w-20" disabled={row.kind !== "aerial"} value={row.run_count ?? ""} onChange={(e) => update(index, { run_count: number(e.target.value) })} /></td>
                <td className="px-2 py-1"><input aria-label={t("categories.countedRuns")} type="number" min={1} max={20} className="input w-20" disabled={row.kind !== "aerial"} placeholder={t("categories.allRuns")} value={row.counted_runs ?? ""} onChange={(e) => update(index, { counted_runs: number(e.target.value) })} /></td>
                <td className="px-2 py-1 text-center"><input aria-label={t("categories.perCourse")} type="checkbox" className="h-4 w-4" checked={row.rank_per_bracket} onChange={(e) => update(index, { rank_per_bracket: e.target.checked })} /></td>
                <td className="px-2 py-1"><button type="button" className="btn-secondary px-2" aria-label={t("categories.remove")} onClick={() => setRows((prev) => prev.filter((_, i) => i !== index))}><Trash2 className="h-4 w-4" /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button type="button" className="btn-secondary text-sm" onClick={() => setRows((prev) => [...prev, { key: "", label_de: "", label_en: "", kind: "custom", formula_preset: null, run_count: null, counted_runs: null, rank_per_bracket: false }])}><Plus className="h-4 w-4" />{t("categories.add")}</button>
    </div>
  );
}

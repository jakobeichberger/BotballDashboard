import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import type { ChecklistItem, ChecklistPreset, DocMaxPoints, RuleSet, TiebreakerCriterion, TiebreakerPreset } from "./types";
import { apiErrorMessage } from "@/lib/errors";

const DOC_MAX_DEFAULT: DocMaxPoints = { p1: 100, p2: 100, p3: 100, onsite: 100 };
// The 2026 documentation rubrics: Period 1 /100, Period 2 /95, Period 3 /100, Onsite /100.
const DOC_MAX_2026: DocMaxPoints = { p1: 100, p2: 95, p3: 100, onsite: 100 };
const EMPTY: Omit<RuleSet, "season_id"> = { tiebreakers: [], finals_replay: false, end_contact_bonus_percent: 25, referee_checklist: [], seeding_tiebreakers: false, doc_max_points: DOC_MAX_DEFAULT };

/** Per-season tie-breaker order, finals replay rule, contact bonus and referee checklist. */
export default function SeasonRulesEditor({ seasonId, onMessage }: { seasonId: string; onMessage: (message: string) => void }) {
  const { t } = useTranslation("scoring");
  const queryClient = useQueryClient();
  const rules = useQuery<RuleSet>({ queryKey: ["scoring-rules", seasonId], queryFn: async () => (await api.get(`/scoring/seasons/${seasonId}/rules`)).data, enabled: !!seasonId });
  const presets = useQuery<TiebreakerPreset[]>({ queryKey: ["tiebreaker-presets"], queryFn: async () => (await api.get("/scoring/tiebreaker-presets")).data });
  const [draft, setDraft] = useState(EMPTY);
  const [presetId, setPresetId] = useState("");
  const checklistPresets = useQuery<ChecklistPreset[]>({ queryKey: ["checklist-presets"], queryFn: async () => (await api.get("/scoring/referee-checklist-presets")).data });
  const [checklistPresetId, setChecklistPresetId] = useState("");
  const docMax = draft.doc_max_points ?? DOC_MAX_DEFAULT;
  useEffect(() => { if (rules.data) setDraft({ ...EMPTY, ...rules.data }); }, [rules.data]);

  const save = useMutation({
    mutationFn: async () => api.put(`/scoring/seasons/${seasonId}/rules`, draft),
    onSuccess: () => { onMessage(t("rules.saved")); queryClient.invalidateQueries({ queryKey: ["scoring-rules", seasonId] }); },
    onError: (error: any) => onMessage(apiErrorMessage(error, t("rules.saveFailed"))),
  });
  const loadPreset = () => {
    const preset = presets.data?.find((item) => item.id === presetId);
    if (preset) setDraft({ ...draft, tiebreakers: preset.tiebreakers.map((c) => ({ ...c })), finals_replay: preset.finals_replay });
  };
  const setCriterion = (index: number, change: Partial<TiebreakerCriterion>) => setDraft({ ...draft, tiebreakers: draft.tiebreakers.map((c, i) => (i === index ? { ...c, ...change } : c)) });
  const move = (index: number, delta: number) => {
    const list = [...draft.tiebreakers];
    const target = index + delta;
    if (target < 0 || target >= list.length) return;
    [list[index], list[target]] = [list[target], list[index]];
    setDraft({ ...draft, tiebreakers: list });
  };
  const setItem = (index: number, change: Partial<ChecklistItem>) => setDraft({ ...draft, referee_checklist: draft.referee_checklist.map((item, i) => (i === index ? { ...item, ...change } : item)) });

  if (!seasonId) return null;
  return (
    <section className="card p-5 lg:col-span-2" aria-labelledby="season-rules-title">
      <h2 id="season-rules-title" className="mb-1 text-lg font-semibold">{t("rules.title")}</h2>
      <p className="mb-4 text-sm text-gray-500">{t("rules.hint")}</p>
      <div className="mb-4 flex flex-wrap items-end gap-2">
        <label className="text-sm font-medium">{t("rules.preset")}<select className="input mt-1 block" value={presetId} onChange={(e) => setPresetId(e.target.value)}><option value="">{t("rules.choosePreset")}</option>{presets.data?.map((preset) => <option key={preset.id} value={preset.id}>{preset.name}</option>)}</select></label>
        <button type="button" className="btn-secondary" disabled={!presetId} onClick={loadPreset}>{t("rules.apply")}</button>
      </div>
      <ol className="space-y-2">
        {draft.tiebreakers.map((criterion, index) => (
          <li key={index} className="grid items-center gap-2 rounded border p-2 text-sm dark:border-gray-700 md:grid-cols-[2rem_2fr_1fr_7rem_7rem_1.5fr_auto]">
            <span className="font-semibold">{index + 1}.</span>
            <input aria-label={t("rules.tiebreaker")} className="input" value={criterion.label} onChange={(e) => setCriterion(index, { label: e.target.value })} />
            <input aria-label={t("rules.tiebreakerKey")} className="input font-mono text-xs" value={criterion.key} onChange={(e) => setCriterion(index, { key: e.target.value })} />
            <select aria-label={t("rules.direction")} className="input" value={criterion.direction} onChange={(e) => setCriterion(index, { direction: e.target.value as TiebreakerCriterion["direction"] })}><option value="max">{t("rules.more")}</option><option value="min">{t("rules.less")}</option></select>
            <select aria-label={t("rules.source")} className="input" value={criterion.source} onChange={(e) => setCriterion(index, { source: e.target.value as TiebreakerCriterion["source"] })}><option value="entry">{t("rules.entry")}</option><option value="sheet">{t("rules.sheet")}</option></select>
            <input aria-label={t("rules.sheetFields")} className="input font-mono text-xs" disabled={criterion.source !== "sheet"} placeholder={t("rules.sheetFieldsPlaceholder")} value={criterion.sheet_keys.join(", ")} onChange={(e) => setCriterion(index, { sheet_keys: e.target.value.split(",").map((key) => key.trim()).filter(Boolean) })} />
            <div className="flex items-center gap-1">
              <label className="mr-1 flex items-center gap-1 text-xs" title={t("rules.replayOnlyHint")}><input type="checkbox" checked={criterion.replay_only} onChange={(e) => setCriterion(index, { replay_only: e.target.checked })} />{t("rules.replay")}</label>
              <button type="button" className="btn-secondary px-2" aria-label={t("rules.up")} disabled={index === 0} onClick={() => move(index, -1)}><ArrowUp className="h-4 w-4" /></button>
              <button type="button" className="btn-secondary px-2" aria-label={t("rules.down")} disabled={index === draft.tiebreakers.length - 1} onClick={() => move(index, 1)}><ArrowDown className="h-4 w-4" /></button>
              <button type="button" className="btn-secondary px-2" aria-label={t("rules.removeTiebreaker")} onClick={() => setDraft({ ...draft, tiebreakers: draft.tiebreakers.filter((_, i) => i !== index) })}><Trash2 className="h-4 w-4" /></button>
            </div>
          </li>
        ))}
      </ol>
      <button type="button" className="btn-secondary mt-2 text-sm" onClick={() => setDraft({ ...draft, tiebreakers: [...draft.tiebreakers, { key: `tiebreaker_${draft.tiebreakers.length + 1}`, label: t("rules.newTiebreaker"), direction: "max", source: "entry", sheet_keys: [], replay_only: false }] })}><Plus className="h-4 w-4" />{t("rules.tiebreaker")}</button>

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <label className="flex items-start gap-2 text-sm"><input className="mt-1" type="checkbox" checked={draft.finals_replay} onChange={(e) => setDraft({ ...draft, finals_replay: e.target.checked })} /><span><strong>{t("rules.finalsReplay")}</strong><br /><span className="text-gray-500">{t("rules.finalsReplayHint")}</span></span></label>
        <label className="text-sm font-medium">{t("rules.contactBonus")}<input type="number" min={0} max={100} className="input mt-1 w-32" value={draft.end_contact_bonus_percent} onChange={(e) => setDraft({ ...draft, end_contact_bonus_percent: Number(e.target.value) })} /></label>
        <label className="flex items-start gap-2 text-sm md:col-span-2"><input className="mt-1" type="checkbox" checked={!!draft.seeding_tiebreakers} onChange={(e) => setDraft({ ...draft, seeding_tiebreakers: e.target.checked })} /><span><strong>{t("rules.seedingTiebreakers")}</strong><br /><span className="text-gray-500">{t("rules.seedingTiebreakersHint")}</span></span></label>
      </div>

      <h3 className="mb-2 mt-5 font-semibold">{t("rules.docMax")}</h3>
      <p className="mb-2 text-sm text-gray-500">{t("rules.docMaxHint")}</p>
      <div className="flex flex-wrap items-end gap-2">
        {(["p1", "p2", "p3", "onsite"] as const).map((part) => (
          <label key={part} className="text-sm font-medium">{t(`rules.docMaxPart.${part}`)}<input type="number" min={1} max={1000} className="input mt-1 block w-24" value={docMax[part]} onChange={(e) => setDraft({ ...draft, doc_max_points: { ...docMax, [part]: Number(e.target.value) } })} /></label>
        ))}
        <button type="button" className="btn-secondary" onClick={() => setDraft({ ...draft, doc_max_points: { ...DOC_MAX_2026 } })}>{t("rules.docMax2026")}</button>
      </div>

      <h3 className="mb-2 mt-5 font-semibold">{t("rules.checklist")}</h3>
      <p className="mb-2 text-sm text-gray-500">{t("rules.checklistHint")}</p>
      <div className="mb-3 flex flex-wrap items-end gap-2">
        <label className="text-sm font-medium">{t("rules.checklistPreset")}<select className="input mt-1 block" value={checklistPresetId} onChange={(e) => setChecklistPresetId(e.target.value)}><option value="">{t("rules.choosePreset")}</option>{checklistPresets.data?.map((preset) => <option key={preset.id} value={preset.id}>{preset.name}</option>)}</select></label>
        <button type="button" className="btn-secondary" disabled={!checklistPresetId} onClick={() => { const preset = checklistPresets.data?.find((item) => item.id === checklistPresetId); if (preset) setDraft({ ...draft, referee_checklist: preset.items.map((item) => ({ ...item })) }); }}>{t("rules.applyChecklist")}</button>
      </div>
      <ul className="space-y-2">
        {draft.referee_checklist.map((item, index) => (
          <li key={index} className="grid items-center gap-2 sm:grid-cols-[2fr_1fr_auto_auto]">
            <input aria-label={t("rules.checkItem")} className="input" value={item.label} onChange={(e) => setItem(index, { label: e.target.value })} />
            <input aria-label={t("rules.checkItemKey")} className="input font-mono text-xs" value={item.key} onChange={(e) => setItem(index, { key: e.target.value })} />
            <label className="flex items-center gap-1 text-sm"><input type="checkbox" checked={item.required} onChange={(e) => setItem(index, { required: e.target.checked })} />{t("rules.required")}</label>
            <button type="button" className="btn-secondary px-2" aria-label={t("rules.removeCheckItem")} onClick={() => setDraft({ ...draft, referee_checklist: draft.referee_checklist.filter((_, i) => i !== index) })}><Trash2 className="h-4 w-4" /></button>
          </li>
        ))}
      </ul>
      <button type="button" className="btn-secondary mt-2 text-sm" onClick={() => setDraft({ ...draft, referee_checklist: [...draft.referee_checklist, { key: `check_${draft.referee_checklist.length + 1}`, label: t("rules.newCheckItem"), required: true }] })}><Plus className="h-4 w-4" />{t("rules.checkItem")}</button>
      <div><button type="button" className="btn-primary mt-4" disabled={save.isPending} onClick={() => save.mutate()}>{t("rules.save")}</button></div>
    </section>
  );
}

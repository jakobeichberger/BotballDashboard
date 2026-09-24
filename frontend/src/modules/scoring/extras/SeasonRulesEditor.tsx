import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import type { ChecklistItem, RuleSet, TiebreakerCriterion, TiebreakerPreset } from "./types";

const EMPTY: Omit<RuleSet, "season_id"> = { tiebreakers: [], finals_replay: false, end_contact_bonus_percent: 25, referee_checklist: [] };

/** Per-season tie-breaker order, finals replay rule, contact bonus and referee checklist. */
export default function SeasonRulesEditor({ seasonId, onMessage }: { seasonId: string; onMessage: (message: string) => void }) {
  const queryClient = useQueryClient();
  const rules = useQuery<RuleSet>({ queryKey: ["scoring-rules", seasonId], queryFn: async () => (await api.get(`/scoring/seasons/${seasonId}/rules`)).data, enabled: !!seasonId });
  const presets = useQuery<TiebreakerPreset[]>({ queryKey: ["tiebreaker-presets"], queryFn: async () => (await api.get("/scoring/tiebreaker-presets")).data });
  const [draft, setDraft] = useState(EMPTY);
  const [presetId, setPresetId] = useState("");
  useEffect(() => { if (rules.data) setDraft({ ...EMPTY, ...rules.data }); }, [rules.data]);

  const save = useMutation({
    mutationFn: async () => api.put(`/scoring/seasons/${seasonId}/rules`, draft),
    onSuccess: () => { onMessage("Wertungsregeln gespeichert."); queryClient.invalidateQueries({ queryKey: ["scoring-rules", seasonId] }); },
    onError: (error: any) => onMessage(typeof error.response?.data?.detail === "string" ? error.response.data.detail : "Regeln konnten nicht gespeichert werden (Schlüssel prüfen)."),
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
      <h2 id="season-rules-title" className="mb-1 text-lg font-semibold">Tie-Breaker & Sonderregeln (Saison)</h2>
      <p className="mb-4 text-sm text-gray-500">Reihenfolge wie im Game Review. „Score-Sheet“ liest den Wert aus den Sheet-Feldern (Summe beider Seiten), „Eingabe“ tragen Juroren pro Match ein. Gilt für Seeding-Gleichstände, DE-Matches und die DE-Platzierung.</p>
      <div className="mb-4 flex flex-wrap items-end gap-2">
        <label className="text-sm font-medium">Vorlage<select className="input mt-1 block" value={presetId} onChange={(e) => setPresetId(e.target.value)}><option value="">Game Review wählen</option>{presets.data?.map((preset) => <option key={preset.id} value={preset.id}>{preset.name}</option>)}</select></label>
        <button type="button" className="btn-secondary" disabled={!presetId} onClick={loadPreset}>Übernehmen</button>
      </div>
      <ol className="space-y-2">
        {draft.tiebreakers.map((criterion, index) => (
          <li key={index} className="grid items-center gap-2 rounded border p-2 text-sm dark:border-gray-700 md:grid-cols-[2rem_2fr_1fr_7rem_7rem_1.5fr_auto]">
            <span className="font-semibold">{index + 1}.</span>
            <input aria-label="Tie-Breaker" className="input" value={criterion.label} onChange={(e) => setCriterion(index, { label: e.target.value })} />
            <input aria-label="Tie-Breaker-Schlüssel" className="input font-mono text-xs" value={criterion.key} onChange={(e) => setCriterion(index, { key: e.target.value })} />
            <select aria-label="Richtung" className="input" value={criterion.direction} onChange={(e) => setCriterion(index, { direction: e.target.value as TiebreakerCriterion["direction"] })}><option value="max">mehr gewinnt</option><option value="min">weniger gewinnt</option></select>
            <select aria-label="Quelle" className="input" value={criterion.source} onChange={(e) => setCriterion(index, { source: e.target.value as TiebreakerCriterion["source"] })}><option value="entry">Eingabe</option><option value="sheet">Score-Sheet</option></select>
            <input aria-label="Sheet-Felder" className="input font-mono text-xs" disabled={criterion.source !== "sheet"} placeholder="feld_a, feld_b" value={criterion.sheet_keys.join(", ")} onChange={(e) => setCriterion(index, { sheet_keys: e.target.value.split(",").map((key) => key.trim()).filter(Boolean) })} />
            <div className="flex items-center gap-1">
              <label className="mr-1 flex items-center gap-1 text-xs" title="Nur nach einem Replay verwenden"><input type="checkbox" checked={criterion.replay_only} onChange={(e) => setCriterion(index, { replay_only: e.target.checked })} />Replay</label>
              <button type="button" className="btn-secondary px-2" aria-label="Nach oben" disabled={index === 0} onClick={() => move(index, -1)}><ArrowUp className="h-4 w-4" /></button>
              <button type="button" className="btn-secondary px-2" aria-label="Nach unten" disabled={index === draft.tiebreakers.length - 1} onClick={() => move(index, 1)}><ArrowDown className="h-4 w-4" /></button>
              <button type="button" className="btn-secondary px-2" aria-label="Tie-Breaker entfernen" onClick={() => setDraft({ ...draft, tiebreakers: draft.tiebreakers.filter((_, i) => i !== index) })}><Trash2 className="h-4 w-4" /></button>
            </div>
          </li>
        ))}
      </ol>
      <button type="button" className="btn-secondary mt-2 text-sm" onClick={() => setDraft({ ...draft, tiebreakers: [...draft.tiebreakers, { key: `tiebreaker_${draft.tiebreakers.length + 1}`, label: "Neuer Tie-Breaker", direction: "max", source: "entry", sheet_keys: [], replay_only: false }] })}><Plus className="h-4 w-4" />Tie-Breaker</button>

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <label className="flex items-start gap-2 text-sm"><input className="mt-1" type="checkbox" checked={draft.finals_replay} onChange={(e) => setDraft({ ...draft, finals_replay: e.target.checked })} /><span><strong>Finale wiederholen statt Tie-Breaker</strong><br /><span className="text-gray-500">2026: „In the finals … the match will be replayed until one team scores more points.“</span></span></label>
        <label className="text-sm font-medium">Bonus bei Kontakt am Spielende (% des Gegner-Scores)<input type="number" min={0} max={100} className="input mt-1 w-32" value={draft.end_contact_bonus_percent} onChange={(e) => setDraft({ ...draft, end_contact_bonus_percent: Number(e.target.value) })} /></label>
      </div>

      <h3 className="mb-2 mt-5 font-semibold">Schiedsrichter-Checkliste</h3>
      <p className="mb-2 text-sm text-gray-500">Wird vor dem Bestätigen eines Scores abgehakt und mit dem Match gespeichert.</p>
      <ul className="space-y-2">
        {draft.referee_checklist.map((item, index) => (
          <li key={index} className="grid items-center gap-2 sm:grid-cols-[2fr_1fr_auto_auto]">
            <input aria-label="Prüfpunkt" className="input" value={item.label} onChange={(e) => setItem(index, { label: e.target.value })} />
            <input aria-label="Prüfpunkt-Schlüssel" className="input font-mono text-xs" value={item.key} onChange={(e) => setItem(index, { key: e.target.value })} />
            <label className="flex items-center gap-1 text-sm"><input type="checkbox" checked={item.required} onChange={(e) => setItem(index, { required: e.target.checked })} />Pflicht</label>
            <button type="button" className="btn-secondary px-2" aria-label="Prüfpunkt entfernen" onClick={() => setDraft({ ...draft, referee_checklist: draft.referee_checklist.filter((_, i) => i !== index) })}><Trash2 className="h-4 w-4" /></button>
          </li>
        ))}
      </ul>
      <button type="button" className="btn-secondary mt-2 text-sm" onClick={() => setDraft({ ...draft, referee_checklist: [...draft.referee_checklist, { key: `check_${draft.referee_checklist.length + 1}`, label: "Neuer Prüfpunkt", required: true }] })}><Plus className="h-4 w-4" />Prüfpunkt</button>
      <div><button type="button" className="btn-primary mt-4" disabled={save.isPending} onClick={() => save.mutate()}>Regeln speichern</button></div>
    </section>
  );
}

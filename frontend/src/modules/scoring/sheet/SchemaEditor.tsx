import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Copy, Plus, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import type { ScoringSchema } from "@/api/types";
import type { CompetitionLevel, SchemaListEntry, SchemaTemplate } from "@/modules/scoring/extras/types";
import { definitionProblems } from "./definitionProblems";
import { fromFlatFields, inputFields, isEither, isStructured, type SectionMultiplier, type SheetDefinition, type SheetField, type SheetMultiplier, type SheetSection } from "./calculator";

type Mode = "structured" | "json";

const slug = (text: string) => text.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").replace(/^(\d)/, "k_$1") || "feld";

const emptyDefinition = (): SheetDefinition => ({ sides: [], sections: [{ key: "section_1", label: "Bereich 1", fields: [{ key: "pieces", label: "Spielteile", type: "count", multiplier: 1, min_value: 0, max_value: null, required: false }], multipliers: [] }] });

function toDefinition(schema: ScoringSchema | undefined): SheetDefinition {
  if (!schema) return emptyDefinition();
  if (isStructured(schema.definition)) return structuredClone(schema.definition);
  return schema.fields.length ? fromFlatFields(schema.fields.map((field) => ({ ...field }))) : emptyDefinition();
}

interface Props {
  eventId: string;
  schema?: ScoringSchema;
  onMessage: (message: string) => void;
}

export default function SchemaEditor({ eventId, schema, onMessage }: Props) {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<Mode>("structured");
  const [draft, setDraft] = useState<SheetDefinition>(() => toDefinition(schema));
  const [json, setJson] = useState("");
  const [levelId, setLevelId] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [cloneSource, setCloneSource] = useState("");
  const templates = useQuery<SchemaTemplate[]>({ queryKey: ["schema-templates"], queryFn: async () => (await api.get("/scoring/schema-templates")).data });
  const levels = useQuery<CompetitionLevel[]>({ queryKey: ["levels"], queryFn: async () => (await api.get("/seasons/competition-levels/all")).data });
  const cloneSources = useQuery<SchemaListEntry[]>({ queryKey: ["scoring-schemas"], queryFn: async () => (await api.get("/scoring/schemas")).data });

  useEffect(() => { setDraft(toDefinition(schema)); }, [schema]);
  const problems = useMemo(() => definitionProblems(draft), [draft]);
  const inputs = useMemo(() => (problems.length ? 0 : inputFields(draft).length), [draft, problems]);

  const invalidate = () => { queryClient.invalidateQueries({ queryKey: ["event-schema", eventId] }); queryClient.invalidateQueries({ queryKey: ["scoring-schemas"] }); };
  const errorText = (error: any) => (error instanceof SyntaxError ? "Schema-JSON ist ungültig." : typeof error.response?.data?.detail === "string" ? error.response.data.detail : "Schema konnte nicht gespeichert werden.");
  const save = useMutation({
    mutationFn: async () => {
      let body: Record<string, unknown>;
      if (mode === "json") {
        const parsed = JSON.parse(json);
        body = Array.isArray(parsed) ? { fields: parsed as SheetField[] } : { definition: parsed as SheetDefinition };
      } else {
        body = { definition: draft };
      }
      return api.post(`/v1/events/${eventId}/scoring-schema/versions`, { ...body, competition_level_id: levelId || null, activate: true });
    },
    onSuccess: () => { onMessage("Neue Scoring-Schema-Version wurde aktiviert."); invalidate(); },
    onError: (error: any) => onMessage(errorText(error)),
  });
  const clone = useMutation({
    mutationFn: async () => api.post(`/scoring/events/${eventId}/scoring-schema/clone`, { source_schema_id: cloneSource, competition_level_id: levelId || null, activate: true }),
    onSuccess: () => { onMessage("Schema wurde geklont und als neue Version aktiviert."); setCloneSource(""); invalidate(); },
    onError: (error: any) => onMessage(errorText(error)),
  });

  const switchMode = (next: Mode) => {
    if (next === mode) return;
    if (next === "json") { setJson(JSON.stringify(draft, null, 2)); setMode(next); return; }
    try {
      const parsed = JSON.parse(json);
      setDraft(Array.isArray(parsed) ? fromFlatFields(parsed) : isStructured(parsed) ? parsed : draft);
      setMode(next);
    } catch { onMessage("Schema-JSON ist ungültig."); }
  };
  const loadTemplate = () => {
    const template = templates.data?.find((item) => item.id === templateId);
    if (!template) return;
    setDraft(structuredClone(template.definition));
    setMode("structured");
    onMessage(template.complete ? `Vorlage „${template.name}“ geladen – prüfen und aktivieren.` : `Vorlage „${template.name}“ geladen. ${template.notes}`);
  };

  const updateSection = (index: number, change: Partial<SheetSection>) => setDraft((current) => ({ ...current, sections: current.sections.map((section, i) => (i === index ? { ...section, ...change } : section)) }));
  const moveSection = (index: number, delta: number) => setDraft((current) => {
    const sections = [...current.sections];
    const target = index + delta;
    if (target < 0 || target >= sections.length) return current;
    [sections[index], sections[target]] = [sections[target], sections[index]];
    return { ...current, sections };
  });
  const addSection = () => setDraft((current) => {
    const number = current.sections.length + 1;
    return { ...current, sections: [...current.sections, { key: `section_${number}`, label: `Bereich ${number}`, fields: [{ key: `section_${number}_pieces`, label: "Spielteile", type: "count", multiplier: 1, min_value: 0, max_value: null, required: false }], multipliers: [] }] };
  });

  return (
    <section className="card p-5 lg:col-span-2" aria-labelledby="schema-editor-title">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 id="schema-editor-title" className="text-lg font-semibold">Versioniertes Scoring-Schema</h2>
        <div className="inline-flex overflow-hidden rounded-lg border dark:border-gray-700" role="tablist">
          {(["structured", "json"] as Mode[]).map((item) => <button key={item} type="button" role="tab" aria-selected={mode === item} className={`px-3 py-1.5 text-sm ${mode === item ? "bg-primary-600 text-white" : ""}`} onClick={() => switchMode(item)}>{item === "structured" ? "Editor" : "JSON"}</button>)}
        </div>
      </div>
      <p className="mb-4 text-sm text-gray-500">Bereiche mit Feldern (Anzahl × Punkte) und Bereichs-Multiplikatoren wie auf dem Papier-Sheet. Speichern erzeugt eine neue aktive Version; bestehende Matches behalten ihren Snapshot. Aktuell: {schema ? `Version ${schema.version}${schema.definition ? " (strukturiert)" : " (flach)"}` : "kein Schema"}.</p>

      <div className="mb-4 grid gap-3 md:grid-cols-3">
        <label className="text-sm font-medium">Wettbewerbsstufe<select className="input mt-1 w-full" value={levelId} onChange={(e) => setLevelId(e.target.value)}><option value="">Standard (alle Stufen)</option>{levels.data?.map((level) => <option key={level.id} value={level.id}>{level.name}</option>)}</select></label>
        <div className="text-sm font-medium">Vorlage<div className="mt-1 flex gap-2"><select aria-label="Vorlage" className="input min-w-0 flex-1" value={templateId} onChange={(e) => setTemplateId(e.target.value)}><option value="">Vorlage wählen</option>{templates.data?.map((template) => <option key={template.id} value={template.id}>{template.name}{template.complete ? "" : " – unvollständig"}</option>)}</select><button type="button" className="btn-secondary" disabled={!templateId} onClick={loadTemplate}>Laden</button></div></div>
        <div className="text-sm font-medium">Klonen von<div className="mt-1 flex gap-2"><select aria-label="Schema zum Klonen" className="input min-w-0 flex-1" value={cloneSource} onChange={(e) => setCloneSource(e.target.value)}><option value="">Event/Stufe wählen</option>{cloneSources.data?.filter((item) => item.id !== schema?.id).map((item) => <option key={item.id} value={item.id}>{item.event_name ?? item.season_name} · {item.competition_level_name ?? "Standard"} · v{item.version}</option>)}</select><button type="button" className="btn-secondary" aria-label="Klonen" disabled={!cloneSource || clone.isPending} onClick={() => clone.mutate()}><Copy className="h-4 w-4" /></button></div></div>
      </div>

      {mode === "json" ? (
        <textarea aria-label="Schema-JSON" className="input min-h-64 w-full font-mono text-xs" value={json} onChange={(e) => setJson(e.target.value)} />
      ) : (
        <div className="space-y-4">
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.sides.length > 0} onChange={(e) => setDraft({ ...draft, sides: e.target.checked ? ["A", "B"] : [] })} />Getrennte Seiten A/B (Total = A + B)</label>
          {draft.sections.map((section, index) => (
            <SectionEditor key={index} section={section} index={index} count={draft.sections.length} onChange={(change) => updateSection(index, change)} onMove={(delta) => moveSection(index, delta)} onRemove={() => setDraft({ ...draft, sections: draft.sections.filter((_, i) => i !== index) })} />
          ))}
          <button type="button" className="btn-secondary" onClick={addSection}><Plus className="h-4 w-4" />Bereich</button>
          {problems.length > 0 && <ul role="alert" className="list-inside list-disc rounded-lg bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-900/30 dark:text-amber-100">{problems.map((problem) => <li key={problem}>{problem}</li>)}</ul>}
          {!problems.length && <p className="text-xs text-gray-500">{inputs} Eingabefelder{draft.sides.length ? " (beide Seiten)" : ""}.</p>}
        </div>
      )}
      <button type="button" className="btn-primary mt-4" disabled={save.isPending || (mode === "structured" && problems.length > 0)} onClick={() => save.mutate()}>Neue Version aktivieren</button>
    </section>
  );
}

interface SectionProps {
  section: SheetSection;
  index: number;
  count: number;
  onChange: (change: Partial<SheetSection>) => void;
  onMove: (delta: number) => void;
  onRemove: () => void;
}

function SectionEditor({ section, index, count, onChange, onMove, onRemove }: SectionProps) {
  const updateField = (i: number, change: Partial<SheetField>) => onChange({ fields: section.fields.map((field, j) => (j === i ? { ...field, ...change } : field)) });
  const updateMultiplier = (i: number, next: SectionMultiplier) => onChange({ multipliers: section.multipliers.map((m, j) => (j === i ? next : m)) });
  const newKey = (suffix: string) => `${section.key}_${suffix}`;
  return (
    <fieldset className="rounded-lg border p-3 dark:border-gray-700">
      <legend className="px-1 text-sm font-semibold">Bereich {index + 1}</legend>
      <div className="mb-3 grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
        <input aria-label="Bereichsname" className="input" value={section.label} onChange={(e) => onChange({ label: e.target.value })} placeholder="Name" />
        <input aria-label="Bereichs-Schlüssel" className="input font-mono text-xs" value={section.key} onChange={(e) => onChange({ key: e.target.value })} placeholder="schluessel" />
        <div className="flex gap-1">
          <button type="button" className="btn-secondary px-2" aria-label="Nach oben" disabled={index === 0} onClick={() => onMove(-1)}><ArrowUp className="h-4 w-4" /></button>
          <button type="button" className="btn-secondary px-2" aria-label="Nach unten" disabled={index === count - 1} onClick={() => onMove(1)}><ArrowDown className="h-4 w-4" /></button>
          <button type="button" className="btn-danger px-2" aria-label="Bereich entfernen" onClick={onRemove}><Trash2 className="h-4 w-4" /></button>
        </div>
      </div>
      <p className="mb-1 text-xs font-medium uppercase text-gray-500">Felder (Wert × Punkte)</p>
      <div className="space-y-2">
        {section.fields.map((field, i) => (
          <div key={i} className="grid gap-2 sm:grid-cols-[1.4fr_1fr_7rem_5rem_5rem_auto]">
            <input aria-label="Feldname" className="input" value={field.label} onChange={(e) => updateField(i, { label: e.target.value })} onBlur={() => !field.key && updateField(i, { key: newKey(slug(field.label)) })} />
            <input aria-label="Feld-Schlüssel" className="input font-mono text-xs" value={field.key} onChange={(e) => updateField(i, { key: e.target.value })} />
            <select aria-label="Feldtyp" className="input" value={field.type ?? "count"} onChange={(e) => updateField(i, { type: e.target.value as SheetField["type"] })}><option value="count">Anzahl</option><option value="boolean">Ja/Nein</option><option value="number">Zahl</option></select>
            <input aria-label="Punkte je Stück" title="Punkte je Stück" type="number" step="any" className="input" value={field.multiplier ?? 1} onChange={(e) => updateField(i, { multiplier: Number(e.target.value) })} />
            <input aria-label="Maximum" title="Maximum" type="number" min={0} className="input" value={field.max_value ?? ""} placeholder="max" onChange={(e) => updateField(i, { max_value: e.target.value === "" ? null : Number(e.target.value) })} />
            <button type="button" className="btn-secondary px-2" aria-label="Feld entfernen" onClick={() => onChange({ fields: section.fields.filter((_, j) => j !== i) })}><Trash2 className="h-4 w-4" /></button>
          </div>
        ))}
        <button type="button" className="btn-secondary text-xs" onClick={() => onChange({ fields: [...section.fields, { key: newKey(`field_${section.fields.length + 1}`), label: "Neues Feld", type: "count", multiplier: 1, min_value: 0, max_value: null, required: false }] })}><Plus className="h-3 w-3" />Feld</button>
      </div>
      <p className="mb-1 mt-3 text-xs font-medium uppercase text-gray-500">Bereichs-Multiplikatoren (auf die Zwischensumme)</p>
      <div className="space-y-2">
        {section.multipliers.map((multiplier, i) => (
          <div key={i} className="rounded border border-dashed p-2 dark:border-gray-700">
            {isEither(multiplier) ? (
              <div className="space-y-2">
                <div className="grid gap-2 sm:grid-cols-[1.4fr_1fr_auto]">
                  <input aria-label="Name der Entweder-oder-Gruppe" className="input" value={multiplier.label} onChange={(e) => updateMultiplier(i, { ...multiplier, label: e.target.value })} />
                  <input aria-label="Gruppen-Schlüssel" className="input font-mono text-xs" value={multiplier.key} onChange={(e) => updateMultiplier(i, { ...multiplier, key: e.target.value })} />
                  <button type="button" className="btn-secondary px-2" aria-label="Gruppe entfernen" onClick={() => onChange({ multipliers: section.multipliers.filter((_, j) => j !== i) })}><Trash2 className="h-4 w-4" /></button>
                </div>
                <p className="text-xs text-gray-500">Entweder-oder: es zählt die Alternative mit dem höchsten Faktor.</p>
                {multiplier.either.map((option, k) => (
                  <MultiplierRow key={k} value={option} onChange={(next) => updateMultiplier(i, { ...multiplier, either: multiplier.either.map((o, j) => (j === k ? next : o)) })} onRemove={() => updateMultiplier(i, { ...multiplier, either: multiplier.either.filter((_, j) => j !== k) })} />
                ))}
                <button type="button" className="btn-secondary text-xs" onClick={() => updateMultiplier(i, { ...multiplier, either: [...multiplier.either, { key: newKey(`option_${multiplier.either.length + 1}`), label: "Alternative", type: "count", factor: 1, offset: 0, max_value: null }] })}><Plus className="h-3 w-3" />Alternative</button>
              </div>
            ) : (
              <MultiplierRow value={multiplier} onChange={(next) => updateMultiplier(i, next)} onRemove={() => onChange({ multipliers: section.multipliers.filter((_, j) => j !== i) })} />
            )}
          </div>
        ))}
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn-secondary text-xs" onClick={() => onChange({ multipliers: [...section.multipliers, { key: newKey(`multiplier_${section.multipliers.length + 1}`), label: "Bonus", type: "boolean", factor: 2, max_value: 1 }] })}><Plus className="h-3 w-3" />Multiplikator</button>
          <button type="button" className="btn-secondary text-xs" onClick={() => onChange({ multipliers: [...section.multipliers, { key: newKey(`either_${section.multipliers.length + 1}`), label: "Entweder-oder", either: [{ key: newKey(`either_${section.multipliers.length + 1}_a`), label: "Alternative A", type: "count", factor: 1, offset: 0, max_value: null }, { key: newKey(`either_${section.multipliers.length + 1}_b`), label: "Alternative B", type: "count", factor: 2, offset: 0, max_value: null }] }] })}><Plus className="h-3 w-3" />Entweder-oder</button>
        </div>
      </div>
    </fieldset>
  );
}

function MultiplierRow({ value, onChange, onRemove }: { value: SheetMultiplier; onChange: (next: SheetMultiplier) => void; onRemove: () => void }) {
  const counted = (value.type ?? "boolean") !== "boolean";
  return (
    <div className="grid gap-2 sm:grid-cols-[1.4fr_1fr_8rem_4.5rem_4.5rem_4.5rem_auto]">
      <input aria-label="Multiplikator-Name" className="input" value={value.label} onChange={(e) => onChange({ ...value, label: e.target.value })} />
      <input aria-label="Multiplikator-Schlüssel" className="input font-mono text-xs" value={value.key} onChange={(e) => onChange({ ...value, key: e.target.value })} />
      <select aria-label="Multiplikator-Art" className="input" value={value.type ?? "boolean"} onChange={(e) => onChange({ ...value, type: e.target.value as SheetMultiplier["type"], max_value: e.target.value === "boolean" ? 1 : value.max_value ?? null })}><option value="boolean">Häkchen × Faktor</option><option value="count">Anzahl × Faktor</option></select>
      <input aria-label="Faktor" title="Faktor" type="number" step="any" className="input" value={value.factor ?? 1} onChange={(e) => onChange({ ...value, factor: Number(e.target.value) })} />
      <input aria-label="Offset" title="Offset (+n)" type="number" step="any" className="input" disabled={!counted} value={counted ? value.offset ?? 0 : ""} onChange={(e) => onChange({ ...value, offset: Number(e.target.value) })} />
      <input aria-label="Multiplikator-Maximum" title="Maximum" type="number" min={0} className="input" disabled={!counted} value={counted ? value.max_value ?? "" : ""} placeholder="max" onChange={(e) => onChange({ ...value, max_value: e.target.value === "" ? null : Number(e.target.value) })} />
      <button type="button" className="btn-secondary px-2" aria-label="Multiplikator entfernen" onClick={onRemove}><Trash2 className="h-4 w-4" /></button>
    </div>
  );
}

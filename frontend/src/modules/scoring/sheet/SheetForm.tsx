import { useId, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { Minus, Plus } from "lucide-react";
import { computeSheet, isDerived, isEither, rawKey, type RawScores, type SheetDefinition, type SheetField, type SheetMultiplier, type SheetResult } from "./calculator";
import { sheetMessages } from "./issues";

interface Props {
  definition: SheetDefinition;
  values: RawScores;
  /** null: the field was cleared (the key is dropped from the raw scores). */
  onChange: (key: string, value: number | boolean | null) => void;
  disabled?: boolean;
}

/**
 * Entry form laid out like the paper sheet: one tab per side, sections with
 * their itemised fields, the area multipliers below, and the live section
 * breakdown (subtotal × multiplier = total) from the shared calculator.
 */
export default function SheetForm({ definition, values, onChange, disabled }: Props) {
  const { t } = useTranslation("scoring");
  const sides: (string | null)[] = definition.sides.length ? definition.sides : [null];
  const [activeSide, setActiveSide] = useState<string | null>(sides[0]);
  const result: SheetResult = useMemo(() => computeSheet(values, definition), [values, definition]);
  const sideResult = result.sides.find((item) => item.side === activeSide) ?? result.sides[0];
  const side = sides.includes(activeSide) ? activeSide : sides[0];

  return (
    <div className="space-y-4">
      {definition.sides.length > 0 && (
        <div className="flex flex-wrap items-center gap-2" role="tablist" aria-label={t("sheet.side")}>
          {definition.sides.map((item) => {
            const total = result.sides.find((s) => s.side === item)?.total ?? 0;
            return <button key={item} type="button" role="tab" aria-selected={side === item} className={side === item ? "btn-primary" : "btn-secondary"} onClick={() => setActiveSide(item)}>{t("sheet.sideTotal", { side: item, total })}</button>;
          })}
          <span className="text-sm text-leise">{t("sheet.total", { sides: definition.sides.join(" + ") })} <strong>{result.total}</strong></span>
        </div>
      )}
      {definition.sections.map((section, index) => {
        const breakdown = sideResult?.sections[index];
        return (
          <fieldset disabled={disabled} key={section.key} className="card p-4">
            <legend className="px-2 font-semibold">{section.label || section.key}</legend>
            <div className="grid gap-4 sm:grid-cols-2">
              {section.fields.map((field) => <Input key={field.key} spec={field} rawKey={rawKey(side, field.key)} hint={`× ${field.multiplier ?? 1}`} values={values} onChange={onChange} />)}
            </div>
            {section.multipliers.length > 0 && (
              <div className="mt-3 grid gap-3 border-t pt-3 sm:grid-cols-2">
                {section.multipliers.map((multiplier) => isEither(multiplier) ? (
                  <div key={multiplier.key} className="rounded border border-dashed p-2 sm:col-span-2">
                    <p className="mb-2 text-xs font-medium text-leise">{t("sheet.eitherHint", { name: multiplier.label })}</p>
                    <div className="grid gap-3 sm:grid-cols-2">{multiplier.either.map((option) => <Input key={option.key} spec={option} rawKey={rawKey(side, option.key)} hint={multiplierHint(option, t)} values={values} onChange={onChange} />)}</div>
                  </div>
                ) : isDerived(multiplier) ? (
                  <p key={multiplier.key} className="text-sm text-leise">
                    {multiplier.label} <span className="text-xs">{t("sheet.derivedHint", { field: section.fields.find((f) => f.key === multiplier.source)?.label ?? multiplier.source })}</span>
                  </p>
                ) : <Input key={multiplier.key} spec={multiplier} rawKey={rawKey(side, multiplier.key)} hint={multiplierHint(multiplier, t)} values={values} onChange={onChange} />)}
              </div>
            )}
            {breakdown && <p className="mt-3 text-right text-sm text-leise" aria-live="polite">{breakdown.subtotal}{breakdown.multiplier !== 1 ? ` × ${breakdown.multiplier}` : ""} = <strong className="text-fg">{breakdown.total}</strong></p>}
          </fieldset>
        );
      })}
      {result.errors.length > 0 && <ul role="alert" className="list-inside list-disc rounded-lg bg-danger/[0.07] p-3 text-sm text-danger">{sheetMessages(result, t).map((message) => <li key={message}>{message}</li>)}</ul>}
    </div>
  );
}

function multiplierHint(spec: SheetMultiplier, t: TFunction): string {
  const area = t("scoring:sheet.area");
  if ((spec.type ?? "boolean") === "boolean") return `${area} × ${spec.factor ?? 1}`;
  const factor = spec.factor ?? 1;
  const offset = spec.offset ?? 0;
  return `${area} × (n${factor !== 1 ? ` × ${factor}` : ""}${offset ? ` + ${offset}` : ""})`;
}

function Input({ spec, rawKey: key, hint, values, onChange }: { spec: SheetField | SheetMultiplier; rawKey: string; hint: string; values: RawScores; onChange: Props["onChange"] }) {
  const { t } = useTranslation("scoring");
  const id = useId();
  const type = spec.type ?? ("factor" in spec ? "boolean" : "count");
  const value = values[key];
  if (type === "boolean") {
    // The whole row is the tap target (≥ 44 px), not just the 24 px box.
    return (
      <label className="flex min-h-11 cursor-pointer items-center gap-3 text-sm font-medium">
        <input className="h-6 w-6 shrink-0" type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(key, event.target.checked)} />
        <span>{spec.label} <span className="text-xs text-leise">{hint}</span></span>
      </label>
    );
  }
  const min = spec.min_value ?? 0;
  const max = spec.max_value ?? undefined;
  const current = typeof value === "number" ? value : Number(value ?? 0) || 0;
  const input = (
    <input id={id} className="input w-full text-lg" type="number" inputMode={type === "count" ? "numeric" : "decimal"} min={min} max={max} value={value === undefined || value === null || typeof value === "boolean" ? "" : String(value)}
           onChange={(event) => onChange(key, event.target.value === "" ? null : Number(event.target.value))} />
  );
  return (
    <div className="text-sm font-medium">
      <label htmlFor={id}>{spec.label} <span className="text-xs text-leise">{hint}</span></label>
      {type === "count" ? (
        // Thumb-sized steppers for counting at the table; typing still works.
        <span className="mt-1 flex items-center gap-2">
          <button type="button" className="btn-secondary h-11 w-11 shrink-0 justify-center p-0" aria-label={t("sheet.decrease", { label: spec.label })} disabled={current <= min} onClick={() => onChange(key, Math.max(min, current - 1))}><Minus className="h-5 w-5" aria-hidden="true" /></button>
          {input}
          <button type="button" className="btn-secondary h-11 w-11 shrink-0 justify-center p-0" aria-label={t("sheet.increase", { label: spec.label })} disabled={max !== undefined && current >= max} onClick={() => onChange(key, max !== undefined ? Math.min(max, current + 1) : current + 1)}><Plus className="h-5 w-5" aria-hidden="true" /></button>
        </span>
      ) : <span className="mt-1 block">{input}</span>}
    </div>
  );
}

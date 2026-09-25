import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { computeSheet, isEither, rawKey, type RawScores, type SheetDefinition, type SheetField, type SheetMultiplier, type SheetResult } from "./calculator";

interface Props {
  definition: SheetDefinition;
  values: RawScores;
  onChange: (key: string, value: number | boolean) => void;
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
          <span className="text-sm text-gray-500">{t("sheet.total", { sides: definition.sides.join(" + ") })} <strong>{result.total}</strong></span>
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
              <div className="mt-3 grid gap-3 border-t pt-3 dark:border-gray-800 sm:grid-cols-2">
                {section.multipliers.map((multiplier) => isEither(multiplier) ? (
                  <div key={multiplier.key} className="rounded border border-dashed p-2 dark:border-gray-700 sm:col-span-2">
                    <p className="mb-2 text-xs font-medium text-gray-500">{t("sheet.eitherHint", { name: multiplier.label })}</p>
                    <div className="grid gap-3 sm:grid-cols-2">{multiplier.either.map((option) => <Input key={option.key} spec={option} rawKey={rawKey(side, option.key)} hint={multiplierHint(option, t)} values={values} onChange={onChange} />)}</div>
                  </div>
                ) : <Input key={multiplier.key} spec={multiplier} rawKey={rawKey(side, multiplier.key)} hint={multiplierHint(multiplier, t)} values={values} onChange={onChange} />)}
              </div>
            )}
            {breakdown && <p className="mt-3 text-right text-sm text-gray-500" aria-live="polite">{breakdown.subtotal}{breakdown.multiplier !== 1 ? ` × ${breakdown.multiplier}` : ""} = <strong className="text-gray-900 dark:text-white">{breakdown.total}</strong></p>}
          </fieldset>
        );
      })}
      {result.errors.length > 0 && <ul role="alert" className="list-inside list-disc rounded-lg bg-red-50 p-3 text-sm text-red-800 dark:bg-red-900/30 dark:text-red-100">{result.errors.map((error) => <li key={error}>{error}</li>)}</ul>}
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
  const isBoolean = (spec.type ?? ("factor" in spec ? "boolean" : "count")) === "boolean";
  const value = values[key];
  return (
    <label className="text-sm font-medium">
      {spec.label} <span className="text-xs text-gray-500">{hint}</span>
      {isBoolean ? (
        <input className="ml-3 h-5 w-5 align-middle" type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(key, event.target.checked)} />
      ) : (
        <input className="input mt-1 w-full text-lg" type="number" inputMode="decimal" min={spec.min_value ?? 0} max={spec.max_value ?? undefined} value={value === undefined || value === null || typeof value === "boolean" ? "" : String(value)} onChange={(event) => onChange(key, Number(event.target.value))} />
      )}
    </label>
  );
}

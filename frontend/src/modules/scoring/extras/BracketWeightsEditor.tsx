import { useEffect, useState, type ReactNode } from "react";
import { Trans, useTranslation } from "react-i18next";
import { Plus, Save, Trash2 } from "lucide-react";

/** Parses the editor rows; empty labels and non-numeric weights are dropped. */
function weightsFromRows(rows: [string, string][]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [bracket, value] of rows) {
    const key = bracket.trim();
    const num = Number(value);
    if (key && value.trim() !== "" && Number.isFinite(num)) out[key] = num;
  }
  return out;
}

/**
 * Bracket weights (bracket label → factor), used by the season formulas as
 * `bracket_weight`. Shared by the season formula editor and the per-event
 * override in the event setup.
 */
export default function BracketWeightsEditor({
  weights,
  onSave,
  saving,
  title,
  hint,
  actions,
  disabled = false,
}: {
  weights: Record<string, number>;
  onSave: (weights: Record<string, number>) => void;
  saving: boolean;
  title?: string;
  hint?: ReactNode;
  /** Extra buttons next to "save" (e.g. reset to the season weights). */
  actions?: ReactNode;
  disabled?: boolean;
}) {
  const { t } = useTranslation("scoring");
  const [draft, setDraft] = useState<[string, string][]>([]);

  // Keyed on the content: callers often pass a fresh `{}` while loading, which
  // must not wipe what the user is typing.
  const weightsKey = JSON.stringify(weights);
  useEffect(() => {
    const entries = Object.entries(JSON.parse(weightsKey) as Record<string, number>);
    setDraft(entries.length > 0 ? entries.map(([k, v]) => [k, String(v)]) : [["A", "1"]]);
  }, [weightsKey]);

  return (
    <div className="card p-4 space-y-3">
      <div>
        <h2 className="font-medium">{title ?? t("formulas.bracketWeights")}</h2>
        <p className="text-xs text-gray-500">
          {hint ?? <Trans t={t} i18nKey="formulas.bracketWeightsHint" components={{ code: <code className="font-mono" /> }} />}
        </p>
      </div>
      <div className="space-y-2">
        {draft.map(([bracket, value], i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              className="input font-mono max-w-[6rem]"
              placeholder="A"
              aria-label={t("formulas.bracketLabel", { index: i + 1 })}
              disabled={disabled}
              value={bracket}
              onChange={(e) =>
                setDraft((p) => p.map((row, idx) => (idx === i ? [e.target.value, row[1]] : row)))
              }
            />
            <span className="text-gray-400">×</span>
            <input
              className="input font-mono max-w-[12rem]"
              placeholder="1.0"
              aria-label={t("formulas.bracketWeight", { index: i + 1 })}
              disabled={disabled}
              value={value}
              onChange={(e) =>
                setDraft((p) => p.map((row, idx) => (idx === i ? [row[0], e.target.value] : row)))
              }
            />
            <button
              type="button"
              className="btn-danger px-2"
              title={t("formulas.remove")}
              aria-label={t("formulas.remove")}
              disabled={disabled}
              onClick={() => setDraft((p) => p.filter((_, idx) => idx !== i))}
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn-secondary" disabled={disabled} onClick={() => setDraft((p) => [...p, ["", "1"]])}>
          <Plus className="w-4 h-4" />
          {t("de.bracket")}
        </button>
        <button type="button" className="btn-primary" onClick={() => onSave(weightsFromRows(draft))} disabled={disabled || saving}>
          <Save className="w-4 h-4" />
          {t("formulas.saveWeights")}
        </button>
        {actions}
      </div>
    </div>
  );
}

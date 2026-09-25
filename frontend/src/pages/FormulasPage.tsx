import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { Trans, useTranslation } from "react-i18next";
import { CATEGORY_LABEL } from "@/lib/teams";
import { api } from "@/lib/api";
import {
  Calculator,
  Plus,
  Trash2,
  Save,
  RotateCcw,
  AlertTriangle,
  CheckCircle2,
  ArrowUp,
  ArrowDown,
} from "lucide-react";

const CATEGORIES = [
  { key: "botball", label: "Botball" },
  { key: "open", label: "PRIA Open" },
  { key: "aerial", label: "Aerial" },
  { key: "jbc", label: "JBC" },
] as const;

type Category = (typeof CATEGORIES)[number]["key"];

interface Formula {
  key: string;
  expression: string;
  label?: string | null;
}

interface FunctionDoc {
  name: string;
  signature: string;
  description: string;
}

interface FormulaPreset {
  id: string;
  label: string;
  category: string;
  description: string;
  formulas: { key: string; expression: string }[];
}

interface Reference {
  inputs: Record<string, string>;
  row_functions: FunctionDoc[];
  scope_functions: FunctionDoc[];
  defaults: Record<string, { key: string; expression: string }[]>;
  presets?: FormulaPreset[];
}

interface PreviewIssue {
  key: string;
  team_id: string | null;
  message: string;
}

interface PreviewRow {
  team_id: string;
  team_name: string | null;
  rank: number | null;
  values: Record<string, number>;
}

interface PreviewResponse {
  ok: boolean;
  order: string[];
  issues: PreviewIssue[];
  rows: PreviewRow[];
}

function formatValue(v: number): string {
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
}

export default function FormulasPage() {
  const { t } = useTranslation("scoring");
  const { eventId = "" } = useParams();
  const queryClient = useQueryClient();
  const [category, setCategory] = useState<Category>("botball");
  const [formulas, setFormulas] = useState<Formula[]>([]);
  const [dirty, setDirty] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Formulas are stored per season (that is how the game document is
  // published); results are per event, so the preview needs the event.
  const { data: event } = useQuery<{ id: string; season_id: string; name: string }>({
    queryKey: ["event", eventId],
    queryFn: async () => (await api.get(`/v1/events/${eventId}`)).data,
    enabled: !!eventId,
  });
  const seasonId = event?.season_id ?? "";

  const { data: reference } = useQuery<Reference>({
    queryKey: ["formula-reference"],
    queryFn: async () => {
      const { data } = await api.get("/scoring/formulas/reference");
      return data;
    },
  });

  const { data: effective, isLoading } = useQuery<Formula[]>({
    queryKey: ["formulas", seasonId, category],
    queryFn: async () => {
      const { data } = await api.get(
        `/scoring/formulas/seasons/${seasonId}/${category}/effective`,
      );
      return data;
    },
    enabled: !!seasonId,
  });

  // Reload the editor whenever the season or category changes.
  useEffect(() => {
    if (effective) {
      setFormulas(effective.map((f) => ({ key: f.key, expression: f.expression })));
      setDirty(false);
      setSaveError(null);
    }
  }, [effective]);

  const { data: bracketWeights } = useQuery<Record<string, number>>({
    queryKey: ["bracket-weights", seasonId, category],
    queryFn: async () => {
      const { data } = await api.get(
        `/scoring/formulas/seasons/${seasonId}/${category}/bracket-weights`,
      );
      return data;
    },
    enabled: !!seasonId,
  });

  // ── Live preview (debounced) ───────────────────────────────────────────────

  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const payload = useMemo(() => JSON.stringify(formulas), [formulas]);

  useEffect(() => {
    if (!eventId || formulas.length === 0) {
      setPreview(null);
      return;
    }
    let cancelled = false;
    setPreviewing(true);
    const timer = setTimeout(async () => {
      try {
        const { data } = await api.post<PreviewResponse>(
          `/scoring/formulas/events/${eventId}/${category}/preview`,
          { formulas },
        );
        if (!cancelled) setPreview(data);
      } catch {
        if (!cancelled) setPreview(null);
      } finally {
        if (!cancelled) setPreviewing(false);
      }
    }, 400);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [payload, eventId, category]);

  // ── Mutations ──────────────────────────────────────────────────────────────

  const saveMutation = useMutation({
    mutationFn: async () => {
      await api.put(`/scoring/formulas/seasons/${seasonId}/${category}`, {
        formulas: formulas.map((f, i) => ({ ...f, sort_order: i })),
      });
    },
    onSuccess: () => {
      setDirty(false);
      setSaveError(null);
      queryClient.invalidateQueries({ queryKey: ["formulas", seasonId, category] });
    },
    onError: (err: any) => {
      setSaveError(err?.response?.data?.detail ?? t("formulas.saveFailed"));
    },
  });

  const resetMutation = useMutation({
    mutationFn: async () => {
      await api.post(`/scoring/formulas/seasons/${seasonId}/${category}/reset`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["formulas", seasonId, category] });
    },
  });

  const weightsMutation = useMutation({
    mutationFn: async (weights: Record<string, number>) => {
      await api.put(`/scoring/formulas/seasons/${seasonId}/${category}/bracket-weights`, {
        weights,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bracket-weights", seasonId, category] });
    },
  });

  // ── Editing helpers ────────────────────────────────────────────────────────

  const update = (i: number, patch: Partial<Formula>) => {
    setFormulas((prev) => prev.map((f, idx) => (idx === i ? { ...f, ...patch } : f)));
    setDirty(true);
  };
  const remove = (i: number) => {
    setFormulas((prev) => prev.filter((_, idx) => idx !== i));
    setDirty(true);
  };
  const move = (i: number, delta: number) => {
    setFormulas((prev) => {
      const next = [...prev];
      const j = i + delta;
      if (j < 0 || j >= next.length) return prev;
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
    setDirty(true);
  };
  const add = () => {
    setFormulas((prev) => [...prev, { key: "", expression: "" }]);
    setDirty(true);
  };

  // Presets (ECER, regional, GCER, …) are loaded into the editor as a draft,
  // so they can be reviewed against the live preview before saving.
  const presets = (reference?.presets ?? []).filter((p) => p.category === category);
  const [presetId, setPresetId] = useState("");
  const loadPreset = (id: string) => {
    const preset = presets.find((p) => p.id === id);
    if (!preset) return;
    setFormulas(preset.formulas.map((f) => ({ key: f.key, expression: f.expression })));
    setDirty(true);
    setPresetId("");
  };

  const issuesByKey = useMemo(() => {
    const map: Record<string, PreviewIssue[]> = {};
    for (const issue of preview?.issues ?? []) {
      (map[issue.key] ??= []).push(issue);
    }
    return map;
  }, [preview]);

  const columns = preview?.order ?? [];

  if (!seasonId) {
    return (
      <div className="card p-6">
        <p className="text-gray-600 dark:text-gray-300">{t("events:loading")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Calculator className="w-6 h-6 text-primary-600" />
          <div>
            <h1 className="text-xl font-semibold">{t("formulas.title")}</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {t("formulas.subtitle")}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {presets.length > 0 && (
            <select
              className="input"
              aria-label={t("formulas.loadPreset")}
              value={presetId}
              onChange={(e) => loadPreset(e.target.value)}
            >
              <option value="">{t("formulas.loadPresetOption")}</option>
              {presets.map((p) => (
                <option key={p.id} value={p.id} title={p.description}>
                  {p.label}
                </option>
              ))}
            </select>
          )}
          <button
            className="btn-secondary"
            onClick={() => resetMutation.mutate()}
            disabled={resetMutation.isPending}
          >
            <RotateCcw className="w-4 h-4" />
            {t("formulas.reset")}
          </button>
          <button
            className="btn-primary"
            onClick={() => saveMutation.mutate()}
            disabled={!dirty || saveMutation.isPending}
          >
            <Save className="w-4 h-4" />
            {t("common:save")}
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {CATEGORIES.map((c) => (
          <button
            key={c.key}
            onClick={() => setCategory(c.key)}
            className={
              category === c.key
                ? "btn-primary"
                : "btn-secondary"
            }
          >
            {c.key === "open" ? c.label : CATEGORY_LABEL[c.key]}
          </button>
        ))}
      </div>

      {saveError && (
        <div className="card p-4 border-red-300 dark:border-red-800 bg-red-50 dark:bg-red-900/20">
          <div className="flex items-start gap-2 text-red-700 dark:text-red-300">
            <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
            <span className="text-sm">{saveError}</span>
          </div>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* ── Editor ───────────────────────────────────────────────────────── */}
        <div className="lg:col-span-2 space-y-4">
          <div className="card p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="font-medium">{t("formulas.formulas")}</h2>
              <button className="btn-secondary" onClick={add}>
                <Plus className="w-4 h-4" />
                {t("formulas.formula")}
              </button>
            </div>

            {isLoading && <p className="text-sm text-gray-500">{t("common:loading")}</p>}

            {formulas.map((f, i) => {
              const issues = issuesByKey[f.key] ?? [];
              return (
                <div
                  key={i}
                  className="rounded-lg border border-gray-200 dark:border-gray-700 p-3 space-y-2"
                >
                  <div className="flex items-center gap-2">
                    <input
                      className="input font-mono max-w-[16rem]"
                      placeholder={t("schema.keyPlaceholder")}
                      value={f.key}
                      onChange={(e) => update(i, { key: e.target.value })}
                    />
                    <span className="text-gray-400">=</span>
                    <div className="flex-1" />
                    <button
                      className="btn-secondary px-2"
                      title={t("rules.up")}
                      onClick={() => move(i, -1)}
                    >
                      <ArrowUp className="w-4 h-4" />
                    </button>
                    <button
                      className="btn-secondary px-2"
                      title={t("rules.down")}
                      onClick={() => move(i, 1)}
                    >
                      <ArrowDown className="w-4 h-4" />
                    </button>
                    <button
                      className="btn-danger px-2"
                      title={t("formulas.remove")}
                      onClick={() => remove(i)}
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                  <textarea
                    className="input font-mono text-sm"
                    rows={2}
                    spellCheck={false}
                    placeholder="3/4 * ((n - rank(seed_total) + 1) / n) + 1/4 * ..."
                    value={f.expression}
                    onChange={(e) => update(i, { expression: e.target.value })}
                  />
                  {issues.length > 0 && (
                    <div className="text-sm text-red-600 dark:text-red-400 space-y-0.5">
                      {issues.slice(0, 3).map((issue, k) => (
                        <div key={k} className="flex items-start gap-1.5">
                          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                          <span>
                            {issue.team_id ? `${issue.team_id}: ` : ""}
                            {issue.message}
                          </span>
                        </div>
                      ))}
                      {issues.length > 3 && (
                        <div className="text-xs">{t("formulas.more", { count: issues.length - 3 })}</div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* ── Bracket weights ────────────────────────────────────────────── */}
          <BracketWeightsCard
            weights={bracketWeights ?? {}}
            onSave={(w) => weightsMutation.mutate(w)}
            saving={weightsMutation.isPending}
          />

          {/* ── Preview ────────────────────────────────────────────────────── */}
          <div className="card p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="font-medium">{t("formulas.preview")}</h2>
              {previewing ? (
                <span className="text-sm text-gray-500">{t("formulas.calculating")}</span>
              ) : preview?.ok ? (
                <span className="flex items-center gap-1.5 text-sm text-green-600 dark:text-green-400">
                  <CheckCircle2 className="w-4 h-4" />
                  {t("formulas.calculated", { count: preview.rows.length })}
                </span>
              ) : null}
            </div>

            {/* Only set-level problems (cycles, unknown variables) land here —
                anything tied to a formula is shown under that formula instead. */}
            {preview?.issues
              .filter((i) => !i.key)
              .map((issue, k) => (
                <div key={k} className="text-sm text-red-600 dark:text-red-400">
                  {issue.message}
                </div>
              ))}

            {preview && preview.rows.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left border-b dark:border-gray-700">
                      <th className="py-2 pr-3">#</th>
                      <th className="py-2 pr-3">{t("scouting.team")}</th>
                      {columns.map((c) => (
                        <th key={c} className="py-2 pr-3 font-mono text-xs whitespace-nowrap">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((r) => (
                      <tr key={r.team_id} className="border-b dark:border-gray-800">
                        <td className="py-1.5 pr-3 text-gray-500">{r.rank ?? "DQ"}</td>
                        <td className="py-1.5 pr-3">{r.team_name ?? r.team_id}</td>
                        {columns.map((c) => (
                          <td key={c} className="py-1.5 pr-3 font-mono text-xs">
                            {r.values[c] !== undefined ? formatValue(r.values[c]) : "—"}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {preview && preview.rows.length === 0 && (
              <p className="text-sm text-gray-500">
                {t("formulas.noTeams")}
              </p>
            )}
          </div>
        </div>

        {/* ── Reference ─────────────────────────────────────────────────────── */}
        <div className="space-y-4">
          <div className="card p-4">
            <h2 className="font-medium mb-2">{t("formulas.variables")}</h2>
            <dl className="space-y-1.5 text-sm">
              {Object.entries(reference?.inputs ?? {}).map(([name, desc]) => (
                <div key={name}>
                  <dt className="font-mono text-xs text-primary-700 dark:text-primary-400">
                    {name}
                  </dt>
                  <dd className="text-gray-600 dark:text-gray-400 text-xs">{desc}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="card p-4">
            <h2 className="font-medium mb-2">{t("formulas.functions")}</h2>
            <p className="text-xs text-gray-500 mb-2">{t("formulas.perTeam")}</p>
            <dl className="space-y-1.5 text-sm mb-4">
              {(reference?.row_functions ?? []).map((f) => (
                <div key={f.name}>
                  <dt className="font-mono text-xs text-primary-700 dark:text-primary-400">
                    {f.signature}
                  </dt>
                  <dd className="text-gray-600 dark:text-gray-400 text-xs">{f.description}</dd>
                </div>
              ))}
            </dl>
            <p className="text-xs text-gray-500 mb-2">{t("formulas.acrossTeams")}</p>
            <dl className="space-y-1.5 text-sm">
              {(reference?.scope_functions ?? []).map((f) => (
                <div key={f.name}>
                  <dt className="font-mono text-xs text-primary-700 dark:text-primary-400">
                    {f.signature}
                  </dt>
                  <dd className="text-gray-600 dark:text-gray-400 text-xs">{f.description}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="card p-4">
            <h2 className="font-medium mb-1">{t("formulas.order")}</h2>
            <p className="text-xs text-gray-500 mb-2">
              {t("formulas.orderHint")}
            </p>
            <div className="font-mono text-xs text-gray-600 dark:text-gray-400 break-words">
              {columns.length > 0 ? columns.join(" → ") : "—"}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function BracketWeightsCard({
  weights,
  onSave,
  saving,
}: {
  weights: Record<string, number>;
  onSave: (w: Record<string, number>) => void;
  saving: boolean;
}) {
  const { t } = useTranslation("scoring");
  const [draft, setDraft] = useState<[string, string][]>([]);

  useEffect(() => {
    const entries = Object.entries(weights);
    setDraft(entries.length > 0 ? entries.map(([k, v]) => [k, String(v)]) : [["A", "1"]]);
  }, [weights]);

  const commit = () => {
    const out: Record<string, number> = {};
    for (const [bracket, value] of draft) {
      const key = bracket.trim();
      const num = Number(value);
      if (key && Number.isFinite(num)) out[key] = num;
    }
    onSave(out);
  };

  return (
    <div className="card p-4 space-y-3">
      <div>
        <h2 className="font-medium">{t("formulas.bracketWeights")}</h2>
        <p className="text-xs text-gray-500">
          <Trans t={t} i18nKey="formulas.bracketWeightsHint" components={{ code: <code className="font-mono" /> }} />
        </p>
      </div>
      <div className="space-y-2">
        {draft.map(([bracket, value], i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              className="input font-mono max-w-[6rem]"
              placeholder="A"
              value={bracket}
              onChange={(e) =>
                setDraft((p) => p.map((row, idx) => (idx === i ? [e.target.value, row[1]] : row)))
              }
            />
            <span className="text-gray-400">×</span>
            <input
              className="input font-mono max-w-[12rem]"
              placeholder="1.0"
              value={value}
              onChange={(e) =>
                setDraft((p) => p.map((row, idx) => (idx === i ? [row[0], e.target.value] : row)))
              }
            />
            <button
              className="btn-danger px-2"
              title={t("formulas.remove")}
              onClick={() => setDraft((p) => p.filter((_, idx) => idx !== i))}
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <button className="btn-secondary" onClick={() => setDraft((p) => [...p, ["", "1"]])}>
          <Plus className="w-4 h-4" />
          {t("de.bracket")}
        </button>
        <button className="btn-primary" onClick={commit} disabled={saving}>
          <Save className="w-4 h-4" />
          {t("formulas.saveWeights")}
        </button>
      </div>
    </div>
  );
}

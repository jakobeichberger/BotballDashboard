/**
 * Category registry of a season (GET/PUT /seasons/{id}/categories).
 *
 * A category is what a team competes in (Botball, ECER Open, Aerial Junior,
 * Aerial Senior, JBC, or one an organiser added). Everything that used to
 * hard-code "botball | open | aerial | jbc" reads the season's list here.
 * Local types: not yet part of the generated client.
 */
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "@/lib/api";
import { CATEGORY_LABEL } from "@/lib/teams";

export type CategoryKind = "botball" | "open" | "aerial" | "jbc" | "custom";

export interface SeasonCategory {
  key: string;
  label_de: string;
  label_en: string;
  kind: CategoryKind;
  formula_preset: string | null;
  run_count: number | null;
  counted_runs: number | null;
  rank_per_bracket: boolean;
  sort_order?: number | null;
}

export const CATEGORY_KINDS: CategoryKind[] = ["botball", "open", "aerial", "jbc", "custom"];

/**
 * Kinds whose teams play no seeding or head-to-head matches: their results are
 * aerial runs or challenge points (backend modules.seasons.categories.MATCHLESS_KINDS,
 * which rejects a match score for them). A custom category may score matches.
 */
export const MATCHLESS_KINDS: CategoryKind[] = ["aerial", "jbc"];

export const playsMatches = (kind: CategoryKind): boolean => !MATCHLESS_KINDS.includes(kind);

/** The backend defaults (modules.seasons.categories), used until the list has loaded. */
export const DEFAULT_CATEGORIES: SeasonCategory[] = [
  { key: "botball", label_de: "Botball", label_en: "Botball", kind: "botball", formula_preset: null, run_count: null, counted_runs: null, rank_per_bracket: false },
  { key: "open", label_de: "ECER Open", label_en: "ECER Open", kind: "open", formula_preset: null, run_count: null, counted_runs: null, rank_per_bracket: false },
  { key: "aerial_junior", label_de: "Aerial Junior", label_en: "Aerial Junior", kind: "aerial", formula_preset: null, run_count: 6, counted_runs: 3, rank_per_bracket: false },
  { key: "aerial", label_de: "Aerial Senior", label_en: "Aerial Senior", kind: "aerial", formula_preset: null, run_count: 4, counted_runs: null, rank_per_bracket: false },
  { key: "jbc", label_de: "Junior Botball Challenge", label_en: "Junior Botball Challenge", kind: "jbc", formula_preset: null, run_count: null, counted_runs: null, rank_per_bracket: false },
];

export function categoryLabel(entry: SeasonCategory | undefined, key: string, language: string): string {
  if (!entry) return CATEGORY_LABEL[key] ?? key;
  return language.startsWith("de") ? entry.label_de : entry.label_en;
}

export function useSeasonCategories(seasonId?: string) {
  const { i18n } = useTranslation();
  const query = useQuery<SeasonCategory[]>({
    queryKey: ["season-categories", seasonId],
    queryFn: async () => (await api.get(`/seasons/${seasonId}/categories`)).data,
    enabled: !!seasonId,
  });
  const categories = query.data?.length ? query.data : DEFAULT_CATEGORIES;
  const byKey = new Map(categories.map((entry) => [entry.key, entry]));
  return {
    categories,
    isLoading: query.isLoading,
    byKey,
    label: (key: string) => categoryLabel(byKey.get(key), key, i18n.language),
    kindOf: (key: string): CategoryKind => byKey.get(key)?.kind ?? ((CATEGORY_KINDS as string[]).includes(key) ? (key as CategoryKind) : "custom"),
  };
}

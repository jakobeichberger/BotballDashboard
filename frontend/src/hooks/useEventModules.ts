import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

/** Feature modules an event can switch on (backend: modules.events.module_access). */
export type ModuleKey = "seeding" | "double_elimination" | "paper" | "documentation" | "aerial" | "printing" | "bots";

/**
 * A route's module requirement. `paper_scoring` is the season flag
 * use_paper_scoring (the paper score is entered with the documentation scores).
 */
export type ModuleRequirement = ModuleKey | "paper_scoring";

export interface EventModules {
  event_id: string;
  available_modules: ModuleKey[];
  active_modules: ModuleKey[];
  effective_modules: ModuleKey[];
  season_flags: Record<string, boolean>;
}

export const MODULE_LABELS: Record<ModuleKey, { de: string; en: string; seasonFlag?: string }> = {
  seeding: { de: "Seeding", en: "Seeding", seasonFlag: "use_seeding" },
  double_elimination: { de: "Double Elimination", en: "Double elimination", seasonFlag: "use_double_elimination" },
  paper: { de: "Paper-Review", en: "Paper review" },
  documentation: { de: "Dokumentation", en: "Documentation", seasonFlag: "use_documentation_scoring" },
  aerial: { de: "Aerial", en: "Aerial", seasonFlag: "use_aerial" },
  printing: { de: "3D-Druck", en: "3D printing" },
  bots: { de: "Roboter-Galerie", en: "Robot gallery" },
};

export function useEventModules(eventId?: string) {
  return useQuery<EventModules>({
    queryKey: ["event-modules", eventId],
    queryFn: async () => (await api.get(`/v1/events/${eventId}/modules`)).data,
    enabled: !!eventId,
    staleTime: 60_000,
  });
}

/**
 * Whether a route needing `requirement` (any of a list) is available.
 * Unknown module state (loading, offline without cache) fails open — the
 * backend still refuses disabled modules.
 */
export function isModuleEnabled(
  modules: EventModules | undefined,
  requirement?: ModuleRequirement | readonly ModuleRequirement[],
): boolean {
  if (!requirement || !modules) return true;
  const required = typeof requirement === "string" ? [requirement] : requirement;
  return required.some((item) =>
    item === "paper_scoring" ? !!modules.season_flags.use_paper_scoring : modules.effective_modules.includes(item),
  );
}

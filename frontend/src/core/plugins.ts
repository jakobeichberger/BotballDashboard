/**
 * Static module registry for the modular monolith.
 *
 * Modules are compiled with the application. This registry is the single source
 * for event routes, navigation, permissions, dashboard widgets and translations;
 * it is deliberately not a runtime plugin loader.
 */
import { lazy, type ComponentType, type LazyExoticComponent } from "react";
import type { ModuleRequirement } from "@/hooks/useEventModules";

export interface RouteDefinition {
  path: string;
  component: LazyExoticComponent<ComponentType>;
  permission: string;
  label: { de: string; en: string };
  icon: "dashboard" | "teams" | "schedule" | "scoring" | "scans" | "papers" | "printing" | "bots" | "settings";
  navigation?: boolean;
  /** Per-event module switch (any of) the route needs; see useEventModules. */
  module?: ModuleRequirement | readonly ModuleRequirement[];
}

export interface DashboardWidgetDefinition {
  id: "teams" | "matches" | "papers" | "print_jobs";
  permission: string;
  audience: "admin" | "juror" | "reviewer" | "mentor";
  label: { de: string; en: string };
}

export interface ModuleDefinition {
  id: string;
  routes: RouteDefinition[];
  dashboardWidgets: DashboardWidgetDefinition[];
  translations: readonly string[];
}

// Kept as a compatibility type for module-local declarations from older builds.
export interface PluginDefinition {
  id: string;
  name: { de: string; en: string };
  routes: Array<{
    path: string;
    component: LazyExoticComponent<ComponentType>;
    permission?: string;
    label: { de: string; en: string };
    icon?: string;
  }>;
  dashboardWidgets: Array<{
    id: string;
    component: LazyExoticComponent<ComponentType>;
    defaultSize: "small" | "medium" | "large";
    permission?: string;
  }>;
  i18n: { de: () => Promise<unknown>; en: () => Promise<unknown> };
}

export const modules: readonly ModuleDefinition[] = [
  {
    id: "dashboard",
    routes: [
      { path: "dashboard", component: lazy(() => import("@/pages/DashboardPage")), permission: "dashboard:read", label: { de: "Dashboard", en: "Dashboard" }, icon: "dashboard", navigation: true },
      // Empty permission: every signed-in user may manage their own profile.
      { path: "profile", component: lazy(() => import("@/pages/ProfilePage")), permission: "", label: { de: "Profil", en: "Profile" }, icon: "settings", navigation: false },
    ],
    dashboardWidgets: [],
    translations: ["common", "dashboard"],
  },
  {
    id: "teams",
    routes: [
      { path: "teams", component: lazy(() => import("@/pages/TeamsPage")), permission: "teams:read", label: { de: "Teams", en: "Teams" }, icon: "teams", navigation: true },
      { path: "teams/matrix", component: lazy(() => import("@/pages/TeamSeasonMatrixPage")), permission: "teams:read", label: { de: "Team-Saison-Matrix", en: "Team-season matrix" }, icon: "teams", navigation: false },
      { path: "teams/:id", component: lazy(() => import("@/pages/TeamDetailPage")), permission: "teams:read", label: { de: "Team", en: "Team" }, icon: "teams", navigation: false },
      { path: "bots", component: lazy(() => import("@/pages/BotsPage")), permission: "teams:read", label: { de: "Roboter", en: "Robots" }, icon: "bots", navigation: true, module: "bots" },
      { path: "bots/:id", component: lazy(() => import("@/pages/BotDetailPage")), permission: "teams:read", label: { de: "Roboter", en: "Robot" }, icon: "bots", navigation: false, module: "bots" },
    ],
    dashboardWidgets: [{ id: "teams", permission: "teams:read", audience: "mentor", label: { de: "Teams", en: "Teams" } }],
    translations: ["teams"],
  },
  {
    id: "events",
    routes: [
      { path: "schedule", component: lazy(() => import("@/pages/EventSchedulePage")), permission: "events:read", label: { de: "Zeitplan", en: "Schedule" }, icon: "schedule", navigation: true },
      { path: "settings", component: lazy(() => import("@/pages/EventSetupPage")), permission: "events:write", label: { de: "Event-Verwaltung", en: "Event setup" }, icon: "settings", navigation: true },
    ],
    dashboardWidgets: [],
    translations: ["events"],
  },
  {
    id: "admin",
    routes: [
      { path: "admin/*", component: lazy(() => import("@/pages/SettingsPage")), permission: "users:read", label: { de: "Admin-Einstellungen", en: "Admin settings" }, icon: "settings", navigation: true },
    ],
    dashboardWidgets: [],
    translations: ["common"],
  },
  {
    id: "scoring",
    routes: [
      { path: "scoring", component: lazy(() => import("@/pages/EventScoringPage")), permission: "scoring:read", label: { de: "Wertung", en: "Scoring" }, icon: "scoring", navigation: true },
      { path: "scans", component: lazy(() => import("@/pages/ScanReviewPage")), permission: "scoring:read", label: { de: "OCR-Prüfung", en: "OCR review" }, icon: "scans", navigation: true },
      { path: "scoreboard", component: lazy(() => import("@/pages/ScoreboardPage")), permission: "scoring:read", label: { de: "Rangliste & Ergebnisse", en: "Rankings & results" }, icon: "scoring", navigation: true },
      { path: "scoring/entry", component: lazy(() => import("@/pages/ScoreEntryPage")), permission: "scoring:write", label: { de: "Punkte eintragen", en: "Enter scores" }, icon: "scoring", navigation: false },
      { path: "scoring/de", component: lazy(() => import("@/pages/DEPage")), permission: "scoring:admin", label: { de: "Double Elimination", en: "Double elimination" }, icon: "scoring", navigation: false, module: "double_elimination" },
      { path: "scoring/aerial", component: lazy(() => import("@/pages/AerialPage")), permission: "scoring:admin", label: { de: "Aerial", en: "Aerial" }, icon: "scoring", navigation: false, module: "aerial" },
      { path: "scoring/doc", component: lazy(() => import("@/pages/DocScoringPage")), permission: "scoring:admin", label: { de: "Dokumentation", en: "Documentation" }, icon: "scoring", navigation: false, module: ["documentation", "paper_scoring"] },
      { path: "scoring/score-sheets", component: lazy(() => import("@/modules/scoring/score-sheets/pages/ScoreSheetsPage")), permission: "scoring:admin", label: { de: "Score-Sheets", en: "Score sheets" }, icon: "scans", navigation: false },
      { path: "formulas", component: lazy(() => import("@/pages/FormulasPage")), permission: "scoring:formulas", label: { de: "Punkteformeln", en: "Scoring formulas" }, icon: "scoring", navigation: true },
    ],
    dashboardWidgets: [{ id: "matches", permission: "scoring:read", audience: "juror", label: { de: "Wertungen", en: "Scores" } }],
    translations: ["scoring", "events"],
  },
  {
    id: "papers",
    routes: [
      { path: "papers", component: lazy(() => import("@/pages/PapersPage")), permission: "papers:read", label: { de: "Paper-Review", en: "Paper review" }, icon: "papers", navigation: true, module: "paper" },
      { path: "papers/:id", component: lazy(() => import("@/pages/PaperDetailPage")), permission: "papers:read", label: { de: "Paper", en: "Paper" }, icon: "papers", navigation: false, module: "paper" },
    ],
    dashboardWidgets: [{ id: "papers", permission: "papers:read", audience: "reviewer", label: { de: "Paper", en: "Papers" } }],
    translations: ["papers"],
  },
  {
    id: "printing",
    routes: [
      { path: "printing", component: lazy(() => import("@/pages/PrintingPage")), permission: "printing:read", label: { de: "3D-Druck", en: "3D printing" }, icon: "printing", navigation: true, module: "printing" },
      { path: "printing/jobs/:id", component: lazy(() => import("@/pages/PrintJobDetailPage")), permission: "printing:read", label: { de: "Druckauftrag", en: "Print job" }, icon: "printing", navigation: false, module: "printing" },
    ],
    dashboardWidgets: [{ id: "print_jobs", permission: "printing:read", audience: "admin", label: { de: "Druckaufträge", en: "Print jobs" } }],
    translations: ["printing"],
  },
] as const;

export const eventRoutes = modules.flatMap((module) => module.routes);
export const navigationRoutes = eventRoutes.filter((route) => route.navigation);
export const dashboardWidgets = modules.flatMap((module) => module.dashboardWidgets);
export const translationNamespaces = [...new Set(modules.flatMap((module) => module.translations))];

/**
 * Static module registry for the modular monolith.
 *
 * Modules are compiled with the application. This registry is the single source
 * for event routes, navigation, permissions, dashboard widgets and translations;
 * it is deliberately not a runtime plugin loader.
 */
import { lazy, type ComponentType, type LazyExoticComponent } from "react";

export interface RouteDefinition {
  path: string;
  component: LazyExoticComponent<ComponentType>;
  permission: string;
  label: { de: string; en: string };
  icon: "dashboard" | "teams" | "schedule" | "scoring" | "scans" | "papers" | "printing" | "settings";
  navigation?: boolean;
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
    routes: [{ path: "dashboard", component: lazy(() => import("@/pages/DashboardPage")), permission: "dashboard:read", label: { de: "Dashboard", en: "Dashboard" }, icon: "dashboard", navigation: true }],
    dashboardWidgets: [],
    translations: ["common", "dashboard"],
  },
  {
    id: "teams",
    routes: [{ path: "teams", component: lazy(() => import("@/pages/TeamsPage")), permission: "teams:read", label: { de: "Teams", en: "Teams" }, icon: "teams", navigation: true }],
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
    id: "scoring",
    routes: [
      { path: "scoring", component: lazy(() => import("@/pages/EventScoringPage")), permission: "scoring:read", label: { de: "Wertung", en: "Scoring" }, icon: "scoring", navigation: true },
      { path: "scans", component: lazy(() => import("@/pages/ScanReviewPage")), permission: "scoring:read", label: { de: "OCR-Prüfung", en: "OCR review" }, icon: "scans", navigation: true },
    ],
    dashboardWidgets: [{ id: "matches", permission: "scoring:read", audience: "juror", label: { de: "Wertungen", en: "Scores" } }],
    translations: ["scoring", "events"],
  },
  {
    id: "papers",
    routes: [{ path: "papers", component: lazy(() => import("@/pages/PapersPage")), permission: "papers:read", label: { de: "Paper-Review", en: "Paper review" }, icon: "papers", navigation: true }],
    dashboardWidgets: [{ id: "papers", permission: "papers:read", audience: "reviewer", label: { de: "Paper", en: "Papers" } }],
    translations: ["papers"],
  },
  {
    id: "printing",
    routes: [{ path: "printing", component: lazy(() => import("@/pages/PrintingPage")), permission: "printing:read", label: { de: "3D-Druck", en: "3D printing" }, icon: "printing", navigation: true }],
    dashboardWidgets: [{ id: "print_jobs", permission: "printing:read", audience: "admin", label: { de: "Druckaufträge", en: "Print jobs" } }],
    translations: ["printing"],
  },
] as const;

export const eventRoutes = modules.flatMap((module) => module.routes);
export const navigationRoutes = eventRoutes.filter((route) => route.navigation);
export const dashboardWidgets = modules.flatMap((module) => module.dashboardWidgets);
export const translationNamespaces = [...new Set(modules.flatMap((module) => module.translations))];

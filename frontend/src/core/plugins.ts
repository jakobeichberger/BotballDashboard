/**
 * Static module registry for the modular monolith.
 *
 * Modules are compiled with the application. This registry is the single source
 * for event routes, navigation, permissions and translation namespaces; it is
 * deliberately not a runtime plugin loader. Dashboards pick their sections by
 * role themselves (pages/dashboard), so modules declare no dashboard widgets.
 */
import { lazy, type ComponentType, type LazyExoticComponent } from "react";
import type { ModuleRequirement } from "@/hooks/useEventModules";

/**
 * Sidebar sections, in display order: the event itself (people, schedule,
 * submissions), everything around scoring, and organiser administration.
 */
export const NAV_GROUPS = ["event", "scoring", "admin"] as const;
export type NavGroup = (typeof NAV_GROUPS)[number];

export interface RouteDefinition {
  path: string;
  component: LazyExoticComponent<ComponentType>;
  permission: string;
  label: { de: string; en: string };
  icon: "dashboard" | "teams" | "schedule" | "scoring" | "scans" | "papers" | "printing" | "bots" | "settings" | "stats" | "performance" | "calendar" | "scouting" | "ranking" | "formulas" | "awards" | "admin";
  navigation?: boolean;
  /** Sidebar section the navigation entry is listed under (see NAV_GROUPS). */
  group?: NavGroup;
  /** Per-event module switch (any of) the route needs; see useEventModules. */
  module?: ModuleRequirement | readonly ModuleRequirement[];
}

export interface ModuleDefinition {
  id: string;
  routes: RouteDefinition[];
  /** i18n namespaces the module's pages use; the i18n key test checks they exist. */
  translations: readonly string[];
}

export const modules: readonly ModuleDefinition[] = [
  {
    id: "dashboard",
    routes: [
      { path: "dashboard", component: lazy(() => import("@/pages/DashboardPage")), permission: "dashboard:read", label: { de: "Dashboard", en: "Dashboard" }, icon: "dashboard", navigation: true, group: "event" },
      // Empty permission: every signed-in user may manage their own profile.
      { path: "profile", component: lazy(() => import("@/pages/ProfilePage")), permission: "", label: { de: "Profil", en: "Profile" }, icon: "settings", navigation: false },
      { path: "calendar", component: lazy(() => import("@/pages/CalendarPage")), permission: "seasons:read", label: { de: "Deadlines", en: "Deadlines" }, icon: "calendar", navigation: true, group: "event" },
    ],
    translations: ["common", "auth", "dashboard", "profile", "analytics"],
  },
  {
    id: "teams",
    routes: [
      { path: "teams", component: lazy(() => import("@/pages/TeamsPage")), permission: "teams:read", label: { de: "Teams", en: "Teams" }, icon: "teams", navigation: true, group: "event" },
      { path: "teams/matrix", component: lazy(() => import("@/pages/TeamSeasonMatrixPage")), permission: "teams:read", label: { de: "Team-Saison-Matrix", en: "Team-season matrix" }, icon: "teams", navigation: false },
      { path: "teams/:id", component: lazy(() => import("@/pages/TeamDetailPage")), permission: "teams:read", label: { de: "Team", en: "Team" }, icon: "teams", navigation: false },
      { path: "bots", component: lazy(() => import("@/pages/BotsPage")), permission: "teams:read", label: { de: "Roboter", en: "Robots" }, icon: "bots", navigation: true, group: "event", module: "bots" },
      { path: "bots/:id", component: lazy(() => import("@/pages/BotDetailPage")), permission: "teams:read", label: { de: "Roboter", en: "Robot" }, icon: "bots", navigation: false, module: "bots" },
    ],
    translations: ["teams", "bots"],
  },
  {
    id: "events",
    routes: [
      { path: "schedule", component: lazy(() => import("@/pages/EventSchedulePage")), permission: "events:read", label: { de: "Zeitplan", en: "Schedule" }, icon: "schedule", navigation: true, group: "event" },
      { path: "settings", component: lazy(() => import("@/pages/EventSetupPage")), permission: "events:write", label: { de: "Event-Verwaltung", en: "Event setup" }, icon: "settings", navigation: true, group: "admin" },
    ],
    translations: ["events"],
  },
  {
    id: "admin",
    routes: [
      { path: "admin/*", component: lazy(() => import("@/pages/SettingsPage")), permission: "users:read", label: { de: "Admin-Einstellungen", en: "Admin settings" }, icon: "admin", navigation: true, group: "admin" },
    ],
    translations: ["common", "settings"],
  },
  {
    id: "scoring",
    routes: [
      { path: "scoring", component: lazy(() => import("@/pages/EventScoringPage")), permission: "scoring:read", label: { de: "Wertung", en: "Scoring" }, icon: "scoring", navigation: true, group: "scoring" },
      { path: "scans", component: lazy(() => import("@/pages/ScanReviewPage")), permission: "scoring:read", label: { de: "OCR-Prüfung", en: "OCR review" }, icon: "scans", navigation: true, group: "scoring" },
      { path: "scouting", component: lazy(() => import("@/pages/ScoutingPage")), permission: "scoring:read", label: { de: "Scouting", en: "Scouting" }, icon: "scouting", navigation: true, group: "scoring" },
      { path: "scoreboard", component: lazy(() => import("@/pages/ScoreboardPage")), permission: "scoring:read", label: { de: "Rangliste & Ergebnisse", en: "Rankings & results" }, icon: "ranking", navigation: true, group: "scoring" },
      { path: "scoring/entry", component: lazy(() => import("@/pages/ScoreEntryPage")), permission: "scoring:write", label: { de: "Punkte eintragen", en: "Enter scores" }, icon: "scoring", navigation: false },
      { path: "scoring/de", component: lazy(() => import("@/pages/DEPage")), permission: "scoring:admin", label: { de: "Double Elimination", en: "Double elimination" }, icon: "scoring", navigation: false, module: "double_elimination" },
      { path: "scoring/aerial", component: lazy(() => import("@/pages/AerialPage")), permission: "scoring:admin", label: { de: "Aerial", en: "Aerial" }, icon: "scoring", navigation: false, module: "aerial" },
      { path: "scoring/jbc", component: lazy(() => import("@/pages/JBCPage")), permission: "scoring:admin", label: { de: "Junior Botball Challenge", en: "Junior Botball Challenge" }, icon: "scoring", navigation: false },
      { path: "scoring/doc", component: lazy(() => import("@/pages/DocScoringPage")), permission: "scoring:admin", label: { de: "Dokumentation", en: "Documentation" }, icon: "scoring", navigation: false, module: ["documentation", "paper_scoring"] },
      { path: "scoring/score-sheets", component: lazy(() => import("@/modules/scoring/score-sheets/pages/ScoreSheetsPage")), permission: "scoring:admin", label: { de: "Score-Sheets", en: "Score sheets" }, icon: "scans", navigation: false },
      // Mentors see their own team only; the backend scopes the data.
      { path: "performance", component: lazy(() => import("@/pages/PerformancePage")), permission: "scoring:write", label: { de: "Performance", en: "Performance" }, icon: "performance", navigation: true, group: "scoring" },
      { path: "statistics", component: lazy(() => import("@/pages/StatisticsPage")), permission: "scoring:admin", label: { de: "Statistik & Anomalien", en: "Statistics & anomalies" }, icon: "stats", navigation: true, group: "scoring" },
      { path: "awards", component: lazy(() => import("@/pages/AwardsPage")), permission: "scoring:read", label: { de: "Awards", en: "Awards" }, icon: "awards", navigation: true, group: "scoring" },
      { path: "formulas", component: lazy(() => import("@/pages/FormulasPage")), permission: "scoring:formulas", label: { de: "Punkteformeln", en: "Scoring formulas" }, icon: "formulas", navigation: true, group: "scoring" },
    ],
    translations: ["scoring", "events", "analytics"],
  },
  {
    id: "papers",
    routes: [
      { path: "papers", component: lazy(() => import("@/pages/PapersPage")), permission: "papers:read", label: { de: "Paper-Review", en: "Paper review" }, icon: "papers", navigation: true, group: "event", module: "paper" },
      { path: "papers/:id", component: lazy(() => import("@/pages/PaperDetailPage")), permission: "papers:read", label: { de: "Paper", en: "Paper" }, icon: "papers", navigation: false, module: "paper" },
    ],
    translations: ["papers"],
  },
  {
    id: "printing",
    routes: [
      { path: "printing", component: lazy(() => import("@/pages/PrintingPage")), permission: "printing:read", label: { de: "3D-Druck", en: "3D printing" }, icon: "printing", navigation: true, group: "event", module: "printing" },
      { path: "printing/jobs/:id", component: lazy(() => import("@/pages/PrintJobDetailPage")), permission: "printing:read", label: { de: "Druckauftrag", en: "Print job" }, icon: "printing", navigation: false, module: "printing" },
    ],
    translations: ["printing"],
  },
] as const;

export const eventRoutes = modules.flatMap((module) => module.routes);
export const navigationRoutes = eventRoutes.filter((route) => route.navigation);
export const translationNamespaces = [...new Set(modules.flatMap((module) => module.translations))];

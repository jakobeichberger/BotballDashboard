/**
 * Plugin Registry
 *
 * Every module exports a `PluginDefinition` from its `index.tsx`.
 * This file collects all plugins and exposes helpers used by the
 * app router and navigation builder.
 */

import type { ComponentType, LazyExoticComponent } from 'react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface RouteDefinition {
  path: string
  component: LazyExoticComponent<ComponentType>
  permission?: string
  label: { de: string; en: string }
  icon?: string
}

export interface WidgetDefinition {
  id: string
  component: LazyExoticComponent<ComponentType>
  defaultSize: 'small' | 'medium' | 'large'
  permission?: string
}

export interface PluginDefinition {
  id: string
  name: { de: string; en: string }
  routes: RouteDefinition[]
  dashboardWidgets: WidgetDefinition[]
  i18n: {
    de: () => Promise<unknown>
    en: () => Promise<unknown>
  }
}

// ---------------------------------------------------------------------------
// Plugin registration
// ---------------------------------------------------------------------------

import scoringPlugin from '@/modules/scoring'
// import paperReviewPlugin from '@/modules/paper-review'   // add when implemented
// import printPlugin       from '@/modules/print'          // add when implemented

export const plugins: PluginDefinition[] = [
  scoringPlugin,
  // paperReviewPlugin,
  // printPlugin,
]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** All routes across all registered plugins */
export const allRoutes = (): RouteDefinition[] =>
  plugins.flatMap((p) => p.routes)

/** All dashboard widgets across all registered plugins */
export const allWidgets = (): WidgetDefinition[] =>
  plugins.flatMap((p) => p.dashboardWidgets)

/** Load i18n resources for the given language from all plugins */
export const loadPluginI18n = async (lang: 'de' | 'en') => {
  const results = await Promise.all(plugins.map((p) => p.i18n[lang]()))
  // Returns array of JSON objects; caller merges them into i18next
  return results
}

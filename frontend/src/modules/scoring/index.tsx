/**
 * Scoring Module – plugin registration
 *
 * Registers routes, nav items, dashboard widgets and i18n
 * for the scoring module (including Score Sheet Import).
 *
 * The core plugin registry (src/core/plugins.ts) iterates over
 * all module index files and calls register() at app startup.
 */

import { lazy } from 'react'
import type { PluginDefinition } from '@/core/plugins'

const ScoreSheetsPage = lazy(
  () => import('./score-sheets/pages/ScoreSheetsPage')
)
// Further pages (RankingPage, TournamentPage, …) added here as implemented
// const RankingPage    = lazy(() => import('./ranking/pages/RankingPage'))
// const TournamentPage = lazy(() => import('./tournament/pages/TournamentPage'))

const plugin: PluginDefinition = {
  id: 'scoring',
  name: { de: 'Scoring', en: 'Scoring' },

  routes: [
    {
      path: '/scoring/score-sheets',
      // Season and optional level come from URL params set by the parent layout
      component: ScoreSheetsPage,
      permission: 'scoring:admin',
      label: { de: 'Score-Sheets', en: 'Score Sheets' },
      icon: 'document',
    },
    // { path: '/scoring/ranking',    component: RankingPage,    permission: 'scoring:read', … },
    // { path: '/scoring/tournament', component: TournamentPage, permission: 'scoring:read', … },
  ],

  dashboardWidgets: [
    // { id: 'ranking',     component: …, defaultSize: 'large',  permission: 'scoring:read' },
    // { id: 'bracket',     component: …, defaultSize: 'large',  permission: 'scoring:read' },
    // { id: 'performance', component: …, defaultSize: 'medium', permission: 'scoring:read' },
  ],

  i18n: {
    de: () => import('./score-sheets/i18n/de.json'),
    en: () => import('./score-sheets/i18n/en.json'),
  },
}

export default plugin

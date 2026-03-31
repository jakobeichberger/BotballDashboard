/**
 * Score Sheet Import – API client
 */

import { api } from '@/lib/api'

export interface ScoringField {
  key: string
  label: string
  multiplier: number
  max_value: number | null
  type: 'count' | 'boolean'
  section: string | null
  notes: string | null
}

export interface ExtractedFieldCandidate {
  raw_text: string
  suggested_key: string
  suggested_label: string
  suggested_multiplier: number | null
  suggested_max_value: number | null
  confidence: number
  page: number
  accepted: boolean
}

export interface ScoreSheetTemplateListItem {
  id: string
  label: string
  year: number
  game_theme: string | null
  is_active: boolean
  file_name: string
  ocr_status: 'pending' | 'processing' | 'done' | 'failed'
  confirmed_fields_count: number | null
  uploaded_at: string
}

export interface ScoreSheetTemplate extends ScoreSheetTemplateListItem {
  season_id: string
  competition_level_id: string | null
  file_size_bytes: number | null
  extracted_fields: ExtractedFieldCandidate[] | null
  confirmed_fields: ScoringField[] | null
  uploaded_by: string
  confirmed_by: string | null
  confirmed_at: string | null
}

export interface UploadScoreSheetParams {
  seasonId: string
  file: File
  label: string
  year: number
  gameTheme?: string
  competitionLevelId?: string
}

export interface ConfirmFieldsParams {
  sheetId: string
  fields: ScoringField[]
  applyToSchema: boolean
}

// ---------------------------------------------------------------------------

export const scoreSheetApi = {
  list: (seasonId: string, competitionLevelId?: string) =>
    api.get<ScoreSheetTemplateListItem[]>(
      `/scoring/seasons/${seasonId}/score-sheets`,
      { params: competitionLevelId ? { competition_level_id: competitionLevelId } : {} }
    ).then(r => r.data),

  get: (sheetId: string) =>
    api.get<ScoreSheetTemplate>(`/scoring/score-sheets/${sheetId}`).then(r => r.data),

  upload: ({ seasonId, file, label, year, gameTheme, competitionLevelId }: UploadScoreSheetParams) => {
    const form = new FormData()
    form.append('file', file)
    form.append('label', label)
    form.append('year', String(year))
    if (gameTheme) form.append('game_theme', gameTheme)
    if (competitionLevelId) form.append('competition_level_id', competitionLevelId)
    return api.post<ScoreSheetTemplate>(
      `/scoring/seasons/${seasonId}/score-sheets`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    ).then(r => r.data)
  },

  downloadUrl: (sheetId: string) => `/api/scoring/score-sheets/${sheetId}/file`,

  confirm: ({ sheetId, fields, applyToSchema }: ConfirmFieldsParams) =>
    api.post<ScoreSheetTemplate>(`/scoring/score-sheets/${sheetId}/confirm`, {
      fields,
      apply_to_schema: applyToSchema,
    }).then(r => r.data),

  setActive: (sheetId: string) =>
    api.put(`/scoring/score-sheets/${sheetId}/active`),

  delete: (sheetId: string) =>
    api.delete(`/scoring/score-sheets/${sheetId}`),
}

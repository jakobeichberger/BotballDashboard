/**
 * ScoreSheetsPage
 *
 * Admin page: manage scoring sheet PDFs for a season.
 *
 * Layout:
 *   ┌─────────────────────────────────────────────────────┐
 *   │  Score Sheets – ECER 2026          [+ Upload PDF]   │
 *   ├───────────┬─────────────────────────────────────────┤
 *   │  Sheet    │  FieldCandidateEditor (right panel)     │
 *   │  list     │                                         │
 *   │           │                                         │
 *   └───────────┴─────────────────────────────────────────┘
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { scoreSheetApi, type ScoreSheetTemplate, type ScoreSheetTemplateListItem } from '../api/scoreSheets'
import ScoreSheetUploadForm from '../components/ScoreSheetUploadForm'
import FieldCandidateEditor from '../components/FieldCandidateEditor'

const OCR_STATUS_BADGE: Record<string, string> = {
  pending:    'badge badge-gray',
  processing: 'badge badge-yellow',
  done:       'badge badge-green',
  failed:     'badge badge-red',
}

export default function ScoreSheetsPage() {
  const { t } = useTranslation()
  const { seasonId, competitionLevelId } = useParams<{
    seasonId: string
    competitionLevelId?: string
  }>()
  const queryClient = useQueryClient()

  const [showUpload, setShowUpload] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  // List query
  const { data: sheets = [], isLoading } = useQuery({
    queryKey: ['score-sheets', seasonId, competitionLevelId],
    queryFn: () => scoreSheetApi.list(seasonId!, competitionLevelId),
    enabled: !!seasonId,
    // Poll while any sheet is still processing
    refetchInterval: (query) =>
      query.state.data?.some((s) => s.ocr_status === 'processing' || s.ocr_status === 'pending')
        ? 3000
        : false,
  })

  // Detail query (only when a sheet is selected)
  const { data: selectedSheet } = useQuery({
    queryKey: ['score-sheets', 'detail', selectedId],
    queryFn: () => scoreSheetApi.get(selectedId!),
    enabled: !!selectedId,
  })

  // Set active mutation
  const setActive = useMutation({
    mutationFn: (id: string) => scoreSheetApi.setActive(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['score-sheets', seasonId] }),
  })

  // Delete mutation
  const deleteSheet = useMutation({
    mutationFn: (id: string) => scoreSheetApi.delete(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ['score-sheets', seasonId] })
      if (selectedId === id) setSelectedId(null)
    },
  })

  const handleDelete = (sheet: ScoreSheetTemplateListItem) => {
    if (!confirm(t('scoreSheets.deleteConfirm', { label: sheet.label }))) return
    deleteSheet.mutate(sheet.id)
  }

  return (
    <div className="flex flex-col h-full gap-4 p-4 lg:p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">{t('scoreSheets.title')}</h1>
          <p className="text-sm text-gray-500 mt-0.5">{t('scoreSheets.subtitle')}</p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => setShowUpload(true)}
        >
          + {t('scoreSheets.upload.button')}
        </button>
      </div>

      {/* Upload modal */}
      {showUpload && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white dark:bg-gray-900 rounded-xl shadow-xl p-6 w-full max-w-lg mx-4">
            <h2 className="text-lg font-semibold mb-4">{t('scoreSheets.upload.title')}</h2>
            <ScoreSheetUploadForm
              seasonId={seasonId!}
              competitionLevelId={competitionLevelId}
              onSuccess={() => {
                setShowUpload(false)
                queryClient.invalidateQueries({ queryKey: ['score-sheets', seasonId] })
              }}
              onCancel={() => setShowUpload(false)}
            />
          </div>
        </div>
      )}

      {/* Main content */}
      <div className="flex flex-1 gap-4 min-h-0">
        {/* Left: sheet list */}
        <div className="w-full lg:w-80 shrink-0 flex flex-col gap-2 overflow-y-auto">
          {isLoading && (
            <p className="text-sm text-gray-500 py-4 text-center">{t('common.loading')}</p>
          )}

          {!isLoading && sheets.length === 0 && (
            <div className="text-center py-12 text-gray-400 text-sm">
              <p className="text-2xl mb-2">📄</p>
              <p>{t('scoreSheets.empty')}</p>
            </div>
          )}

          {sheets.map((sheet) => (
            <button
              key={sheet.id}
              type="button"
              onClick={() => setSelectedId(sheet.id)}
              className={[
                'w-full text-left rounded-lg border p-3 transition-colors',
                selectedId === sheet.id
                  ? 'border-blue-500 bg-blue-50 dark:bg-blue-950'
                  : 'border-gray-200 dark:border-gray-700 hover:border-blue-300',
              ].join(' ')}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="font-medium text-sm truncate">{sheet.label}</p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {sheet.year} {sheet.game_theme ? `· ${sheet.game_theme}` : ''}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0">
                  {sheet.is_active && (
                    <span className="badge badge-blue text-xs">{t('scoreSheets.active')}</span>
                  )}
                  <span className={OCR_STATUS_BADGE[sheet.ocr_status] ?? 'badge badge-gray'}>
                    {t(`scoreSheets.ocr.${sheet.ocr_status}`)}
                  </span>
                </div>
              </div>

              {sheet.confirmed_fields_count != null && (
                <p className="text-xs text-green-600 dark:text-green-400 mt-1.5">
                  ✓ {sheet.confirmed_fields_count} {t('scoreSheets.fields.confirmed')}
                </p>
              )}

              {/* Actions row */}
              <div className="flex gap-2 mt-2" onClick={(e) => e.stopPropagation()}>
                <a
                  href={scoreSheetApi.downloadUrl(sheet.id)}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                >
                  {t('scoreSheets.download')}
                </a>
                {!sheet.is_active && (
                  <>
                    <span className="text-gray-300">·</span>
                    <button
                      type="button"
                      onClick={() => setActive.mutate(sheet.id)}
                      className="text-xs text-gray-600 dark:text-gray-400 hover:underline"
                    >
                      {t('scoreSheets.setActive')}
                    </button>
                    <span className="text-gray-300">·</span>
                    <button
                      type="button"
                      onClick={() => handleDelete(sheet)}
                      className="text-xs text-red-500 hover:underline"
                    >
                      {t('common.delete')}
                    </button>
                  </>
                )}
              </div>
            </button>
          ))}
        </div>

        {/* Right: field editor */}
        <div className="flex-1 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700 p-4 lg:p-6">
          {!selectedSheet ? (
            <div className="flex h-full items-center justify-center text-gray-400 text-sm">
              {t('scoreSheets.selectToEdit')}
            </div>
          ) : selectedSheet.ocr_status === 'processing' || selectedSheet.ocr_status === 'pending' ? (
            <div className="flex flex-col items-center justify-center gap-3 h-full text-gray-500">
              <div className="animate-spin h-8 w-8 rounded-full border-2 border-blue-500 border-t-transparent" />
              <p className="text-sm">{t('scoreSheets.ocr.processing')}</p>
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-between mb-4">
                <h2 className="font-semibold">{selectedSheet.label}</h2>
                <span className="text-sm text-gray-500">{selectedSheet.file_name}</span>
              </div>
              <FieldCandidateEditor
                template={selectedSheet}
                onConfirmed={() =>
                  queryClient.invalidateQueries({ queryKey: ['score-sheets', 'detail', selectedId] })
                }
              />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

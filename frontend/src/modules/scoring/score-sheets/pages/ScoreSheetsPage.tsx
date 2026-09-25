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
import { useSearchParams } from 'react-router-dom'
import { useScoringScope } from '@/hooks/useScoringScope'
import { scoreSheetApi, type ScoreSheetTemplateListItem } from '../api/scoreSheets'
import ScoreSheetUploadForm from '../components/ScoreSheetUploadForm'
import FieldCandidateEditor from '../components/FieldCandidateEditor'
import OcrLayoutEditor from '../components/OcrLayoutEditor'
import Modal from '@/components/Modal'
import { confirmAction } from '@/lib/confirm'
import { downloadFile } from '@/lib/download'
import { toast } from '@/lib/toast'

const OCR_STATUS_BADGE: Record<string, string> = {
  pending:    'badge badge-gray',
  processing: 'badge badge-yellow',
  done:       'badge badge-green',
  failed:     'badge badge-red',
}

export default function ScoreSheetsPage() {
  const { t } = useTranslation('scoring')
  // The page lives under /events/:eventId: templates belong to that event's
  // season; an optional ?competition_level_id= narrows the list.
  const { seasonId } = useScoringScope()
  const [searchParams] = useSearchParams()
  const competitionLevelId = searchParams.get('competition_level_id') ?? undefined
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
      query.state.data?.some((s: ScoreSheetTemplateListItem) => s.ocr_status === 'processing' || s.ocr_status === 'pending')
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

  const handleDelete = async (sheet: ScoreSheetTemplateListItem) => {
    if (!(await confirmAction({ message: t('scoreSheets.deleteConfirm', { label: sheet.label }), tone: 'danger' }))) return
    deleteSheet.mutate(sheet.id)
  }

  // The file endpoint needs the bearer token: a plain link would get a 401.
  const handleDownload = async (sheet: ScoreSheetTemplateListItem) => {
    try {
      await downloadFile(scoreSheetApi.downloadUrl(sheet.id), undefined, undefined, `${sheet.label}.pdf`)
    } catch (error) {
      toast.apiError(error, t('scoreSheets.downloadFailed'))
    }
  }

  return (
    <div className="flex flex-col h-full gap-4 p-4 lg:p-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">{t('scoreSheets.title')}</h1>
          <p className="text-sm text-gray-500 mt-0.5">{t('scoreSheets.subtitle')}</p>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => setShowUpload(true)}
        >
          <span aria-hidden="true">+</span> {t('scoreSheets.upload.button')}
        </button>
      </div>

      {/* Upload modal */}
      <Modal open={showUpload} title={t('scoreSheets.upload.title')} onClose={() => setShowUpload(false)}>
        <ScoreSheetUploadForm
          seasonId={seasonId!}
          competitionLevelId={competitionLevelId}
          onSuccess={() => {
            setShowUpload(false)
            queryClient.invalidateQueries({ queryKey: ['score-sheets', seasonId] })
          }}
          onCancel={() => setShowUpload(false)}
        />
      </Modal>

      {/* Main content */}
      <div className="flex flex-1 flex-col gap-4 min-h-0 lg:flex-row">
        {/* Left: sheet list */}
        <div className="w-full lg:w-80 shrink-0 flex flex-col gap-2 lg:overflow-y-auto">
          {isLoading && (
            <p role="status" className="text-sm text-gray-500 py-4 text-center">{t('common:loading')}</p>
          )}

          {!isLoading && sheets.length === 0 && (
            <div className="text-center py-12 text-gray-400 text-sm">
              <p className="text-2xl mb-2" aria-hidden="true">📄</p>
              <p>{t('scoreSheets.empty')}</p>
            </div>
          )}

          {sheets.map((sheet) => (
            <div
              key={sheet.id}
              className={[
                'w-full rounded-lg border transition-colors',
                selectedId === sheet.id
                  ? 'border-blue-500 bg-blue-50 dark:bg-blue-950'
                  : 'border-gray-200 dark:border-gray-700 hover:border-blue-300',
              ].join(' ')}
            >
              {/* Selecting and the row actions are separate controls: a button must not contain links or buttons. */}
              <button
                type="button"
                onClick={() => setSelectedId(sheet.id)}
                aria-pressed={selectedId === sheet.id}
                className="block w-full rounded-t-lg p-3 pb-2 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
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
                  <span aria-hidden="true">✓ </span>{sheet.confirmed_fields_count} {t('scoreSheets.fields.confirmed')}
                </p>
              )}
              </button>

              {/* Actions row */}
              <div className="flex flex-wrap gap-1 px-2 pb-2">
                <button
                  type="button"
                  onClick={() => void handleDownload(sheet)}
                  className="min-h-11 rounded px-2 text-xs text-blue-600 hover:underline dark:text-blue-400"
                  aria-label={t('scoreSheets.downloadFor', { label: sheet.label })}
                >
                  {t('scoreSheets.download')}
                </button>
                {!sheet.is_active && (
                  <>
                    <button
                      type="button"
                      onClick={() => setActive.mutate(sheet.id)}
                      className="min-h-11 rounded px-2 text-xs text-gray-600 hover:underline dark:text-gray-400"
                    >
                      {t('scoreSheets.setActive')}
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDelete(sheet)}
                      className="min-h-11 rounded px-2 text-xs text-red-600 hover:underline"
                      aria-label={t('scoreSheets.deleteFor', { label: sheet.label })}
                    >
                      {t('common:delete')}
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Right: field editor */}
        <div className="min-w-0 flex-1 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700 p-4 lg:p-6">
          {!selectedSheet ? (
            <div className="flex h-full items-center justify-center text-gray-400 text-sm">
              {t('scoreSheets.selectToEdit')}
            </div>
          ) : selectedSheet.ocr_status === 'processing' || selectedSheet.ocr_status === 'pending' ? (
            <div className="flex flex-col items-center justify-center gap-3 h-full text-gray-500">
              <div className="animate-spin h-8 w-8 rounded-full border-2 border-blue-500 border-t-transparent" />
              <p className="text-sm">{t('scoreSheets.ocr.processingHint')}</p>
            </div>
          ) : (
            <div>
              <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                <h2 className="font-semibold">{selectedSheet.label}</h2>
                <span className="text-sm text-gray-500">{selectedSheet.file_name}</span>
              </div>
              <FieldCandidateEditor
                template={selectedSheet}
                onConfirmed={() =>
                  queryClient.invalidateQueries({ queryKey: ['score-sheets', 'detail', selectedId] })
                }
              />
              <div className="mt-8 border-t border-gray-200 pt-6 dark:border-gray-700">
                <OcrLayoutEditor
                  template={selectedSheet}
                  onSaved={() =>
                    queryClient.invalidateQueries({ queryKey: ['score-sheets', 'detail', selectedId] })
                  }
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

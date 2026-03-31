/**
 * FieldCandidateEditor
 *
 * Shows the OCR-extracted field candidates in a table.
 * Admin can accept/reject/edit each candidate and confirm the final list.
 */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  scoreSheetApi,
  type ExtractedFieldCandidate,
  type ScoringField,
  type ScoreSheetTemplate,
} from '../api/scoreSheets'

interface Props {
  template: ScoreSheetTemplate
  onConfirmed?: () => void
}

/** Convert an accepted candidate into a ScoringField */
function candidateToField(c: ExtractedFieldCandidate): ScoringField {
  return {
    key: c.suggested_key,
    label: c.suggested_label,
    multiplier: c.suggested_multiplier ?? 1,
    max_value: c.suggested_max_value,
    type: 'count',
    section: null,
    notes: null,
  }
}

export default function FieldCandidateEditor({ template, onConfirmed }: Props) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const rawCandidates = template.extracted_fields ?? []

  // Local state: editable list of fields (starts from accepted candidates or confirmed_fields)
  const [fields, setFields] = useState<ScoringField[]>(() => {
    if (template.confirmed_fields?.length) return template.confirmed_fields
    return rawCandidates.filter((c) => c.accepted).map(candidateToField)
  })

  const [applyToSchema, setApplyToSchema] = useState(true)
  const [showCandidates, setShowCandidates] = useState(!template.confirmed_fields?.length)

  const confirm = useMutation({
    mutationFn: () =>
      scoreSheetApi.confirm({ sheetId: template.id, fields, applyToSchema }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['score-sheets'] })
      onConfirmed?.()
    },
  })

  const updateField = (idx: number, patch: Partial<ScoringField>) => {
    setFields((prev) => prev.map((f, i) => (i === idx ? { ...f, ...patch } : f)))
  }

  const removeField = (idx: number) => {
    setFields((prev) => prev.filter((_, i) => i !== idx))
  }

  const addFromCandidate = (c: ExtractedFieldCandidate) => {
    setFields((prev) => [...prev, candidateToField(c)])
  }

  const addBlank = () => {
    setFields((prev) => [
      ...prev,
      { key: '', label: '', multiplier: 1, max_value: null, type: 'count', section: null, notes: null },
    ])
  }

  const OCR_STATUS_COLOR: Record<string, string> = {
    done: 'text-green-600 dark:text-green-400',
    processing: 'text-yellow-600 dark:text-yellow-400',
    pending: 'text-gray-500',
    failed: 'text-red-600 dark:text-red-400',
  }

  return (
    <div className="space-y-6">
      {/* OCR status banner */}
      <div className="flex items-center gap-2 text-sm">
        <span className="font-medium">{t('scoreSheets.ocr.status')}:</span>
        <span className={OCR_STATUS_COLOR[template.ocr_status] ?? ''}>
          {t(`scoreSheets.ocr.${template.ocr_status}`)}
        </span>
        {template.ocr_status === 'done' && (
          <span className="text-gray-500">
            — {rawCandidates.length} {t('scoreSheets.ocr.candidatesFound')}
          </span>
        )}
      </div>

      {/* Toggle raw candidates */}
      {rawCandidates.length > 0 && (
        <button
          type="button"
          className="text-sm text-blue-600 dark:text-blue-400 underline"
          onClick={() => setShowCandidates((v) => !v)}
        >
          {showCandidates
            ? t('scoreSheets.candidates.hide')
            : t('scoreSheets.candidates.show', { count: rawCandidates.length })}
        </button>
      )}

      {/* Raw candidates table */}
      {showCandidates && rawCandidates.length > 0 && (
        <div className="overflow-x-auto rounded border dark:border-gray-700">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-100 dark:bg-gray-800">
              <tr>
                <th className="px-3 py-2 text-left">{t('scoreSheets.candidates.rawText')}</th>
                <th className="px-3 py-2 text-left">{t('scoreSheets.candidates.suggestedLabel')}</th>
                <th className="px-3 py-2 text-right">{t('scoreSheets.candidates.multiplier')}</th>
                <th className="px-3 py-2 text-right">{t('scoreSheets.candidates.confidence')}</th>
                <th className="px-3 py-2 text-right">Pg</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {rawCandidates.map((c, i) => {
                const alreadyAdded = fields.some((f) => f.key === c.suggested_key)
                return (
                  <tr key={i} className="border-t dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800/50">
                    <td className="px-3 py-1.5 font-mono text-xs text-gray-500 max-w-[200px] truncate">
                      {c.raw_text}
                    </td>
                    <td className="px-3 py-1.5">{c.suggested_label}</td>
                    <td className="px-3 py-1.5 text-right">
                      {c.suggested_multiplier != null ? `×${c.suggested_multiplier}` : '–'}
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      <span
                        className={
                          c.confidence >= 0.8
                            ? 'text-green-600'
                            : c.confidence >= 0.5
                            ? 'text-yellow-600'
                            : 'text-red-500'
                        }
                      >
                        {Math.round(c.confidence * 100)}%
                      </span>
                    </td>
                    <td className="px-3 py-1.5 text-right text-gray-400">{c.page}</td>
                    <td className="px-3 py-1.5 text-right">
                      <button
                        type="button"
                        disabled={alreadyAdded}
                        onClick={() => addFromCandidate(c)}
                        className="text-xs text-blue-600 dark:text-blue-400 disabled:opacity-30"
                      >
                        {alreadyAdded ? '✓' : t('scoreSheets.candidates.add')}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Confirmed fields editor */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-medium text-sm">
            {t('scoreSheets.fields.title')} ({fields.length})
          </h3>
          <button type="button" onClick={addBlank} className="btn btn-sm btn-ghost">
            + {t('scoreSheets.fields.addBlank')}
          </button>
        </div>

        <div className="overflow-x-auto rounded border dark:border-gray-700">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-100 dark:bg-gray-800">
              <tr>
                <th className="px-3 py-2 text-left">{t('scoreSheets.fields.key')}</th>
                <th className="px-3 py-2 text-left">{t('scoreSheets.fields.label')}</th>
                <th className="px-3 py-2 text-left">{t('scoreSheets.fields.section')}</th>
                <th className="px-3 py-2 text-right">{t('scoreSheets.fields.multiplier')}</th>
                <th className="px-3 py-2 text-right">{t('scoreSheets.fields.maxValue')}</th>
                <th className="px-3 py-2 text-center">{t('scoreSheets.fields.type')}</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {fields.map((f, idx) => (
                <tr key={idx} className="border-t dark:border-gray-700">
                  <td className="px-2 py-1">
                    <input
                      className="input input-sm w-36 font-mono text-xs"
                      value={f.key}
                      onChange={(e) => updateField(idx, { key: e.target.value })}
                      placeholder="snake_case_key"
                    />
                  </td>
                  <td className="px-2 py-1">
                    <input
                      className="input input-sm w-48"
                      value={f.label}
                      onChange={(e) => updateField(idx, { label: e.target.value })}
                    />
                  </td>
                  <td className="px-2 py-1">
                    <input
                      className="input input-sm w-32"
                      value={f.section ?? ''}
                      onChange={(e) => updateField(idx, { section: e.target.value || null })}
                      placeholder={t('scoreSheets.fields.sectionPlaceholder')}
                    />
                  </td>
                  <td className="px-2 py-1">
                    <input
                      type="number"
                      step="0.5"
                      className="input input-sm w-16 text-right"
                      value={f.multiplier}
                      onChange={(e) => updateField(idx, { multiplier: parseFloat(e.target.value) || 1 })}
                    />
                  </td>
                  <td className="px-2 py-1">
                    <input
                      type="number"
                      className="input input-sm w-16 text-right"
                      value={f.max_value ?? ''}
                      onChange={(e) =>
                        updateField(idx, { max_value: e.target.value ? Number(e.target.value) : null })
                      }
                      placeholder="–"
                    />
                  </td>
                  <td className="px-2 py-1 text-center">
                    <select
                      className="input input-sm w-24"
                      value={f.type}
                      onChange={(e) => updateField(idx, { type: e.target.value as 'count' | 'boolean' })}
                    >
                      <option value="count">count</option>
                      <option value="boolean">boolean</option>
                    </select>
                  </td>
                  <td className="px-2 py-1 text-right">
                    <button
                      type="button"
                      onClick={() => removeField(idx)}
                      className="text-red-500 hover:text-red-700 text-xs px-2"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
              {fields.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-3 py-6 text-center text-gray-400 text-sm">
                    {t('scoreSheets.fields.empty')}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Apply to schema toggle */}
      <label className="flex items-center gap-2 text-sm cursor-pointer">
        <input
          type="checkbox"
          checked={applyToSchema}
          onChange={(e) => setApplyToSchema(e.target.checked)}
          className="checkbox"
        />
        {t('scoreSheets.fields.applyToSchema')}
      </label>

      {/* Confirm button */}
      <div className="flex justify-end gap-3">
        <button
          type="button"
          disabled={fields.length === 0 || confirm.isPending}
          onClick={() => confirm.mutate()}
          className="btn btn-primary"
        >
          {confirm.isPending
            ? t('scoreSheets.fields.confirming')
            : t('scoreSheets.fields.confirm', { count: fields.length })}
        </button>
      </div>

      {confirm.isError && (
        <p className="text-sm text-red-600 dark:text-red-400">
          {t('scoreSheets.fields.confirmError')}
        </p>
      )}
    </div>
  )
}

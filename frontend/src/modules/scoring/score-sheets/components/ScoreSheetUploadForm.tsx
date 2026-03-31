/**
 * ScoreSheetUploadForm
 * Modal/panel for uploading a new scoring sheet PDF.
 */

import { useState, useRef } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { scoreSheetApi, type UploadScoreSheetParams } from '../api/scoreSheets'

interface Props {
  seasonId: string
  competitionLevelId?: string
  onSuccess?: () => void
  onCancel?: () => void
}

export default function ScoreSheetUploadForm({ seasonId, competitionLevelId, onSuccess, onCancel }: Props) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [file, setFile] = useState<File | null>(null)
  const [label, setLabel] = useState('')
  const [year, setYear] = useState(new Date().getFullYear())
  const [gameTheme, setGameTheme] = useState('')
  const [dragOver, setDragOver] = useState(false)

  const upload = useMutation({
    mutationFn: (params: UploadScoreSheetParams) => scoreSheetApi.upload(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['score-sheets', seasonId] })
      onSuccess?.()
    },
  })

  const handleFile = (f: File) => {
    if (f.type !== 'application/pdf') {
      alert(t('scoreSheets.upload.onlyPdf'))
      return
    }
    setFile(f)
    // Pre-fill label from filename if empty
    if (!label) {
      setLabel(f.name.replace(/\.pdf$/i, '').replace(/[-_]/g, ' '))
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped) handleFile(dropped)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!file || !label || !year) return
    upload.mutate({
      seasonId,
      file,
      label,
      year,
      gameTheme: gameTheme || undefined,
      competitionLevelId,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {/* Drop zone */}
      <div
        className={[
          'flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors cursor-pointer',
          dragOver
            ? 'border-blue-500 bg-blue-50 dark:bg-blue-950'
            : 'border-gray-300 dark:border-gray-600 hover:border-blue-400',
        ].join(' ')}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
        />
        {file ? (
          <div className="text-center">
            <p className="text-sm font-medium text-green-600 dark:text-green-400">✓ {file.name}</p>
            <p className="text-xs text-gray-500 mt-1">{(file.size / 1024).toFixed(0)} KB</p>
          </div>
        ) : (
          <div className="text-center">
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {t('scoreSheets.upload.dropzone')}
            </p>
            <p className="text-xs text-gray-400 mt-1">PDF, max. 20 MB</p>
          </div>
        )}
      </div>

      {/* Label */}
      <div>
        <label className="block text-sm font-medium mb-1">
          {t('scoreSheets.upload.label')} *
        </label>
        <input
          type="text"
          required
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="z.B. ECER 2026 Official Score Sheet"
          className="input w-full"
        />
      </div>

      {/* Year + Theme */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium mb-1">
            {t('scoreSheets.upload.year')} *
          </label>
          <input
            type="number"
            required
            value={year}
            min={2020}
            max={2040}
            onChange={(e) => setYear(Number(e.target.value))}
            className="input w-full"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">
            {t('scoreSheets.upload.gameTheme')}
          </label>
          <input
            type="text"
            value={gameTheme}
            onChange={(e) => setGameTheme(e.target.value)}
            placeholder="z.B. Warehouse & Logistics"
            className="input w-full"
          />
        </div>
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-3 pt-2">
        <button type="button" onClick={onCancel} className="btn btn-ghost">
          {t('common.cancel')}
        </button>
        <button
          type="submit"
          disabled={!file || !label || upload.isPending}
          className="btn btn-primary"
        >
          {upload.isPending
            ? t('scoreSheets.upload.uploading')
            : t('scoreSheets.upload.submit')}
        </button>
      </div>

      {upload.isError && (
        <p className="text-sm text-red-600 dark:text-red-400">
          {t('scoreSheets.upload.error')}
        </p>
      )}
    </form>
  )
}

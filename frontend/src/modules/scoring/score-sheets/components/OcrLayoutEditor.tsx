/**
 * OCR layout of a score-sheet template: where on the page the OCR worker
 * reads each confirmed scoring field.
 *
 * Boxes are drawn over a reference image (a scan or photo of a blank sheet,
 * kept in the browser only) or over an empty page, and can be fine-tuned as
 * percentages. They are stored normalized (0–1 of the page), so the page size
 * only sets the resolution the worker aligns every scan to.
 */
import { useEffect, useMemo, useRef, useState, type PointerEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ImagePlus, Save, Trash2 } from 'lucide-react'
import { scoreSheetApi, type OcrRegion, type ScoreSheetTemplate } from '../api/scoreSheets'
import { DEFAULT_PAGE, MIN_SIZE, clamp01, fitRegion, normalizeRegions, rectFromPoints } from '../layout'

const EDGES = ['x', 'y', 'width', 'height'] as const

export default function OcrLayoutEditor({
  template,
  onSaved,
}: {
  template: ScoreSheetTemplate
  onSaved: () => void
}) {
  const { t } = useTranslation('scoring')
  const fields = useMemo(() => template.confirmed_fields ?? [], [template.confirmed_fields])
  const [page, setPage] = useState(DEFAULT_PAGE)
  const [regions, setRegions] = useState<OcrRegion[]>([])
  const [active, setActive] = useState('')
  const [image, setImage] = useState<string | null>(null)
  const [drag, setDrag] = useState<{ start: { x: number; y: number }; current: { x: number; y: number } } | null>(null)
  const [message, setMessage] = useState('')
  const surface = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const width = template.page_width || DEFAULT_PAGE.width
    const height = template.page_height || DEFAULT_PAGE.height
    setPage({ width, height })
    const keys = new Set(fields.map((field) => field.key))
    setRegions(normalizeRegions(template.field_regions, width, height).filter((region) => keys.has(region.key)))
    setActive(fields[0]?.key ?? '')
    setMessage('')
  }, [template.id, template.page_width, template.page_height, template.field_regions, fields])

  useEffect(() => () => { if (image) URL.revokeObjectURL(image) }, [image])

  const regionOf = (key: string) => regions.find((region) => region.key === key)
  const setRegion = (region: OcrRegion) =>
    setRegions((current) => [...current.filter((item) => item.key !== region.key), region])
  const removeRegion = (key: string) => setRegions((current) => current.filter((item) => item.key !== key))

  const save = useMutation({
    mutationFn: () =>
      scoreSheetApi.updateLayout(template.id, {
        page_width: page.width,
        page_height: page.height,
        // Anchors and validation rules have no editor yet; keep what is stored.
        anchors: template.anchors ?? [],
        field_regions: fields.map((field) => regionOf(field.key)).filter((region): region is OcrRegion => !!region),
        validation_rules: template.validation_rules ?? {},
      }),
    onSuccess: () => { setMessage(t('scoreSheets.layout.saved')); onSaved() },
    onError: (e: any) => setMessage(typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : t('scoreSheets.layout.saveFailed')),
  })

  const point = (event: PointerEvent<HTMLDivElement>) => {
    const box = surface.current!.getBoundingClientRect()
    return {
      x: clamp01((event.clientX - box.left) / (box.width || 1)),
      y: clamp01((event.clientY - box.top) / (box.height || 1)),
    }
  }
  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (!active) return
    event.currentTarget.setPointerCapture?.(event.pointerId)
    const start = point(event)
    setDrag({ start, current: start })
  }
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (drag) setDrag({ ...drag, current: point(event) })
  }
  const onPointerUp = (event: PointerEvent<HTMLDivElement>) => {
    if (!drag) return
    const rect = rectFromPoints(active, drag.start, point(event))
    setDrag(null)
    if (rect.width < MIN_SIZE || rect.height < MIN_SIZE) return
    setRegion(rect)
    // Continue with the next field that has no box yet.
    const next = fields.find((field) => field.key !== active && !regionOf(field.key))
    if (next) setActive(next.key)
  }

  const onImage = (file: File | undefined) => {
    if (!file) return
    setImage(URL.createObjectURL(file))
  }

  if (fields.length === 0) {
    return <p className="text-sm text-gray-500">{t('scoreSheets.layout.noFields')}</p>
  }

  const preview = drag ? rectFromPoints(active, drag.start, drag.current) : null
  const labelOf = (key: string) => fields.find((field) => field.key === key)?.label ?? key
  const boxStyle = (region: OcrRegion) => ({
    left: `${region.x * 100}%`,
    top: `${region.y * 100}%`,
    width: `${region.width * 100}%`,
    height: `${region.height * 100}%`,
  })

  return (
    <section className="space-y-4" aria-labelledby="ocr-layout-title">
      <div>
        <h3 id="ocr-layout-title" className="font-semibold">{t('scoreSheets.layout.title')}</h3>
        <p className="text-xs text-gray-500">{t('scoreSheets.layout.hint')}</p>
      </div>

      <div className="flex flex-wrap items-end gap-3 text-sm">
        <label className="btn-secondary flex cursor-pointer items-center gap-2">
          <ImagePlus className="h-4 w-4" aria-hidden="true" />
          {t('scoreSheets.layout.referenceImage')}
          <input
            className="sr-only"
            type="file"
            accept="image/*"
            onChange={(e) => onImage(e.target.files?.[0])}
          />
        </label>
        <label className="font-medium">
          {t('scoreSheets.layout.pageWidth')}
          <input className="input mt-1 w-28" type="number" min={100} max={20000} value={page.width} onChange={(e) => setPage({ ...page, width: Number(e.target.value) })} />
        </label>
        <label className="font-medium">
          {t('scoreSheets.layout.pageHeight')}
          <input className="input mt-1 w-28" type="number" min={100} max={20000} value={page.height} onChange={(e) => setPage({ ...page, height: Number(e.target.value) })} />
        </label>
        <label className="font-medium">
          {t('scoreSheets.layout.drawField')}
          <select className="input mt-1" value={active} onChange={(e) => setActive(e.target.value)}>
            {fields.map((field) => <option key={field.key} value={field.key}>{field.label} ({field.key})</option>)}
          </select>
        </label>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,26rem)_1fr]">
        <div
          ref={surface}
          data-testid="ocr-layout-surface"
          role="application"
          aria-label={t('scoreSheets.layout.surface', { field: labelOf(active) })}
          className="relative w-full cursor-crosshair touch-none select-none overflow-hidden rounded border border-gray-300 bg-white dark:border-gray-600"
          style={{ aspectRatio: `${page.width} / ${page.height}` }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
        >
          {image && (
            <img
              src={image}
              alt=""
              draggable={false}
              className="pointer-events-none absolute inset-0 h-full w-full object-fill"
              onLoad={(e) => setPage({ width: e.currentTarget.naturalWidth, height: e.currentTarget.naturalHeight })}
            />
          )}
          {regions.map((region) => (
            <div
              key={region.key}
              className={`pointer-events-none absolute border-2 ${region.key === active ? 'border-blue-600 bg-blue-500/20' : 'border-emerald-600 bg-emerald-500/10'}`}
              style={boxStyle(region)}
            >
              <span className="absolute -top-4 left-0 whitespace-nowrap rounded bg-gray-900/80 px-1 text-[10px] text-white">{region.key}</span>
            </div>
          ))}
          {preview && <div className="pointer-events-none absolute border-2 border-dashed border-blue-600" style={boxStyle(preview)} />}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500">
                <th scope="col" className="py-1 pr-2 font-medium">{t('scoreSheets.layout.field')}</th>
                {EDGES.map((edge) => <th key={edge} scope="col" className="py-1 pr-2 font-medium">{t(`scoreSheets.layout.edge.${edge}`)}</th>)}
                <th scope="col" className="py-1"><span className="sr-only">{t('common:actions')}</span></th>
              </tr>
            </thead>
            <tbody>
              {fields.map((field) => {
                const region = regionOf(field.key)
                return (
                  <tr key={field.key} className={`border-t border-gray-100 dark:border-gray-800 ${field.key === active ? 'bg-blue-50 dark:bg-blue-950/40' : ''}`}>
                    <td className="py-1 pr-2">
                      <button type="button" className="text-left hover:underline" onClick={() => setActive(field.key)}>
                        {field.label} <span className="font-mono text-xs text-gray-500">{field.key}</span>
                      </button>
                    </td>
                    {EDGES.map((edge) => (
                      <td key={edge} className="py-1 pr-2">
                        {region ? (
                          <input
                            className="input w-20"
                            type="number"
                            min={0}
                            max={100}
                            step={0.1}
                            aria-label={t('scoreSheets.layout.edgeOf', { edge: t(`scoreSheets.layout.edge.${edge}`), field: field.key })}
                            value={Math.round(region[edge] * 1000) / 10}
                            onChange={(e) => setRegion(fitRegion({ ...region, [edge]: Number(e.target.value) / 100 }))}
                          />
                        ) : edge === 'x' ? (
                          <button type="button" className="text-xs text-blue-600 hover:underline dark:text-blue-400" onClick={() => setRegion({ key: field.key, x: 0.1, y: 0.1, width: 0.1, height: 0.03 })}>
                            {t('scoreSheets.layout.addBox')}
                          </button>
                        ) : null}
                      </td>
                    ))}
                    <td className="py-1 text-right">
                      {region && (
                        <button type="button" className="rounded p-1 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30" aria-label={t('scoreSheets.layout.removeBox', { field: field.key })} onClick={() => removeRegion(field.key)}>
                          <Trash2 className="h-4 w-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-gray-500">{t('scoreSheets.layout.coverage', { count: regions.length, total: fields.length })}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="btn-primary flex items-center gap-2" disabled={regions.length === 0 || save.isPending} onClick={() => save.mutate()}>
          <Save className="h-4 w-4" />
          {t('scoreSheets.layout.save')}
        </button>
        {message && <p role="status" className="text-sm text-gray-600 dark:text-gray-300">{message}</p>}
      </div>
    </section>
  )
}

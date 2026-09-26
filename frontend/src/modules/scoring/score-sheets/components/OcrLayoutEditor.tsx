/**
 * OCR layout of a score-sheet template: where on the page the OCR worker
 * reads each confirmed scoring field.
 *
 * Boxes are drawn over a reference image (a scan or photo of a blank sheet,
 * kept in the browser only) or over an empty page, and can be fine-tuned as
 * percentages. They are stored normalized (0–1 of the page), so the page size
 * only sets the resolution the worker aligns every scan to.
 *
 * Anchors are printed reference marks (filled squares) drawn the same way;
 * with two or more the worker aligns each scan by them instead of by the
 * sheet edge. The validation rules below decide which read values are flagged
 * in the scan review.
 */
import { useEffect, useMemo, useRef, useState, type PointerEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ImagePlus, Plus, Save, Trash2 } from 'lucide-react'
import { scoreSheetApi, type OcrAnchor, type OcrRegion, type OcrValidationRules, type ScoreSheetTemplate } from '../api/scoreSheets'
import {
  DEFAULT_PAGE,
  MIN_ANCHORS,
  MIN_SIZE,
  clamp01,
  compactRules,
  fitAnchor,
  fitRegion,
  nextAnchorName,
  normalizeAnchors,
  normalizeRegions,
  parseRules,
  rectFromPoints,
  rulesProblem,
} from '../layout'
import OcrValidationRulesEditor from './OcrValidationRulesEditor'
import { apiErrorMessage } from '@/lib/errors'
import { useChanged } from '@/hooks/useChanged'

const EDGES = ['x', 'y', 'width', 'height'] as const
type DrawMode = 'fields' | 'anchors'

/** The stored layout of `template` as editor state (regions of confirmed fields only). */
function storedLayout(template: ScoreSheetTemplate, fields: { key: string }[]) {
  const width = template.page_width || DEFAULT_PAGE.width
  const height = template.page_height || DEFAULT_PAGE.height
  const keys = new Set(fields.map((field) => field.key))
  return {
    page: { width, height },
    regions: normalizeRegions(template.field_regions, width, height).filter((region) => keys.has(region.key)),
    anchors: normalizeAnchors(template.anchors, width, height),
    rules: parseRules(template.validation_rules, keys),
    active: fields[0]?.key ?? '',
  }
}

export default function OcrLayoutEditor({
  template,
  onSaved,
}: {
  template: ScoreSheetTemplate
  onSaved: () => void
}) {
  const { t } = useTranslation('scoring')
  const fields = useMemo(() => template.confirmed_fields ?? [], [template.confirmed_fields])
  const [stored] = useState(() => storedLayout(template, fields))
  const [page, setPage] = useState(stored.page)
  const [regions, setRegions] = useState<OcrRegion[]>(stored.regions)
  const [anchors, setAnchors] = useState<OcrAnchor[]>(stored.anchors)
  const [rules, setRules] = useState<OcrValidationRules>(stored.rules)
  const [mode, setMode] = useState<DrawMode>('fields')
  const [active, setActive] = useState(stored.active)
  const [image, setImage] = useState<string | null>(null)
  const [drag, setDrag] = useState<{ start: { x: number; y: number }; current: { x: number; y: number } } | null>(null)
  const [message, setMessage] = useState('')
  const surface = useRef<HTMLDivElement>(null)

  // Another template, or a changed stored layout (e.g. after saving), replaces the editor state.
  const layoutChanged = useChanged([template.id, template.page_width, template.page_height, template.field_regions, template.anchors, template.validation_rules, fields])
  if (layoutChanged) {
    const next = storedLayout(template, fields)
    setPage(next.page)
    setRegions(next.regions)
    setAnchors(next.anchors)
    setRules(next.rules)
    setActive(next.active)
    setMessage('')
  }

  useEffect(() => () => { if (image) URL.revokeObjectURL(image) }, [image])

  const regionOf = (key: string) => regions.find((region) => region.key === key)
  const setRegion = (region: OcrRegion) =>
    setRegions((current) => [...current.filter((item) => item.key !== region.key), region])
  const removeRegion = (key: string) => setRegions((current) => current.filter((item) => item.key !== key))
  const setAnchor = (index: number, anchor: OcrAnchor) =>
    setAnchors((current) => current.map((item, i) => (i === index ? anchor : item)))
  const addAnchor = (box: Omit<OcrAnchor, 'name'>) =>
    setAnchors((current) => [...current, { name: nextAnchorName(current), ...box }])
  const removeAnchor = (index: number) => setAnchors((current) => current.filter((_, i) => i !== index))

  const anchorNames = anchors.map((anchor) => anchor.name.trim())
  const anchorProblem = anchorNames.some((name) => !name)
    ? t('scoreSheets.anchors.nameMissing')
    : new Set(anchorNames).size !== anchorNames.length
      ? t('scoreSheets.anchors.nameDuplicate')
      : null
  const ruleProblem = rulesProblem(rules)
  const problem = anchorProblem ?? (ruleProblem ? t(`scoreSheets.rules.problem.${ruleProblem.problem}`, { name: ruleProblem.name }) : null)

  const save = useMutation({
    mutationFn: () =>
      scoreSheetApi.updateLayout(template.id, {
        page_width: page.width,
        page_height: page.height,
        anchors: anchors.map((anchor) => ({ ...anchor, name: anchor.name.trim() })),
        field_regions: fields.map((field) => regionOf(field.key)).filter((region): region is OcrRegion => !!region),
        validation_rules: compactRules(rules),
      }),
    onSuccess: () => { setMessage(t('scoreSheets.layout.saved')); onSaved() },
    onError: (e: any) => setMessage(apiErrorMessage(e, t('scoreSheets.layout.saveFailed'))),
  })

  const point = (event: PointerEvent<HTMLDivElement>) => {
    const box = surface.current!.getBoundingClientRect()
    return {
      x: clamp01((event.clientX - box.left) / (box.width || 1)),
      y: clamp01((event.clientY - box.top) / (box.height || 1)),
    }
  }
  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (mode === 'fields' && !active) return
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
    if (mode === 'anchors') {
      addAnchor({ x: rect.x, y: rect.y, width: rect.width, height: rect.height })
      return
    }
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
    return <p className="text-sm text-leise">{t('scoreSheets.layout.noFields')}</p>
  }

  const preview = drag ? rectFromPoints(active, drag.start, drag.current) : null
  const labelOf = (key: string) => fields.find((field) => field.key === key)?.label ?? key
  const boxStyle = (region: Pick<OcrRegion, 'x' | 'y' | 'width' | 'height'>) => ({
    left: `${region.x * 100}%`,
    top: `${region.y * 100}%`,
    width: `${region.width * 100}%`,
    height: `${region.height * 100}%`,
  })

  return (
    <section className="space-y-4" aria-labelledby="ocr-layout-title">
      <div>
        <h3 id="ocr-layout-title" className="font-semibold">{t('scoreSheets.layout.title')}</h3>
        <p className="text-xs text-leise">{t('scoreSheets.layout.hint')}</p>
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
          {t('scoreSheets.layout.drawMode')}
          <select className="input mt-1" value={mode} onChange={(e) => setMode(e.target.value as DrawMode)}>
            <option value="fields">{t('scoreSheets.layout.modeFields')}</option>
            <option value="anchors">{t('scoreSheets.layout.modeAnchors')}</option>
          </select>
        </label>
        {mode === 'fields' && (
          <label className="font-medium">
            {t('scoreSheets.layout.drawField')}
            <select className="input mt-1" value={active} onChange={(e) => setActive(e.target.value)}>
              {fields.map((field) => <option key={field.key} value={field.key}>{field.label} ({field.key})</option>)}
            </select>
          </label>
        )}
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,26rem)_1fr]">
        <div
          ref={surface}
          data-testid="ocr-layout-surface"
          role="application"
          aria-label={mode === 'anchors' ? t('scoreSheets.anchors.surface') : t('scoreSheets.layout.surface', { field: labelOf(active) })}
          className="relative w-full cursor-crosshair touch-none select-none overflow-hidden rounded border border-rand-stark/70 bg-white"
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
              className={`pointer-events-none absolute border-2 ${region.key === active ? 'border-primary bg-primary/20' : 'border-success bg-emerald-500/10'}`}
              style={boxStyle(region)}
            >
              <span className="absolute -top-4 left-0 whitespace-nowrap rounded bg-gray-900/80 px-1 text-[10px] text-white">{region.key}</span>
            </div>
          ))}
          {anchors.map((anchor, index) => (
            <div
              key={`anchor-${index}`}
              className="pointer-events-none absolute border-2 border-warning bg-amber-400/30"
              style={boxStyle(anchor)}
            >
              <span className="absolute -bottom-4 left-0 whitespace-nowrap rounded bg-amber-700/90 px-1 text-[10px] text-white">{anchor.name}</span>
            </div>
          ))}
          {preview && <div className={`pointer-events-none absolute border-2 border-dashed ${mode === 'anchors' ? 'border-warning' : 'border-primary'}`} style={boxStyle(preview)} />}
        </div>

        <div className="space-y-6 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-fg">
                <th scope="col" className="py-1 pr-2 font-semibold">{t('scoreSheets.layout.field')}</th>
                {EDGES.map((edge) => <th key={edge} scope="col" className="py-1 pr-2 font-semibold">{t(`scoreSheets.layout.edge.${edge}`)}</th>)}
                <th scope="col" className="py-1"><span className="sr-only">{t('common:actions')}</span></th>
              </tr>
            </thead>
            <tbody>
              {fields.map((field) => {
                const region = regionOf(field.key)
                return (
                  <tr key={field.key} className={`border-t border-rand ${field.key === active ? 'bg-primary/6' : ''}`}>
                    <td className="py-1 pr-2">
                      <button type="button" className="text-left hover:underline" onClick={() => setActive(field.key)}>
                        {field.label} <span className="font-mono text-xs text-leise">{field.key}</span>
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
                          <button type="button" className="text-xs text-info hover:underline" onClick={() => setRegion({ key: field.key, x: 0.1, y: 0.1, width: 0.1, height: 0.03 })}>
                            {t('scoreSheets.layout.addBox')}
                          </button>
                        ) : null}
                      </td>
                    ))}
                    <td className="py-1 text-right">
                      {region && (
                        <button type="button" className="rounded p-1 text-danger hover:bg-danger/10" aria-label={t('scoreSheets.layout.removeBox', { field: field.key })} onClick={() => removeRegion(field.key)}>
                          <Trash2 className="h-4 w-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <p className="-mt-4 text-xs text-leise">{t('scoreSheets.layout.coverage', { count: regions.length, total: fields.length })}</p>

          <section aria-labelledby="ocr-anchors-title">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h4 id="ocr-anchors-title" className="font-semibold">{t('scoreSheets.anchors.title')}</h4>
              <button
                type="button"
                className="btn-secondary flex items-center gap-1 text-sm"
                onClick={() => addAnchor({ x: 0.02, y: 0.02, width: 0.03, height: 0.02 })}
              >
                <Plus className="h-4 w-4" aria-hidden="true" />
                {t('scoreSheets.anchors.add')}
              </button>
            </div>
            <p className="text-xs text-leise">{t('scoreSheets.anchors.hint')}</p>
            {anchors.length > 0 && (
              <div className="table-scroll">
              <table className="mt-2 w-full text-sm">
                <thead>
                  <tr className="text-left text-fg">
                    <th scope="col" className="py-1 pr-2 font-semibold">{t('scoreSheets.anchors.name')}</th>
                    {EDGES.map((edge) => <th key={edge} scope="col" className="py-1 pr-2 font-semibold">{t(`scoreSheets.layout.edge.${edge}`)}</th>)}
                    <th scope="col" className="py-1"><span className="sr-only">{t('common:actions')}</span></th>
                  </tr>
                </thead>
                <tbody>
                  {anchors.map((anchor, index) => (
                    <tr key={index} className="border-t border-rand">
                      <td className="py-1 pr-2">
                        <input
                          className="input w-32"
                          maxLength={100}
                          aria-label={t('scoreSheets.anchors.nameOf', { number: index + 1 })}
                          value={anchor.name}
                          onChange={(e) => setAnchor(index, { ...anchor, name: e.target.value })}
                        />
                      </td>
                      {EDGES.map((edge) => (
                        <td key={edge} className="py-1 pr-2">
                          <input
                            className="input w-20"
                            type="number"
                            min={0}
                            max={100}
                            step={0.1}
                            aria-label={t('scoreSheets.layout.edgeOf', { edge: t(`scoreSheets.layout.edge.${edge}`), field: anchor.name })}
                            value={Math.round(anchor[edge] * 1000) / 10}
                            onChange={(e) => setAnchor(index, fitAnchor({ ...anchor, [edge]: Number(e.target.value) / 100 }))}
                          />
                        </td>
                      ))}
                      <td className="py-1 text-right">
                        <button type="button" className="rounded p-1 text-danger hover:bg-danger/10" aria-label={t('scoreSheets.anchors.remove', { name: anchor.name })} onClick={() => removeAnchor(index)}>
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            )}
            {anchors.length > 0 && anchors.length < MIN_ANCHORS && (
              <p className="mt-1 text-xs text-warning">{t('scoreSheets.anchors.tooFew', { min: MIN_ANCHORS })}</p>
            )}
          </section>
        </div>
      </div>

      <OcrValidationRulesEditor rules={rules} fields={fields} onChange={setRules} />

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="btn-primary flex items-center gap-2" disabled={regions.length === 0 || !!problem || save.isPending} onClick={() => save.mutate()}>
          <Save className="h-4 w-4" />
          {t('scoreSheets.layout.save')}
        </button>
        {problem && <p role="alert" className="text-sm text-danger">{problem}</p>}
        {message && <p role="status" className="text-sm text-leise">{message}</p>}
      </div>
    </section>
  )
}

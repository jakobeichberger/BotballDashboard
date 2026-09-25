/**
 * Validation rules of a score-sheet template: which OCR values the worker
 * flags for a closer look in the scan review. Every value is reviewed before
 * it counts; the rules only decide what is highlighted.
 */
import { useTranslation } from 'react-i18next'
import { Plus, Trash2 } from 'lucide-react'
import type { OcrFieldRule, OcrSumRule, OcrValidationRules, ScoringField } from '../api/scoreSheets'

const EMPTY_RULE: Omit<OcrFieldRule, 'key'> = { min_value: null, max_value: null, integer: false, min_confidence: null }

const toNumber = (value: string): number | null => (value.trim() === '' || !Number.isFinite(Number(value)) ? null : Number(value))
const toPercent = (value: number | null) => (value === null ? '' : Math.round(value * 1000) / 10)
const fromPercent = (value: string): number | null => {
  const number = toNumber(value)
  return number === null ? null : Math.min(1, Math.max(0, number / 100))
}

export default function OcrValidationRulesEditor({
  rules,
  fields,
  onChange,
}: {
  rules: OcrValidationRules
  fields: ScoringField[]
  onChange: (rules: OcrValidationRules) => void
}) {
  const { t } = useTranslation('scoring')

  const ruleOf = (key: string): OcrFieldRule => rules.fields.find((rule) => rule.key === key) ?? { key, ...EMPTY_RULE }
  const setFieldRule = (rule: OcrFieldRule) =>
    onChange({ ...rules, fields: [...rules.fields.filter((item) => item.key !== rule.key), rule] })
  const setSum = (index: number, sum: OcrSumRule) =>
    onChange({ ...rules, sums: rules.sums.map((item, i) => (i === index ? sum : item)) })
  const addSum = () =>
    onChange({ ...rules, sums: [...rules.sums, { label: '', keys: [], min_value: null, max_value: null }] })
  const removeSum = (index: number) => onChange({ ...rules, sums: rules.sums.filter((_, i) => i !== index) })

  return (
    <section className="space-y-4" aria-labelledby="ocr-rules-title">
      <div>
        <h4 id="ocr-rules-title" className="font-semibold">{t('scoreSheets.rules.title')}</h4>
        <p className="text-xs text-leise">{t('scoreSheets.rules.hint')}</p>
      </div>

      <label className="block text-sm font-medium">
        {t('scoreSheets.rules.minConfidence')}
        <input
          className="input mt-1 w-28"
          type="number"
          min={0}
          max={100}
          step={1}
          value={toPercent(rules.min_confidence)}
          onChange={(e) => onChange({ ...rules, min_confidence: fromPercent(e.target.value) ?? 0 })}
        />
      </label>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">{t('scoreSheets.rules.fieldRules')}</caption>
          <thead>
            <tr className="text-left text-fg">
              <th scope="col" className="py-1 pr-2 font-semibold">{t('scoreSheets.layout.field')}</th>
              <th scope="col" className="py-1 pr-2 font-semibold">{t('scoreSheets.rules.min')}</th>
              <th scope="col" className="py-1 pr-2 font-semibold">{t('scoreSheets.rules.max')}</th>
              <th scope="col" className="py-1 pr-2 font-semibold">{t('scoreSheets.rules.integer')}</th>
              <th scope="col" className="py-1 pr-2 font-semibold">{t('scoreSheets.rules.fieldConfidence')}</th>
            </tr>
          </thead>
          <tbody>
            {fields.map((field) => {
              const rule = ruleOf(field.key)
              const numeric = field.type !== 'boolean'
              return (
                <tr key={field.key} className="border-t border-rand">
                  <td className="py-1 pr-2">
                    {field.label} <span className="font-mono text-xs text-leise">{field.key}</span>
                  </td>
                  <td className="py-1 pr-2">
                    {numeric && (
                      <input
                        className="input w-20"
                        type="number"
                        aria-label={t('scoreSheets.rules.minOf', { field: field.key })}
                        value={rule.min_value ?? ''}
                        onChange={(e) => setFieldRule({ ...rule, min_value: toNumber(e.target.value) })}
                      />
                    )}
                  </td>
                  <td className="py-1 pr-2">
                    {numeric && (
                      <input
                        className="input w-20"
                        type="number"
                        aria-label={t('scoreSheets.rules.maxOf', { field: field.key })}
                        placeholder={field.max_value === null ? '' : String(field.max_value)}
                        value={rule.max_value ?? ''}
                        onChange={(e) => setFieldRule({ ...rule, max_value: toNumber(e.target.value) })}
                      />
                    )}
                  </td>
                  <td className="py-1 pr-2">
                    {numeric && (
                      <input
                        type="checkbox"
                        aria-label={t('scoreSheets.rules.integerOf', { field: field.key })}
                        checked={rule.integer}
                        onChange={(e) => setFieldRule({ ...rule, integer: e.target.checked })}
                      />
                    )}
                  </td>
                  <td className="py-1 pr-2">
                    <input
                      className="input w-20"
                      type="number"
                      min={0}
                      max={100}
                      aria-label={t('scoreSheets.rules.confidenceOf', { field: field.key })}
                      placeholder={String(toPercent(rules.min_confidence))}
                      value={toPercent(rule.min_confidence)}
                      onChange={(e) => setFieldRule({ ...rule, min_confidence: fromPercent(e.target.value) })}
                    />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <p className="mt-1 text-xs text-leise">{t('scoreSheets.rules.fieldHint')}</p>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h5 className="text-sm font-semibold">{t('scoreSheets.rules.sums')}</h5>
          <button type="button" className="btn-secondary flex items-center gap-1 text-sm" onClick={addSum}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('scoreSheets.rules.addSum')}
          </button>
        </div>
        {rules.sums.length === 0 && <p className="text-xs text-leise">{t('scoreSheets.rules.noSums')}</p>}
        {rules.sums.map((sum, index) => (
          <fieldset key={index} className="rounded border border-rand p-3">
            <legend className="px-1 text-xs text-leise">{t('scoreSheets.rules.sumNumber', { number: index + 1 })}</legend>
            <div className="flex flex-wrap items-end gap-3 text-sm">
              <label className="font-medium">
                {t('scoreSheets.rules.sumLabel')}
                <input className="input mt-1 w-48" value={sum.label} maxLength={100} onChange={(e) => setSum(index, { ...sum, label: e.target.value })} />
              </label>
              <label className="font-medium">
                {t('scoreSheets.rules.min')}
                <input className="input mt-1 w-24" type="number" value={sum.min_value ?? ''} onChange={(e) => setSum(index, { ...sum, min_value: toNumber(e.target.value) })} />
              </label>
              <label className="font-medium">
                {t('scoreSheets.rules.max')}
                <input className="input mt-1 w-24" type="number" value={sum.max_value ?? ''} onChange={(e) => setSum(index, { ...sum, max_value: toNumber(e.target.value) })} />
              </label>
              <button
                type="button"
                className="rounded p-1 text-danger hover:bg-danger/10"
                aria-label={t('scoreSheets.rules.removeSum', { number: index + 1 })}
                onClick={() => removeSum(index)}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm" role="group" aria-label={t('scoreSheets.rules.sumFields')}>
              {fields.map((field) => (
                <label key={field.key} className="flex items-center gap-1">
                  <input
                    type="checkbox"
                    checked={sum.keys.includes(field.key)}
                    onChange={(e) =>
                      setSum(index, {
                        ...sum,
                        keys: e.target.checked ? [...sum.keys, field.key] : sum.keys.filter((key) => key !== field.key),
                      })
                    }
                  />
                  {field.label}
                </label>
              ))}
            </div>
          </fieldset>
        ))}
      </div>
    </section>
  )
}

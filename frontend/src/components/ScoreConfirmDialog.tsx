import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import Modal from "@/components/Modal";
import { formatNumber } from "@/i18n/format";

export interface ScoreSummaryField {
  key: string;
  label: string;
  multiplier: number;
  type: string;
}

interface Props {
  open: boolean;
  title?: string;
  /** Team / match lines shown above the field table. */
  context: Array<[string, string]>;
  fields: ScoreSummaryField[];
  values: Record<string, number | boolean | undefined>;
  total: number;
  offline?: boolean;
  pending?: boolean;
  /**
   * A problem to point out before sending (e.g. the round is already
   * recorded); with `blocked` the entry cannot be submitted as it is and
   * `action` offers the way out (e.g. correct the existing entry).
   */
  warning?: string;
  blocked?: boolean;
  action?: ReactNode;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Last check before an official score is submitted (spec 09 "Bestätigung vor dem Absenden"). */
export default function ScoreConfirmDialog({ open, title, context, fields, values, total, offline, pending, warning, blocked, action, onConfirm, onCancel }: Props) {
  const { t } = useTranslation();
  const two = { minimumFractionDigits: 2, maximumFractionDigits: 2 };
  return (
    <Modal open={open} title={title ?? t("scoreConfirm.title")} onClose={onCancel}>
      <dl className="mb-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        {context.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-leise">{label}</dt>
            <dd className="font-medium">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="table-scroll">
      <table className="mb-4 w-full text-sm">
        <thead>
          <tr className="border-b">
            <th className="py-1 text-left font-semibold">{t("scoreConfirm.field")}</th>
            <th className="py-1 text-right font-semibold">{t("scoreConfirm.value")}</th>
            <th className="py-1 text-right font-semibold">{t("scoreConfirm.points")}</th>
          </tr>
        </thead>
        <tbody>
          {fields.map((field) => {
            const raw = values[field.key];
            const numeric = Number(raw ?? 0);
            const shown = field.type === "boolean" ? (raw ? t("yes") : t("no")) : String(raw ?? 0);
            return (
              <tr key={field.key} className="border-b last:border-0">
                <td className="py-1">{field.label}</td>
                <td className="py-1 text-right">{shown}</td>
                <td className="py-1 text-right">{formatNumber(numeric * field.multiplier, two)}</td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row" colSpan={2} className="pt-2 text-left">{t("scoreConfirm.total")}</th>
            <td className="pt-2 text-right text-lg font-bold" data-testid="confirm-total">{formatNumber(total, two)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
      {warning && (
        <div role="alert" className={`mb-4 rounded-lg p-2 text-sm ${blocked ? "bg-danger/[0.07] text-danger" : "bg-warning/10 text-warning"}`}>
          <p>{warning}</p>
          {action && <div className="mt-2">{action}</div>}
        </div>
      )}
      {offline && (
        <p className="mb-4 rounded-lg bg-warning/10 p-2 text-sm text-warning">
          {t("scoreConfirm.offline")}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <button type="button" className="btn-secondary" onClick={onCancel}>{t("scoreConfirm.correct")}</button>
        <button type="button" className="btn-primary" disabled={pending || blocked} onClick={onConfirm}>
          {blocked ? t("scoreConfirm.cannotSubmit") : offline ? t("scoreConfirm.saveLocally") : t("scoreConfirm.submit")}
        </button>
      </div>
    </Modal>
  );
}

import Modal from "@/components/Modal";

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
  onConfirm: () => void;
  onCancel: () => void;
}

/** Last check before an official score is submitted (spec 09 "Bestätigung vor dem Absenden"). */
export default function ScoreConfirmDialog({ open, title = "Wertung bestätigen", context, fields, values, total, offline, pending, onConfirm, onCancel }: Props) {
  return (
    <Modal open={open} title={title} onClose={onCancel}>
      <dl className="mb-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        {context.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-gray-500">{label}</dt>
            <dd className="font-medium">{value}</dd>
          </div>
        ))}
      </dl>
      <table className="mb-4 w-full text-sm">
        <thead>
          <tr className="border-b dark:border-gray-700">
            <th className="py-1 text-left font-medium">Feld</th>
            <th className="py-1 text-right font-medium">Wert</th>
            <th className="py-1 text-right font-medium">Punkte</th>
          </tr>
        </thead>
        <tbody>
          {fields.map((field) => {
            const raw = values[field.key];
            const numeric = Number(raw ?? 0);
            const shown = field.type === "boolean" ? (raw ? "Ja" : "Nein") : String(raw ?? 0);
            return (
              <tr key={field.key} className="border-b last:border-0 dark:border-gray-800">
                <td className="py-1">{field.label}</td>
                <td className="py-1 text-right">{shown}</td>
                <td className="py-1 text-right">{(numeric * field.multiplier).toFixed(2)}</td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row" colSpan={2} className="pt-2 text-left">Gesamt</th>
            <td className="pt-2 text-right text-lg font-bold" data-testid="confirm-total">{total.toFixed(2)}</td>
          </tr>
        </tfoot>
      </table>
      {offline && (
        <p className="mb-4 rounded-lg bg-amber-100 p-2 text-sm text-amber-900">
          Offline: Die Wertung wird auf diesem Gerät gespeichert und automatisch übertragen, sobald wieder eine Verbindung besteht.
        </p>
      )}
      <div className="flex justify-end gap-2">
        <button type="button" className="btn-secondary" onClick={onCancel}>Korrigieren</button>
        <button type="button" className="btn-primary" disabled={pending} onClick={onConfirm}>
          {offline ? "Lokal speichern" : "Verbindlich absenden"}
        </button>
      </div>
    </Modal>
  );
}

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import Modal from "@/components/Modal";
import type { ChecklistItem } from "./types";

interface Props {
  open: boolean;
  items: ChecklistItem[];
  pending?: boolean;
  error?: string;
  onCancel: () => void;
  onConfirm: (checklist: Record<string, boolean>) => void;
}

/** The season's referee checklist, ticked by the juror before a score is confirmed. */
export default function ChecklistConfirmDialog({ open, items, pending, error, onCancel, onConfirm }: Props) {
  const { t } = useTranslation("scoring");
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  useEffect(() => { if (open) setChecked({}); }, [open]);
  const missing = items.filter((item) => item.required && !checked[item.key]);
  return (
    <Modal open={open} title={t("rules.checklist")} onClose={onCancel}>
      <ul className="space-y-2">
        {items.map((item) => (
          <li key={item.key}>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={!!checked[item.key]} onChange={(e) => setChecked({ ...checked, [item.key]: e.target.checked })} />
              {item.label}{item.required && <span className="text-red-600" aria-label={t("rules.required")}>*</span>}
            </label>
          </li>
        ))}
      </ul>
      {error && <p role="alert" className="mt-3 text-sm text-red-600">{error}</p>}
      <div className="mt-4 flex justify-end gap-2">
        <button type="button" className="btn-secondary" onClick={onCancel}>{t("common:cancel")}</button>
        <button type="button" className="btn-primary" disabled={missing.length > 0 || pending} onClick={() => onConfirm(checked)}>{t("rules.confirmScore")}</button>
      </div>
    </Modal>
  );
}

import { useRef } from "react";
import { useTranslation } from "react-i18next";
import Modal from "@/components/Modal";
import { useConfirmStore } from "@/lib/confirm";

/** Renders the dialog of confirmAction() (lib/confirm). Mounted once in App. */
export default function ConfirmHost() {
  const { t } = useTranslation();
  const { pending, settle } = useConfirmStore();
  // Cancel is focused first: Enter on a destructive dialog must not delete.
  const cancelRef = useRef<HTMLButtonElement>(null);
  const danger = pending?.tone === "danger";
  return (
    <Modal open={!!pending} title={pending?.title ?? t("confirmDialog.title")} onClose={() => settle(false)} initialFocus={cancelRef}>
      <p className="whitespace-pre-line text-sm text-fg">{pending?.message}</p>
      <div className="mt-6 flex flex-wrap justify-end gap-2">
        <button ref={cancelRef} type="button" className="btn-secondary" onClick={() => settle(false)}>
          {pending?.cancelLabel ?? t("cancel")}
        </button>
        <button type="button" className={danger ? "btn-danger" : "btn-primary"} onClick={() => settle(true)}>
          {pending?.confirmLabel ?? (danger ? t("delete") : t("confirm"))}
        </button>
      </div>
    </Modal>
  );
}

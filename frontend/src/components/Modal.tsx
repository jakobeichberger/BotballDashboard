import { type ReactNode, useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";

interface ModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  /** Element to focus first (default: the first form field, else the dialog). */
  initialFocus?: React.RefObject<HTMLElement>;
  /** Wider dialogs, e.g. for tables. */
  size?: "md" | "lg";
}

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type=hidden])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

// Open dialogs, innermost last: only that one reacts to Escape and Tab, and
// everything else in <body> is inert (not focusable, hidden from screen readers).
const stack: HTMLElement[] = [];

function applyInert() {
  const top = stack[stack.length - 1];
  for (const child of Array.from(document.body.children)) {
    // Live regions (toasts) stay reachable so their messages are announced.
    if (!(child instanceof HTMLElement) || child.hasAttribute("data-inert-exempt")) continue;
    // inert also hides the subtree from assistive technology.
    if (top && child !== top) child.setAttribute("inert", "");
    else child.removeAttribute("inert");
  }
}

function focusables(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => !el.closest("[inert]"));
}

/**
 * Accessible modal dialog: moves focus into the dialog, keeps Tab inside it,
 * closes on Escape or a click on the backdrop, makes the rest of the page
 * inert and gives focus back to the element that opened it.
 */
export default function Modal({ open, title, onClose, children, initialFocus, size = "md" }: ModalProps) {
  const { t } = useTranslation();
  const titleId = useId();
  const dialogRef = useRef<HTMLElement>(null);
  const layerRef = useRef<HTMLDivElement | null>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const wasOpen = useRef(false);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  if (open && !layerRef.current && typeof document !== "undefined") {
    layerRef.current = document.createElement("div");
    layerRef.current.dataset.modalLayer = "";
  }
  // The element that opened the dialog gets the focus back afterwards.
  if (open && !wasOpen.current && typeof document !== "undefined") {
    openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  }
  wasOpen.current = open;

  useEffect(() => {
    const layer = layerRef.current;
    if (!open || !layer) return;
    const opener = openerRef.current;
    document.body.appendChild(layer);
    stack.push(layer);
    applyInert();

    const dialog = dialogRef.current;
    const first = initialFocus?.current ?? (dialog ? dialog.querySelector<HTMLElement>("input:not([disabled]):not([type=hidden]),select:not([disabled]),textarea:not([disabled])") : null);
    (first ?? dialog)?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (stack[stack.length - 1] !== layer || !dialog) return;
      if (event.key === "Escape") {
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusables(dialog);
      if (items.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const firstItem = items[0];
      const lastItem = items[items.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === firstItem || active === dialog)) {
        event.preventDefault();
        lastItem.focus();
      } else if (!event.shiftKey && active === lastItem) {
        event.preventDefault();
        firstItem.focus();
      } else if (!dialog.contains(active)) {
        event.preventDefault();
        firstItem.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      const index = stack.indexOf(layer);
      if (index >= 0) stack.splice(index, 1);
      layer.remove();
      applyInert();
      // Back to where the user was, unless focus already moved elsewhere.
      if (opener?.isConnected && (!document.activeElement || document.activeElement === document.body)) opener.focus();
    };
    // initialFocus is read once when the dialog opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open || !layerRef.current) return null;
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-tief/60 p-4 backdrop-blur-[2px]"
      role="presentation"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <section
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={`card reveal max-h-[90vh] w-full overflow-y-auto p-5 shadow-tief outline-none sm:p-6 ${size === "lg" ? "max-w-3xl" : "max-w-lg"}`}
      >
        <div className="mb-5 flex items-center justify-between gap-2 border-b border-rand pb-3">
          <h2 id={titleId} className="font-display text-xl font-bold tracking-display">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("close")}
            className="btn-icon -mr-1 border-transparent"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>
        {children}
      </section>
    </div>,
    layerRef.current,
  );
}

import { useState } from "react";
import { createPortal } from "react-dom";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import clsx from "clsx";
import { useToastStore } from "@/lib/toast";

const ICON = { success: CheckCircle2, error: AlertCircle, info: Info } as const;

function toastLayer(): HTMLElement | null {
  if (typeof document === "undefined") return null;
  let layer = document.getElementById("toast-layer");
  if (!layer) {
    layer = document.createElement("div");
    layer.id = "toast-layer";
    // An open dialog makes the rest of the page inert, but not the toasts.
    layer.setAttribute("data-inert-exempt", "");
    document.body.appendChild(layer);
  }
  return layer;
}

/** Toast outlet (lib/toast). Errors are announced assertively, the rest politely. */
export default function Toaster() {
  const { t } = useTranslation();
  const { toasts, dismiss } = useToastStore();
  const [layer] = useState(toastLayer);
  if (!layer) return null;
  return createPortal(
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-[60] flex flex-col items-center gap-2 p-4 sm:items-end">
      {toasts.map((item) => {
        const Icon = ICON[item.tone];
        return (
          <div
            key={item.id}
            role={item.tone === "error" ? "alert" : "status"}
            className={clsx(
              "reveal pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-karte border border-l-4 bg-flaeche p-3 pl-3.5 text-sm text-fg shadow-tief",
              item.tone === "error" && "border-danger/40 border-l-danger",
              item.tone === "success" && "border-success/40 border-l-success",
              item.tone === "info" && "border-rand border-l-info",
            )}
          >
            <Icon
              className={clsx(
                "mt-0.5 h-4 w-4 shrink-0",
                item.tone === "error" ? "text-danger" : item.tone === "success" ? "text-success" : "text-info",
              )}
              aria-hidden="true"
            />
            <p className="min-w-0 flex-1 break-words font-medium">{item.message}</p>
            <button
              type="button"
              onClick={() => dismiss(item.id)}
              aria-label={t("close")}
              className="-m-2 grid h-11 w-11 shrink-0 place-items-center rounded opacity-70 hover:opacity-100"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        );
      })}
    </div>,
    layer,
  );
}

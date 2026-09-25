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
              "pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-lg border p-3 text-sm shadow-lg",
              item.tone === "error" && "border-red-200 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-100",
              item.tone === "success" && "border-green-200 bg-green-50 text-green-900 dark:border-green-800 dark:bg-green-950 dark:text-green-100",
              item.tone === "info" && "border-gray-200 bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100",
            )}
          >
            <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <p className="min-w-0 flex-1 break-words">{item.message}</p>
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

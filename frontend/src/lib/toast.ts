/**
 * Non-blocking notifications (instead of window.alert). Rendered by
 * <Toaster/> in App; callable from anywhere, including mutation callbacks.
 */
import { create } from "zustand";
import { apiErrorMessage } from "@/lib/errors";

export type ToastTone = "success" | "error" | "info";

export interface Toast {
  id: number;
  tone: ToastTone;
  message: string;
}

interface ToastState {
  toasts: Toast[];
  push: (tone: ToastTone, message: string) => number;
  dismiss: (id: number) => void;
}

/** How long a toast stays; errors stay longer so they can be read. */
const DURATION_MS: Record<ToastTone, number> = { success: 4000, info: 5000, error: 8000 };
const MAX_TOASTS = 4;

let nextId = 1;

export const useToastStore = create<ToastState>((set, get) => ({
  toasts: [],
  push: (tone, message) => {
    const id = nextId++;
    // The same message twice in a row (double click) is shown once.
    const toasts = get().toasts.filter((item) => item.message !== message);
    set({ toasts: [...toasts, { id, tone, message }].slice(-MAX_TOASTS) });
    if (typeof window !== "undefined") window.setTimeout(() => get().dismiss(id), DURATION_MS[tone]);
    return id;
  },
  dismiss: (id) => set({ toasts: get().toasts.filter((item) => item.id !== id) }),
}));

export const toast = {
  success: (message: string) => useToastStore.getState().push("success", message),
  info: (message: string) => useToastStore.getState().push("info", message),
  error: (message: string) => useToastStore.getState().push("error", message),
  /** Error toast for a failed API call, translated (lib/errors). */
  apiError: (error: unknown, fallback?: string) => useToastStore.getState().push("error", apiErrorMessage(error, fallback)),
};

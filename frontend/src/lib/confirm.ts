/**
 * Promise-based confirmation dialog (instead of window.confirm), rendered by
 * <ConfirmHost/> in App:
 *
 *   if (await confirmAction({ message, tone: "danger" })) remove.mutate(id);
 */
import { create } from "zustand";

export interface ConfirmOptions {
  message: string;
  /** Dialog title; defaults to "Please confirm". */
  title?: string;
  /** Label of the confirming button; defaults to "Confirm" (or "Delete" for danger). */
  confirmLabel?: string;
  cancelLabel?: string;
  /** Destructive actions get a red button. */
  tone?: "danger" | "default";
}

interface PendingConfirm extends ConfirmOptions {
  resolve: (confirmed: boolean) => void;
}

interface ConfirmState {
  pending: PendingConfirm | null;
  settle: (confirmed: boolean) => void;
}

export const useConfirmStore = create<ConfirmState>((set, get) => ({
  pending: null,
  settle: (confirmed) => {
    const pending = get().pending;
    set({ pending: null });
    pending?.resolve(confirmed);
  },
}));

/** Ask the user; resolves true when they confirm, false on cancel/Escape. */
export function confirmAction(options: ConfirmOptions): Promise<boolean> {
  // A second request replaces the first, which counts as cancelled.
  useConfirmStore.getState().pending?.resolve(false);
  return new Promise((resolve) => useConfirmStore.setState({ pending: { ...options, resolve } }));
}

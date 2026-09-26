import { useEffect } from "react";

/**
 * Ask the browser to confirm closing or reloading the tab while a form has
 * unsaved edits (the browser shows its own, generic text). Navigation inside
 * the app is not intercepted: the app uses <BrowserRouter>, which has no
 * route blocker.
 */
export function useUnsavedChangesWarning(dirty: boolean): void {
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      // Older browsers need returnValue set to show the prompt.
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
}

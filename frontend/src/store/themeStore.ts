import { create } from "zustand";
import { persist } from "zustand/middleware";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

export type Theme = "light" | "dark" | "system";

const THEMES: readonly Theme[] = ["light", "dark", "system"];

export function isTheme(value: unknown): value is Theme {
  return typeof value === "string" && (THEMES as readonly string[]).includes(value);
}

interface ThemeState {
  theme: Theme;
  /** Change the theme and, when signed in, store it in the profile (User.theme). */
  setTheme: (theme: Theme) => void;
  /** Apply the theme loaded from the profile without writing it back. */
  syncFromProfile: (theme: string | null | undefined) => void;
}

function applyTheme(theme: Theme) {
  const isDark =
    theme === "dark" ||
    (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  const root = document.documentElement;
  root.classList.toggle("dark", isDark);
  // data-theme mirrors the class for CSS that keys on the attribute.
  root.dataset.theme = isDark ? "dark" : "light";
  // Browser chrome follows the app theme, not only the system preference
  // (index.html: papier #F2F2F2 / tief #0D0F13).
  document
    .querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')
    .forEach((meta) => meta.setAttribute("content", isDark ? "#0D0F13" : "#F2F2F2"));
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: "system",
      setTheme: (theme) => {
        set({ theme });
        applyTheme(theme);
        // localStorage keeps the choice for this browser; the profile carries
        // it to every other device the user signs in on.
        if (useAuthStore.getState().accessToken) {
          api.patch("/auth/me", { theme }).catch(() => undefined);
        }
      },
      syncFromProfile: (theme) => {
        if (!isTheme(theme) || theme === get().theme) return;
        set({ theme });
        applyTheme(theme);
      },
    }),
    { name: "botball-theme", partialize: (state) => ({ theme: state.theme }) }
  )
);

// Apply on load
if (typeof window !== "undefined") {
  const stored = localStorage.getItem("botball-theme");
  const theme: Theme = stored ? JSON.parse(stored).state?.theme ?? "system" : "system";
  applyTheme(theme);

  // Watch system preference
  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", () => {
      if (useThemeStore.getState().theme === "system") applyTheme("system");
    });
}

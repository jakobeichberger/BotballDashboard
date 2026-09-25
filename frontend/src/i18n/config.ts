import i18n, { type Resource } from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { useAuthStore } from "@/store/authStore";

export const SUPPORTED_LANGUAGES = ["de", "en"] as const;
export type Language = (typeof SUPPORTED_LANGUAGES)[number];

// Every locales/<lng>/<namespace>.json file is bundled; adding a namespace only
// needs the two JSON files (see __tests__/i18n for the key-parity checks).
const files = import.meta.glob<{ default: Record<string, unknown> }>("./locales/*/*.json", { eager: true });
const resources: Resource = {};
for (const [path, module] of Object.entries(files)) {
  const match = /\.\/locales\/(\w+)\/(\w+)\.json$/.exec(path);
  if (!match) continue;
  const [, lng, ns] = match;
  resources[lng] = { ...resources[lng], [ns]: module.default };
}
export const namespaces = Object.keys(resources.en ?? {});

export function isSupportedLanguage(value: unknown): value is Language {
  return typeof value === "string" && (SUPPORTED_LANGUAGES as readonly string[]).includes(value);
}

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    // Spec: a missing translation falls back to English.
    fallbackLng: "en",
    supportedLngs: [...SUPPORTED_LANGUAGES],
    nonExplicitSupportedLngs: true,
    load: "languageOnly",
    ns: namespaces,
    defaultNS: "common",
    fallbackNS: "common",
    // Detection before login: the language last used on this device (written
    // whenever the profile language is applied), then the browser. After login
    // the profile language wins, see the store subscription below.
    detection: {
      order: ["localStorage", "navigator"],
      caches: ["localStorage"],
    },
    interpolation: {
      escapeValue: false,
    },
  });

function applyDocumentLanguage(lng: string) {
  if (typeof document !== "undefined") document.documentElement.lang = lng.split("-")[0];
}
applyDocumentLanguage(i18n.language ?? "en");
i18n.on("languageChanged", applyDocumentLanguage);

// The user profile (User.preferred_language) is the source of truth once it is
// known, so the choice follows the user across devices.
useAuthStore.subscribe((state, previous) => {
  const language = state.user?.preferred_language;
  if (language === previous.user?.preferred_language || !isSupportedLanguage(language)) return;
  if (i18n.resolvedLanguage !== language) void i18n.changeLanguage(language);
});

/** The active UI language, reduced to one of the supported codes. */
export function currentLanguage(): Language {
  const lng = (i18n.resolvedLanguage ?? i18n.language ?? "en").split("-")[0];
  return isSupportedLanguage(lng) ? lng : "en";
}

/** Picks the active language's text from a `{ de, en }` label (module registry). */
export function localized(label: { de: string; en: string }): string {
  return label[currentLanguage()];
}

export default i18n;

import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import resourcesToBackend from "i18next-resources-to-backend";
import { useAuthStore } from "@/store/authStore";

export const SUPPORTED_LANGUAGES = ["de", "en"] as const;
export type Language = (typeof SUPPORTED_LANGUAGES)[number];

/**
 * The translation namespaces = the files locales/<lng>/<namespace>.json.
 * A new namespace needs both JSON files and an entry here; the i18n tests
 * check that this list matches the files.
 */
export const namespaces = [
  "analytics",
  "auth",
  "bots",
  "common",
  "dashboard",
  "events",
  "papers",
  "printing",
  "profile",
  "scoring",
  "settings",
  "teams",
];

// Each language is one lazy chunk (i18n/bundles), so only the active language
// — plus English as the fallback — is downloaded.
type Bundle = Record<string, Record<string, unknown>>;
const bundleLoaders: Record<Language, () => Promise<{ default: Bundle }>> = {
  de: () => import("./bundles/de"),
  en: () => import("./bundles/en"),
};
const bundles = new Map<string, Promise<Bundle>>();

function loadBundle(lng: string): Promise<Bundle> {
  const language: Language = isSupportedLanguage(lng) ? lng : "en";
  let bundle = bundles.get(language);
  if (!bundle) {
    bundle = bundleLoaders[language]().then((module) => module.default);
    // A failed chunk (offline without cache) may be retried later.
    bundle.catch(() => bundles.delete(language));
    bundles.set(language, bundle);
  }
  return bundle;
}

export function isSupportedLanguage(value: unknown): value is Language {
  return typeof value === "string" && (SUPPORTED_LANGUAGES as readonly string[]).includes(value);
}

/** Resolves once the detected language (and the fallback) is loaded. */
export const i18nReady = i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .use(resourcesToBackend((lng: string, ns: string) => loadBundle(lng).then((bundle) => bundle[ns] ?? {})))
  .init({
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
    react: {
      // main.tsx renders after i18nReady; a later language switch keeps the
      // old texts until the new bundle is loaded instead of suspending.
      useSuspense: false,
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

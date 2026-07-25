import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import deCommon from "./locales/de/common.json";
import deDashboard from "./locales/de/dashboard.json";
import deEvents from "./locales/de/events.json";
import enCommon from "./locales/en/common.json";
import enDashboard from "./locales/en/dashboard.json";
import enEvents from "./locales/en/events.json";

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      de: { common: deCommon, dashboard: deDashboard, events: deEvents },
      en: { common: enCommon, dashboard: enDashboard, events: enEvents },
    },
    fallbackLng: "de",
    supportedLngs: ["de", "en"],
    ns: ["common", "dashboard", "events"],
    defaultNS: "common",
    detection: {
      order: ["localStorage", "navigator"],
      caches: ["localStorage"],
    },
    interpolation: {
      escapeValue: false,
    },
  });

export default i18n;

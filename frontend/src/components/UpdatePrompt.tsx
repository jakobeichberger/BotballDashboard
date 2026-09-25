import { useRegisterSW } from "virtual:pwa-register/react";
import { RefreshCw, X } from "lucide-react";
import { useTranslation } from "react-i18next";

/** Check for a new release every hour while the app stays open (event days). */
const UPDATE_CHECK_MS = 60 * 60 * 1000;

/**
 * "New version available – reload". The new service worker waits until the
 * user agrees, so a score being entered is never interrupted by a reload;
 * updateServiceWorker() sends SKIP_WAITING (sw.ts) and reloads once the new
 * worker has taken control.
 */
export default function UpdatePrompt() {
  const { t } = useTranslation();
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegisteredSW(_url, registration) {
      if (!registration) return;
      window.setInterval(() => {
        if (navigator.onLine) void registration.update().catch(() => undefined);
      }, UPDATE_CHECK_MS);
    },
  });
  if (!needRefresh) return null;
  return (
    <div role="status" className="fixed inset-x-0 top-0 z-[55] flex justify-center p-3">
      <div className="flex w-full max-w-md items-center gap-3 rounded-lg border border-primary-200 bg-white p-3 text-sm shadow-lg dark:border-primary-800 dark:bg-gray-900">
        <p className="flex-1">{t("update.available")}</p>
        <button type="button" className="btn-primary min-h-11" onClick={() => void updateServiceWorker(true)}>
          <RefreshCw className="h-4 w-4" aria-hidden="true" /> {t("update.reload")}
        </button>
        <button
          type="button"
          className="grid h-11 w-11 place-items-center rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
          onClick={() => setNeedRefresh(false)}
          aria-label={t("update.later")}
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

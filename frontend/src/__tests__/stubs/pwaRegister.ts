// Test stand-in for vite-plugin-pwa's virtual:pwa-register/react (see vitest.config.ts).
import { useState } from "react";

export function useRegisterSW() {
  const needRefresh = useState(false);
  const offlineReady = useState(false);
  return { needRefresh, offlineReady, updateServiceWorker: async () => undefined };
}

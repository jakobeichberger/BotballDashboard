import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { clearApiCache } from "@/lib/offlineCache";
import { api } from "@/lib/api";
import {
  broadcastLogout,
  broadcastToken,
  clearPendingLogout,
  listenForSessionChanges,
  markPendingLogout,
  refreshSession,
} from "@/lib/sessionRefresh";
import { useAuthStore } from "@/store/authStore";
import { useThemeStore } from "@/store/themeStore";

let restorationStarted = false;

/** Test helper: allow useRestoreSession to run again. */
export function resetSessionRestore(): void {
  restorationStarted = false;
}

/**
 * Restore the session from the refresh cookie on app start. Without a
 * connection (or while the API is unreachable) the cached profile of this
 * device opens a read-only session instead of the login page; it is upgraded
 * once the refresh succeeds after reconnecting.
 */
export function useRestoreSession() {
  const { setSessionChecked, startOfflineSession } = useAuthStore();
  useEffect(() => {
    if (restorationStarted) return;
    restorationStarted = true;
    listenForSessionChanges();
    refreshSession()
      .then((outcome) => {
        if (outcome.status === "unauthorized") useAuthStore.getState().logout();
        if (outcome.status === "unavailable") startOfflineSession();
      })
      .catch(() => startOfflineSession())
      .finally(() => setSessionChecked(true));
  }, [setSessionChecked, startOfflineSession]);

  // Upgrade a read-only offline session as soon as the connection is back.
  const offlineSession = useAuthStore((state) => state.offlineSession);
  useEffect(() => {
    if (!offlineSession) return;
    const upgrade = () => {
      void refreshSession().then((outcome) => {
        if (outcome.status === "unauthorized") useAuthStore.getState().logout();
      });
    };
    window.addEventListener("online", upgrade);
    return () => window.removeEventListener("online", upgrade);
  }, [offlineSession]);
}

export function useCurrentUser() {
  const { accessToken, setUser } = useAuthStore();
  const query = useQuery({
    queryKey: ["auth", "me", accessToken],
    queryFn: async () => (await api.get("/auth/me")).data,
    enabled: !!accessToken,
  });
  useEffect(() => {
    if (!query.data) return;
    // Also applies the profile language (see the store subscription in i18n/config).
    setUser(query.data);
    // The profile is the source of truth across devices (User.theme).
    useThemeStore.getState().syncFromProfile(query.data.theme);
  }, [query.data, setUser]);
  return query;
}

export function useLogin() {
  const { setAccessToken, setSessionChecked } = useAuthStore();
  return async (email: string, password: string) => {
    const { data } = await api.post("/auth/login", { email, password });
    clearPendingLogout();
    setAccessToken(data.access_token);
    setSessionChecked(true);
    // The login rotated the refresh cookie: the other tabs use this token.
    broadcastToken(data.access_token);
    return data;
  };
}

export function useLogout() {
  const { logout } = useAuthStore();
  return async () => {
    try {
      await api.post("/auth/logout");
    } catch {
      // Offline or the server is down: sign out locally anyway and revoke the
      // refresh cookie once the server is reachable (lib/sessionRefresh).
      markPendingLogout();
    } finally {
      logout();
      broadcastLogout();
      // Offline copies of API data belong to this user; don't leave them behind.
      await clearApiCache();
    }
  };
}

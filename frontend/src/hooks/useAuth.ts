import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { clearApiCache } from "@/lib/offlineCache";
import { api, restoreAccessToken } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { useThemeStore } from "@/store/themeStore";

let restorationStarted = false;

export function useRestoreSession() {
  const { setAccessToken, setSessionChecked } = useAuthStore();
  useEffect(() => {
    if (restorationStarted) return;
    restorationStarted = true;
    restoreAccessToken()
      .then((token) => {
        if (token) setAccessToken(token);
      })
      .finally(() => setSessionChecked(true));
  }, [setAccessToken, setSessionChecked]);
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
    setAccessToken(data.access_token);
    setSessionChecked(true);
    return data;
  };
}

export function useLogout() {
  const { logout } = useAuthStore();
  return async () => {
    try {
      await api.post("/auth/logout");
    } finally {
      logout();
      // Offline copies of API data belong to this user; don't leave them behind.
      await clearApiCache();
    }
  };
}

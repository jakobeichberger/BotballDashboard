import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { api, restoreAccessToken } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import i18n from "@/i18n/config";

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
    setUser(query.data);
    if (query.data.preferred_language) i18n.changeLanguage(query.data.preferred_language);
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
    }
  };
}

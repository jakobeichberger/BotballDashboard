import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import i18n from "@/i18n/config";

export function useCurrentUser() {
  const { accessToken, setUser } = useAuthStore();

  const query = useQuery({
    queryKey: ["auth", "me"],
    queryFn: async () => {
      const { data } = await api.get("/auth/me");
      return data;
    },
    enabled: !!accessToken,
  });

  useEffect(() => {
    if (query.data) {
      setUser(query.data);
      if (query.data.preferred_language) {
        i18n.changeLanguage(query.data.preferred_language);
      }
    }
  }, [query.data, setUser]);

  return query;
}

export function useLogin() {
  const { setAccessToken } = useAuthStore();

  return async (email: string, password: string) => {
    const { data } = await api.post("/auth/login", { email, password });
    setAccessToken(data.access_token);
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

import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface AuthUser {
  id: string;
  email: string;
  display_name: string;
  is_superuser: boolean;
  preferred_language: string;
  theme: string;
  roles: Array<{ id: string; name: string; description: string | null }>;
}

interface AuthState {
  accessToken: string | null;
  user: AuthUser | null;
  setAccessToken: (token: string) => void;
  setUser: (user: AuthUser) => void;
  logout: () => void;
  hasRole: (role: string) => boolean;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      user: null,

      setAccessToken: (token) => set({ accessToken: token }),
      setUser: (user) => set({ user }),

      logout: () => {
        set({ accessToken: null, user: null });
      },

      hasRole: (role) => {
        const { user } = get();
        if (!user) return false;
        if (user.is_superuser) return true;
        return user.roles.some((r) => r.name === role);
      },
    }),
    {
      name: "botball-auth",
      partialize: (state) => ({ user: state.user }),
    }
  )
);

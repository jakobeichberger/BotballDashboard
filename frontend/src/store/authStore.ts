import { create } from "zustand";

export interface AuthUser {
  id: string;
  email: string;
  display_name: string;
  is_superuser: boolean;
  preferred_language: string;
  theme: string;
  roles: Array<{ id: string; name: string; description: string | null }>;
  permissions?: string[];
}

interface AuthState {
  accessToken: string | null;
  user: AuthUser | null;
  sessionChecked: boolean;
  setAccessToken: (token: string) => void;
  setUser: (user: AuthUser) => void;
  setSessionChecked: (checked: boolean) => void;
  logout: () => void;
  hasRole: (role: string) => boolean;
  hasPermission: (permission: string) => boolean;
}

// Remove tokens persisted by older releases. Access tokens now live in memory only.
localStorage.removeItem("botball-auth");

export const useAuthStore = create<AuthState>((set, get) => ({
  accessToken: null,
  user: null,
  sessionChecked: false,
  setAccessToken: (token) => set({ accessToken: token }),
  setUser: (user) => set({ user }),
  setSessionChecked: (sessionChecked) => set({ sessionChecked }),
  logout: () => set({ accessToken: null, user: null, sessionChecked: true }),
  hasRole: (role) => {
    const { user } = get();
    return !!user && (user.is_superuser || user.roles.some((item) => item.name === role));
  },
  hasPermission: (permission) => {
    const { user } = get();
    return !!user && (user.is_superuser || !!user.permissions?.includes(permission));
  },
}));

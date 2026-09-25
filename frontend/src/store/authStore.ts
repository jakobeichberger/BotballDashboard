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
  /**
   * Read-only session from the cached profile: the app started without a
   * connection, so no access token could be fetched. Reads come from the
   * service worker cache and scores go to the offline queue; the session is
   * upgraded as soon as a refresh succeeds (see useRestoreSession).
   */
  offlineSession: boolean;
  setAccessToken: (token: string) => void;
  setUser: (user: AuthUser) => void;
  setSessionChecked: (checked: boolean) => void;
  /** Start the read-only offline session; false when no profile is cached. */
  startOfflineSession: () => boolean;
  logout: () => void;
  hasRole: (role: string) => boolean;
  hasPermission: (permission: string) => boolean;
}

// Remove tokens persisted by older releases. Access tokens now live in memory only.
safeStorage(() => localStorage.removeItem("botball-auth"));

/** The last profile of this device, for an offline cold start. Never a token. */
export const PROFILE_CACHE_KEY = "botball-profile";

function safeStorage<T>(action: () => T): T | undefined {
  try {
    return action();
  } catch {
    // Storage disabled (private mode, quota) — the cache is only a convenience.
    return undefined;
  }
}

function cacheProfile(user: AuthUser | null): void {
  safeStorage(() => {
    if (!user) {
      localStorage.removeItem(PROFILE_CACHE_KEY);
      return;
    }
    const { id, email, display_name, is_superuser, preferred_language, theme, roles, permissions } = user;
    localStorage.setItem(
      PROFILE_CACHE_KEY,
      JSON.stringify({ id, email, display_name, is_superuser, preferred_language, theme, roles, permissions }),
    );
  });
}

export function cachedProfile(): AuthUser | null {
  const raw = safeStorage(() => localStorage.getItem(PROFILE_CACHE_KEY));
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as AuthUser;
    return typeof parsed?.id === "string" && Array.isArray(parsed.roles) ? parsed : null;
  } catch {
    return null;
  }
}

export const useAuthStore = create<AuthState>((set, get) => ({
  accessToken: null,
  user: null,
  sessionChecked: false,
  offlineSession: false,
  setAccessToken: (token) => set({ accessToken: token, offlineSession: false }),
  setUser: (user) => {
    cacheProfile(user);
    set({ user });
  },
  setSessionChecked: (sessionChecked) => set({ sessionChecked }),
  startOfflineSession: () => {
    const user = cachedProfile();
    if (!user) return false;
    set({ user, offlineSession: true, sessionChecked: true });
    return true;
  },
  logout: () => {
    cacheProfile(null);
    set({ accessToken: null, user: null, sessionChecked: true, offlineSession: false });
  },
  hasRole: (role) => {
    const { user } = get();
    return !!user && (user.is_superuser || user.roles.some((item) => item.name === role));
  },
  hasPermission: (permission) => {
    const { user } = get();
    return !!user && (user.is_superuser || !!user.permissions?.includes(permission));
  },
}));

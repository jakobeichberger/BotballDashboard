import axios from "axios";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ProtectedRoute from "@/components/ProtectedRoute";
import { resetSessionRestore, useLogout, useRestoreSession } from "@/hooks/useAuth";
import { api } from "@/lib/api";
import { resetSessionRefresh } from "@/lib/sessionRefresh";
import { PROFILE_CACHE_KEY, useAuthStore, type AuthUser } from "@/store/authStore";

const PROFILE: AuthUser = {
  id: "u1",
  email: "juror@example.org",
  display_name: "Juror",
  is_superuser: false,
  preferred_language: "de",
  theme: "system",
  roles: [],
  permissions: ["scoring:write"],
};

function App() {
  useRestoreSession();
  const checked = useAuthStore((state) => state.sessionChecked);
  if (!checked) return <p>restoring</p>;
  return (
    <Routes>
      <Route path="/login" element={<p>Login page</p>} />
      <Route path="/scoring" element={<ProtectedRoute requirePermission="scoring:write"><p>Scoring form</p></ProtectedRoute>} />
    </Routes>
  );
}

function renderApp() {
  return render(<MemoryRouter initialEntries={["/scoring"]}><App /></MemoryRouter>);
}

beforeEach(() => {
  resetSessionRefresh();
  resetSessionRestore();
  localStorage.clear();
  useAuthStore.setState({ accessToken: null, user: null, sessionChecked: false, offlineSession: false });
});

afterEach(() => {
  vi.restoreAllMocks();
  Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
});

describe("session restore", () => {
  it("opens a read-only session from the cached profile when the API is unreachable", async () => {
    useAuthStore.getState().setUser(PROFILE);
    useAuthStore.setState({ user: null });
    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
    vi.spyOn(axios, "post").mockRejectedValue(Object.assign(new Error("Network Error"), { code: "ERR_NETWORK" }));
    renderApp();
    expect(await screen.findByText("Scoring form")).toBeInTheDocument();
    expect(useAuthStore.getState()).toMatchObject({ offlineSession: true, accessToken: null, user: { id: "u1" } });
    // Writes other than queued scores stay blocked in this session.
    await expect(api.patch("/teams/t1", { name: "x" })).rejects.toThrow("OFFLINE_WRITE_BLOCKED");
  });

  it("goes to the login without a cached profile", async () => {
    vi.spyOn(axios, "post").mockRejectedValue(Object.assign(new Error("Network Error"), { code: "ERR_NETWORK" }));
    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
    renderApp();
    expect(await screen.findByText("Login page")).toBeInTheDocument();
  });

  it("drops the cached profile when the refresh cookie is rejected", async () => {
    useAuthStore.getState().setUser(PROFILE);
    vi.spyOn(axios, "post").mockRejectedValue({ response: { status: 401, data: {} } });
    renderApp();
    expect(await screen.findByText("Login page")).toBeInTheDocument();
    expect(localStorage.getItem(PROFILE_CACHE_KEY)).toBeNull();
  });
});

describe("logout", () => {
  it("signs out locally when offline and revokes the cookie on the next start", async () => {
    useAuthStore.setState({ accessToken: "tok", user: PROFILE });
    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
    let logout: () => Promise<void> = async () => undefined;
    function Harness() {
      logout = useLogout();
      return null;
    }
    render(<Harness />);
    // No unhandled rejection although the request cannot be sent.
    await expect(logout()).resolves.toBeUndefined();
    expect(useAuthStore.getState().accessToken).toBeNull();

    // Back online: the refresh cookie must not restore the session.
    Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
    const post = vi.spyOn(axios, "post").mockResolvedValue({ data: {} });
    renderApp();
    expect(await screen.findByText("Login page")).toBeInTheDocument();
    await waitFor(() => expect(post).toHaveBeenCalledWith(expect.stringMatching(/\/auth\/logout$/), {}, expect.anything()));
    expect(post).not.toHaveBeenCalledWith(expect.stringMatching(/\/auth\/refresh$/), expect.anything(), expect.anything());
  });
});

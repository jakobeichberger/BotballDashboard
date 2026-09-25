import { describe, it, expect, beforeEach, vi } from "vitest";
import { useThemeStore } from "@/store/themeStore";
import { useAuthStore } from "@/store/authStore";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({ api: { patch: vi.fn(() => Promise.resolve({ data: {} })) } }));

describe("themeStore", () => {
  beforeEach(() => {
    useThemeStore.setState({ theme: "system" });
    useAuthStore.setState({ accessToken: null });
    document.documentElement.classList.remove("dark");
    vi.clearAllMocks();
  });

  it("defaults to system theme", () => {
    expect(useThemeStore.getState().theme).toBe("system");
  });

  it("setTheme to light removes dark class", () => {
    document.documentElement.classList.add("dark");
    useThemeStore.getState().setTheme("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(useThemeStore.getState().theme).toBe("light");
  });

  it("setTheme to dark adds dark class", () => {
    useThemeStore.getState().setTheme("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(useThemeStore.getState().theme).toBe("dark");
  });

  it("setTheme to system uses matchMedia preference", () => {
    // matchMedia returns matches: false (mocked in setup.ts)
    useThemeStore.getState().setTheme("system");
    // matchMedia returns false → no dark class
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("persists the theme to the profile when signed in", () => {
    useAuthStore.setState({ accessToken: "token" });
    useThemeStore.getState().setTheme("dark");
    expect(api.patch).toHaveBeenCalledWith("/auth/me", { theme: "dark" });
  });

  it("does not call the API when signed out", () => {
    useThemeStore.getState().setTheme("dark");
    expect(api.patch).not.toHaveBeenCalled();
  });

  it("syncFromProfile applies the stored theme without writing it back", () => {
    useAuthStore.setState({ accessToken: "token" });
    useThemeStore.getState().syncFromProfile("dark");
    expect(useThemeStore.getState().theme).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(api.patch).not.toHaveBeenCalled();
    useThemeStore.getState().syncFromProfile("bogus");
    expect(useThemeStore.getState().theme).toBe("dark");
  });
});

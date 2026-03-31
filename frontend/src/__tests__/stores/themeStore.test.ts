import { describe, it, expect, beforeEach } from "vitest";
import { useThemeStore } from "@/store/themeStore";

describe("themeStore", () => {
  beforeEach(() => {
    useThemeStore.setState({ theme: "system" });
    document.documentElement.classList.remove("dark");
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
});

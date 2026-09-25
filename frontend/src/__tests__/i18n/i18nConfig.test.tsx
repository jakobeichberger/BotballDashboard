import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import i18n, { currentLanguage, localized } from "@/i18n/config";
import { formatDate, formatNumber, formatScore } from "@/i18n/format";
import { passwordProblem } from "@/lib/passwordPolicy";
import { PAPER_STATUS_LABEL } from "@/modules/papers/paperMeta";
import { useAuthStore, type AuthUser } from "@/store/authStore";
import LoginPage from "@/pages/LoginPage";

const user = (preferred_language: string): AuthUser => ({
  id: "u1",
  email: "u@example.org",
  display_name: "U",
  is_superuser: false,
  preferred_language,
  theme: "system",
  roles: [],
});

afterEach(() => {
  useAuthStore.setState({ user: null, accessToken: null });
});

describe("i18n configuration", () => {
  it("falls back to English and supports de/en", () => {
    expect(i18n.options.fallbackLng).toEqual(["en"]);
    expect(i18n.options.supportedLngs).toEqual(expect.arrayContaining(["de", "en"]));
  });

  it("follows the profile language of the signed-in user", async () => {
    useAuthStore.getState().setUser(user("en"));
    await vi.waitFor(() => expect(currentLanguage()).toBe("en"));
    expect(document.documentElement.lang).toBe("en");
    useAuthStore.getState().setUser(user("de"));
    await vi.waitFor(() => expect(currentLanguage()).toBe("de"));
  });

  it("ignores unsupported profile languages", async () => {
    useAuthStore.getState().setUser(user("fr"));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(currentLanguage()).toBe("de");
  });

  it("translates module-level labels and messages on access", async () => {
    expect(PAPER_STATUS_LABEL.accepted).toBe("Angenommen");
    expect(passwordProblem("short")).toContain("mindestens 10 Zeichen");
    await i18n.changeLanguage("en");
    expect(PAPER_STATUS_LABEL.accepted).toBe("Accepted");
    expect(passwordProblem("short")).toContain("at least 10 characters");
    expect(localized({ de: "Wertung", en: "Scoring" })).toBe("Scoring");
  });

  it("formats dates and numbers for the active language", async () => {
    expect(formatDate("2026-09-25")).toBe("25.9.2026");
    // de-AT groups thousands with a (narrow no-break) space.
    expect(formatScore(1234.5)).toMatch(/^1\s234,50$/);
    await i18n.changeLanguage("en");
    expect(formatDate("2026-09-25")).toBe("25/09/2026");
    expect(formatScore(1234.5)).toBe("1,234.50");
    expect(formatNumber(null)).toBe("—");
  });

  it("renders pages in the active language", async () => {
    await i18n.changeLanguage("en");
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <LoginPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByText("Forgot password?")).toBeInTheDocument();
  });
});

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { axe, toHaveNoViolations } from "jest-axe";
import Layout from "@/components/Layout";
import { useAuthStore } from "@/store/authStore";

expect.extend(toHaveNoViolations);

vi.mock("react-i18next", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-i18next")>();
  return { ...actual, useTranslation: () => ({ t: (k: string) => k }) as any };
});

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<h1>Inhalt</h1>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

describe("Layout accessibility", () => {
  beforeEach(() => {
    useAuthStore.setState({
      accessToken: "tok",
      user: { id: "u1", display_name: "Dev Admin", is_superuser: true, roles: [] } as any,
    });
  });

  it("labels the primary navigation landmark", () => {
    renderLayout();
    expect(screen.getByRole("navigation", { name: "Hauptnavigation" })).toBeInTheDocument();
  });

  it("gives the language and theme toggles action-describing names", () => {
    renderLayout();
    expect(screen.getByRole("button", { name: /sprache wechseln/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /design wechseln/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /abmelden/i })).toBeInTheDocument();
  });

  it("renders content inside a main landmark", () => {
    renderLayout();
    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    const { container } = renderLayout();
    expect(
      await axe(container, { rules: { "color-contrast": { enabled: false } } })
    ).toHaveNoViolations();
  });
});

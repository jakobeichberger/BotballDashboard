import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe, toHaveNoViolations } from "jest-axe";
import Layout from "@/components/Layout";
import { useAuthStore } from "@/store/authStore";

expect.extend(toHaveNoViolations);

// No real requests from jsdom (events, modules, notifications).
vi.mock("@/lib/api", () => ({ api: { get: vi.fn().mockResolvedValue({ data: [] }), post: vi.fn(), patch: vi.fn() } }));

vi.mock("react-i18next", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-i18next")>();
  const translations: Record<string, string> = {
    mainNavigation: "Hauptnavigation",
    closeMenu: "Menü schließen",
    openMenu: "Menü öffnen",
    logout: "Abmelden",
    changeLanguage: "Sprache wechseln",
    changeTheme: "Design wechseln",
  };
  return {
    ...actual,
    useTranslation: () => ({ t: (key: string) => translations[key] ?? key }) as any,
  };
});

function renderLayout() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<h1>Inhalt</h1>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
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

  it("gives the language and theme controls action-describing names", () => {
    renderLayout();
    expect(screen.getByRole("button", { name: /sprache wechseln/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /design wechseln/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /abmelden/i })).toBeInTheDocument();
  });

  it("renders content inside a main landmark", () => {
    renderLayout();
    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  it("keeps absolutely positioned descendants (sr-only) inside the app shell", () => {
    // Without a positioned ancestor, an sr-only span deep in the scrolling
    // <main> is laid out against the viewport and stretches the document:
    // on phones the page then scrolls on into an empty grey area.
    renderLayout();
    const main = screen.getByRole("main");
    let shell = main.parentElement;
    while (shell?.parentElement && !shell.className.includes("h-screen")) shell = shell.parentElement;
    expect(shell?.className).toMatch(/\brelative\b/);
    expect(main.className).toMatch(/overscroll-contain/);
  });

  it("opens the mobile drawer with focus inside and closes it with Escape", () => {
    renderLayout();
    const menu = screen.getByRole("button", { name: "Menü öffnen" });
    expect(menu).toHaveAttribute("aria-expanded", "false");
    menu.focus();
    fireEvent.click(menu);
    expect(menu).toHaveAttribute("aria-expanded", "true");
    const drawer = screen.getByRole("dialog", { name: "Hauptnavigation" });
    expect(drawer).toContainElement(document.activeElement as HTMLElement);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(menu).toHaveFocus();
  });

  it("has no axe violations", async () => {
    const { container } = renderLayout();
    expect(
      await axe(container, { rules: { "color-contrast": { enabled: false } } })
    ).toHaveNoViolations();
  });
});

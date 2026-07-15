import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { axe, toHaveNoViolations } from "jest-axe";
import LoginPage from "@/pages/LoginPage";

expect.extend(toHaveNoViolations);

vi.mock("@/hooks/useAuth", () => ({
  useLogin: () => vi.fn(),
  useCurrentUser: () => ({ data: null }),
  useLogout: () => vi.fn(),
}));

function renderLogin() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <main>
          <LoginPage />
        </main>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("LoginPage accessibility", () => {
  it("associates labels with their inputs (accessible by label)", () => {
    renderLogin();
    // getByLabelText only succeeds when label htmlFor <-> input id are linked.
    expect(screen.getByLabelText("E-Mail")).toHaveAttribute("type", "email");
    expect(screen.getByLabelText("Passwort")).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    const { container } = renderLogin();
    expect(
      await axe(container, { rules: { "color-contrast": { enabled: false } } })
    ).toHaveNoViolations();
  });
});

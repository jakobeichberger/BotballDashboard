import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import LoginPage from "@/pages/LoginPage";

// Mock useLogin hook
vi.mock("@/hooks/useAuth", () => ({
  useLogin: () => vi.fn().mockResolvedValue({ access_token: "tok" }),
  useCurrentUser: () => ({ data: null }),
  useLogout: () => vi.fn(),
}));

// Mock react-router navigate
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

function renderLoginPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders email and password fields", () => {
    renderLoginPage();
    expect(screen.getByPlaceholderText("admin@example.com")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("••••••••")).toBeInTheDocument();
  });

  it("renders submit button", () => {
    renderLoginPage();
    expect(screen.getByRole("button", { name: /anmelden/i })).toBeInTheDocument();
  });

  it("shows validation error for empty email", async () => {
    renderLoginPage();
    fireEvent.click(screen.getByRole("button", { name: /anmelden/i }));
    await waitFor(() => {
      expect(screen.getByText(/ungültige e-mail/i)).toBeInTheDocument();
    });
  });

  it("shows validation error for empty password", async () => {
    renderLoginPage();
    fireEvent.change(screen.getByPlaceholderText("admin@example.com"), {
      target: { value: "test@test.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: /anmelden/i }));
    await waitFor(() => {
      expect(screen.getByText(/passwort erforderlich/i)).toBeInTheDocument();
    });
  });
});

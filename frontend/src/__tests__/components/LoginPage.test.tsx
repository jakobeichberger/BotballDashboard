import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import LoginPage from "@/pages/LoginPage";

// Mock useLogin hook
const mockLogin = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useAuth", () => ({
  useLogin: () => mockLogin,
  useCurrentUser: () => ({ data: null }),
  useLogout: () => vi.fn(),
}));

// Mock react-router navigate
const mockNavigate = vi.fn();
vi.mock("react-router", async () => {
  const actual = await vi.importActual("react-router");
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
    mockLogin.mockResolvedValue({ access_token: "tok" });
  });

  it("renders email and password fields", () => {
    renderLoginPage();
    expect(screen.getByLabelText("E-Mail")).toBeInTheDocument();
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
    fireEvent.change(screen.getByLabelText("E-Mail"), {
      target: { value: "test@test.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: /anmelden/i }));
    await waitFor(() => {
      expect(screen.getByText(/passwort erforderlich/i)).toBeInTheDocument();
    });
  });

  it("rejects an address without a domain and does not log in", async () => {
    renderLoginPage();
    fireEvent.change(screen.getByLabelText("E-Mail"), { target: { value: "admin@localhost" } });
    fireEvent.change(screen.getByLabelText("Passwort"), { target: { value: "secret" } });
    fireEvent.click(screen.getByRole("button", { name: /anmelden/i }));
    expect(await screen.findByText(/ungültige e-mail/i)).toBeInTheDocument();
    expect(mockLogin).not.toHaveBeenCalled();
  });

  it("logs in with the trimmed address", async () => {
    renderLoginPage();
    fireEvent.change(screen.getByLabelText("E-Mail"), { target: { value: "  juror@test.local " } });
    fireEvent.change(screen.getByLabelText("Passwort"), { target: { value: "secret" } });
    fireEvent.click(screen.getByRole("button", { name: /anmelden/i }));
    await waitFor(() => expect(mockLogin).toHaveBeenCalledWith("juror@test.local", "secret"));
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/"));
  });
});

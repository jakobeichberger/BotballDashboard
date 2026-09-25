import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import ForgotPasswordPage from "@/pages/ForgotPasswordPage";
import ResetPasswordPage from "@/pages/ResetPasswordPage";
import { api } from "@/lib/api";
import { passwordProblem } from "@/lib/passwordPolicy";

vi.mock("@/lib/api", () => ({ api: { post: vi.fn() } }));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("password policy", () => {
  it("mirrors the backend rules", () => {
    expect(passwordProblem("short")).not.toBeNull();
    expect(passwordProblem("aaaaaaaaaaaa")).not.toBeNull();
    expect(passwordProblem("me@example.com", "ME@example.com")).not.toBeNull();
    expect(passwordProblem("correct-horse-1", "me@example.com")).toBeNull();
  });
});

describe("ForgotPasswordPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("requests a reset link and shows a neutral confirmation", async () => {
    (api.post as any).mockResolvedValue({ status: 204 });
    renderAt("/forgot-password");
    fireEvent.change(screen.getByLabelText(/e-mail/i), { target: { value: "a@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: /link anfordern/i }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/falls ein konto/i));
    expect(api.post).toHaveBeenCalledWith("/auth/password-reset/request", { email: "a@example.com" });
  });
});

describe("ResetPasswordPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("rejects a weak password without calling the API", async () => {
    renderAt("/reset-password?token=abc");
    fireEvent.change(screen.getByLabelText(/^neues passwort$/i), { target: { value: "short" } });
    fireEvent.change(screen.getByLabelText(/wiederholen/i), { target: { value: "short" } });
    fireEvent.click(screen.getByRole("button", { name: /passwort setzen/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/mindestens 10/i);
    expect(api.post).not.toHaveBeenCalled();
  });

  it("sends the token from the URL with the new password", async () => {
    (api.post as any).mockResolvedValue({ status: 204 });
    renderAt("/reset-password?token=abc");
    fireEvent.change(screen.getByLabelText(/^neues passwort$/i), { target: { value: "correct-horse-1" } });
    fireEvent.change(screen.getByLabelText(/wiederholen/i), { target: { value: "correct-horse-1" } });
    fireEvent.click(screen.getByRole("button", { name: /passwort setzen/i }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/geändert/i));
    expect(api.post).toHaveBeenCalledWith("/auth/password-reset/confirm", {
      token: "abc",
      new_password: "correct-horse-1",
    });
  });

  it("shows the hint and translates the server's common-password rejection", async () => {
    (api.post as any).mockRejectedValue({
      response: { status: 422, data: { fieldErrors: { new_password: ["Value error, Password is on a list of common or leaked passwords"] } } },
    });
    renderAt("/reset-password?token=abc");
    expect(screen.getByText(/kein bekanntes oder geleaktes Passwort/i)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/^neues passwort$/i), { target: { value: "Password123" } });
    fireEvent.change(screen.getByLabelText(/wiederholen/i), { target: { value: "Password123" } });
    fireEvent.click(screen.getByRole("button", { name: /passwort setzen/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Dieses Passwort steht auf einer Liste häufiger oder geleakter Passwörter."
    );
  });

  it("explains a missing token", () => {
    renderAt("/reset-password");
    expect(screen.getByRole("alert")).toHaveTextContent(/unvollständig/i);
  });
});

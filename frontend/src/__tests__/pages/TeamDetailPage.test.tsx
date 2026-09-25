import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import TeamDetailPage from "@/pages/TeamDetailPage";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const team = {
  id: "t1",
  name: "Team Alpha",
  team_number: null,
  school: "HTL",
  city: null,
  country: "AT",
  competition_level_id: null,
  is_active: true,
  notes: null,
  members: [
    { id: "m1", name: "Frau Mentor", email: null, role: "mentor", user_id: null },
    { id: "m2", name: "Schüler", email: null, role: "member", user_id: "u2" },
  ],
};
const users = [
  { id: "u1", email: "mentor@school.at", display_name: "Frau Mentor", is_active: true, roles: [] },
  { id: "u2", email: "student@school.at", display_name: "Schüler", is_active: true, roles: [] },
];

function mockApi() {
  (api.get as any).mockImplementation((url: string) => {
    if (url === "/teams/t1") return Promise.resolve({ data: team });
    if (url === "/auth/users") return Promise.resolve({ data: users });
    return Promise.resolve({ data: [] });
  });
  (api.patch as any).mockResolvedValue({ data: {} });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/teams/t1"]}>
        <Routes>
          <Route path="/teams/:id" element={<TeamDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("TeamDetailPage – mentor linking", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi();
  });

  it("lets teams:admin link a member to a user account", async () => {
    useAuthStore.setState({
      user: { id: "admin", display_name: "Admin", is_superuser: true, roles: [] } as any,
    });
    renderPage();
    const picker = await screen.findByLabelText("Benutzerkonto für Frau Mentor");
    await waitFor(() => expect(screen.getAllByRole("option", { name: /mentor@school.at/ }).length).toBeGreaterThan(0));
    await userEvent.selectOptions(picker, "u1");
    expect(api.patch).toHaveBeenCalledWith("/teams/t1/members/m1", { user_id: "u1" });

    await userEvent.selectOptions(screen.getByLabelText("Benutzerkonto für Schüler"), "");
    expect(api.patch).toHaveBeenCalledWith("/teams/t1/members/m2", { user_id: null });
  });

  it("shows the link read-only to everyone else", async () => {
    useAuthStore.setState({
      user: {
        id: "mentor",
        email: "m@x",
        display_name: "Mentor",
        is_superuser: false,
        preferred_language: "de",
        theme: "light",
        roles: [{ id: "r", name: "mentor", description: null }],
        permissions: ["teams:read", "teams:write"],
      },
    });
    renderPage();
    expect(await screen.findByText("Konto verknüpft")).toBeInTheDocument();
    expect(screen.queryByLabelText(/benutzerkonto für/i)).not.toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalledWith("/auth/users");
  });
});

describe("TeamDetailPage – editing the team", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi();
  });

  it("lets a mentor edit the profile but not the organizer fields", async () => {
    (api.get as any).mockImplementation((url: string) => {
      if (url === "/teams/t1") return Promise.resolve({ data: team });
      if (url === "/teams/mine") return Promise.resolve({ data: [{ id: "t1" }] });
      return Promise.resolve({ data: [] });
    });
    useAuthStore.setState({
      user: {
        id: "mentor",
        email: "m@x",
        display_name: "Mentor",
        is_superuser: false,
        preferred_language: "de",
        theme: "light",
        roles: [{ id: "r", name: "mentor", description: null }],
        permissions: ["teams:read", "teams:write"],
      },
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /bearbeiten/i }));
    expect(screen.queryByText("Team-Nr.")).not.toBeInTheDocument();
    expect(screen.queryByText("Notizen")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /speichern/i }));
    await waitFor(() => expect(api.patch).toHaveBeenCalled());
    const [, body] = (api.patch as any).mock.calls[0];
    expect(body).toEqual({ name: "Team Alpha", school: "HTL", city: "", country: "AT" });
  });

  it("lets organizers edit team number and notes", async () => {
    useAuthStore.setState({
      user: { id: "admin", display_name: "Admin", is_superuser: true, roles: [] } as any,
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /bearbeiten/i }));
    expect(screen.getByText("Team-Nr.")).toBeInTheDocument();
    expect(screen.getByText("Notizen")).toBeInTheDocument();
  });
});

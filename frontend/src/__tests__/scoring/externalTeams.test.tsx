import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ScoutingPage from "@/pages/ScoutingPage";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }));
// Deleting asks first (lib/confirm); these tests confirm.
vi.mock("@/lib/confirm", () => ({ confirmAction: vi.fn().mockResolvedValue(true) }));

const external = [
  { id: "x1", season_id: "s1", name: "Robo Masters", number: "25-0538", country: "KW", school: null, source: "observed", notes: null, created_by: "mentor", created_at: "" },
  { id: "x2", season_id: "s1", name: "Kuwait Bots", number: null, country: "KW", school: null, source: "observed", notes: null, created_by: "organizer", created_at: "" },
];

function renderPage(userId: string, permissions: string[]) {
  useAuthStore.setState({ user: { id: userId, is_superuser: false, roles: [], permissions } as never });
  (api.get as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
    if (url === "/v1/events/e1") return Promise.resolve({ data: { id: "e1", season_id: "s1", slug: "ecer" } });
    if (url === "/scoring/seasons/s1/external-teams") return Promise.resolve({ data: external });
    return Promise.resolve({ data: [] });
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/events/e1/scouting"]}>
        <Routes><Route path="/events/:eventId/scouting" element={<ScoutingPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("external scouting teams", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.patch as ReturnType<typeof vi.fn>).mockResolvedValue({ data: {} });
    (api.delete as ReturnType<typeof vi.fn>).mockResolvedValue({ data: {} });
  });

  it("lets the creator edit the team but not delete it", async () => {
    renderPage("mentor", ["scoring:read", "scoring:write"]);
    fireEvent.click(await screen.findByRole("button", { name: "Robo Masters · 25-0538" }));
    expect(screen.queryByRole("button", { name: "Robo Masters löschen" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Robo Masters bearbeiten" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Schule" }), { target: { value: "Al-Ru'ya Bilingual School" } });
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/scoring/external-teams/x1", {
      name: "Robo Masters",
      number: "25-0538",
      country: "KW",
      school: "Al-Ru'ya Bilingual School",
      notes: null,
    }));
  });

  it("does not offer editing a team someone else created to a mentor", async () => {
    renderPage("mentor", ["scoring:read", "scoring:write"]);
    fireEvent.click(await screen.findByRole("button", { name: "Kuwait Bots" }));
    expect(screen.queryByRole("button", { name: "Kuwait Bots bearbeiten" })).not.toBeInTheDocument();
  });

  it("lets organizers delete a team", async () => {
    renderPage("organizer", ["scoring:read", "scoring:write", "scoring:admin"]);
    fireEvent.click(await screen.findByRole("button", { name: "Robo Masters · 25-0538" }));
    expect(screen.getByRole("button", { name: "Robo Masters bearbeiten" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Robo Masters löschen" }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/scoring/external-teams/x1"));
  });
});

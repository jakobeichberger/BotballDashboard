import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import ProfilePage from "@/pages/ProfilePage";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), put: vi.fn(), patch: vi.fn(), post: vi.fn(), delete: vi.fn() },
  restoreAccessToken: vi.fn(),
}));

const prefs = {
  match_soon: true,
  score_corrected: true,
  deadlines: true,
  paper_status: true,
  print_status: true,
  announcements: true,
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <ProfilePage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("ProfilePage notification preferences", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ user: { id: "u1", email: "u@test", display_name: "U", preferred_language: "de", roles: [] } as never });
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: prefs });
    (api.put as ReturnType<typeof vi.fn>).mockImplementation(async (_url: string, patch: object) => ({ data: { ...prefs, ...patch } }));
  });

  it("lists every notification type with its stored value", async () => {
    renderPage();
    const box = await screen.findByRole("checkbox", { name: /Druckaufträge/ });
    await waitFor(() => expect(box).toBeEnabled());
    expect(box).toBeChecked();
    for (const label of ["Match beginnt bald", "Score korrigiert", "Deadlines", "Paper-Status", "Ankündigungen"]) {
      expect(screen.getByRole("checkbox", { name: new RegExp(label) })).toBeInTheDocument();
    }
  });

  it("saves a switched-off type", async () => {
    renderPage();
    const box = await screen.findByRole("checkbox", { name: /Druckaufträge/ });
    await waitFor(() => expect(box).toBeEnabled());
    fireEvent.click(box);
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/auth/me/notification-preferences", { print_status: false }));
    await waitFor(() => expect(screen.getByRole("checkbox", { name: /Druckaufträge/ })).not.toBeChecked());
  });
});

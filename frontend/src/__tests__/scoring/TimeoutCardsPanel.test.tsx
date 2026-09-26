import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import TimeoutCardsPanel from "@/modules/scoring/extras/TimeoutCardsPanel";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }));

const REGISTRATIONS = [{ team_id: "t1", team_name: "TechSupport" }] as never;

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TimeoutCardsPanel eventId="e1" registrations={REGISTRATIONS} />
    </QueryClientProvider>,
  );
}

describe("TimeoutCardsPanel load failure", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ hasPermission: () => true } as never);
  });

  it("shows an error with retry instead of an empty list, and no recording form", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockRejectedValueOnce({ response: { status: 500, data: {} } });
    renderPanel();
    expect(await screen.findByRole("alert")).toHaveTextContent(/Serverfehler/);
    // Which teams used their card is unknown: neither "none used" nor the form.
    expect(screen.queryByText("Noch kein Team hat seine Timeout-Karte genutzt.")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Timeout erfassen" })).not.toBeInTheDocument();

    (api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ data: [] });
    fireEvent.click(screen.getByRole("button", { name: "Erneut versuchen" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Timeout erfassen" })).toBeInTheDocument();
  });
});

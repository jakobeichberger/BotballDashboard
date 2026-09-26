import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import TimeoutCardsPanel from "@/modules/scoring/extras/TimeoutCardsPanel";
import ConfirmHost from "@/components/ConfirmHost";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }));

const REGISTRATIONS = [{ team_id: "t1", team_name: "TechSupport" }] as never;

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TimeoutCardsPanel eventId="e1" registrations={REGISTRATIONS} />
      <ConfirmHost />
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

describe("TimeoutCardsPanel revoke", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ hasPermission: () => true } as never);
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: [{ id: "c1", team_id: "t1", team_name: "TechSupport", round_number: 2, reason: "before_hands_off", note: null, used_at: "2026-09-26T10:00:00Z" }],
    });
    (api.delete as ReturnType<typeof vi.fn>).mockResolvedValue({});
  });

  it("asks before revoking and does nothing on cancel", async () => {
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: /TechSupport/ }));
    expect(await screen.findByText(/Timeout-Karte von „TechSupport“ zurücknehmen/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByText(/zurücknehmen\?/)).not.toBeInTheDocument());
    expect(api.delete).not.toHaveBeenCalled();
  });

  it("revokes after confirming", async () => {
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: /TechSupport/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Löschen" }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/scoring/events/e1/timeouts/t1"));
  });
});

import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import EventAuditTrail from "@/components/analytics/EventAuditTrail";
import { revisionChanges, scoreRevisionKind } from "@/lib/audit";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn() } }));

const get = api.get as ReturnType<typeof vi.fn>;

describe("revisionChanges", () => {
  it("lists changed fields and compares raw scores per entry", () => {
    expect(revisionChanges(
      { total_score: 30, raw_scores: { cubes: 10, parked: 1 }, is_disqualified: false, notes: null, version: 1 },
      { total_score: 36, raw_scores: { cubes: 12, parked: 1 }, is_disqualified: true, notes: null, version: 2 },
    )).toEqual([
      { key: "is_disqualified", before: false, after: true },
      { key: "raw_scores.cubes", before: 10, after: 12 },
      { key: "total_score", before: 30, after: 36 },
    ]);
  });

  it("handles missing snapshots (created or removed results)", () => {
    expect(revisionChanges(null, { de_rank: 3 })).toEqual([{ key: "de_rank", before: undefined, after: 3 }]);
    expect(revisionChanges({ de_rank: 3 }, null)).toEqual([{ key: "de_rank", before: 3, after: undefined }]);
  });

  it("classifies score revisions", () => {
    expect(scoreRevisionKind({ previous_value: null, new_value: { total_score: 1 } })).toBe("created");
    expect(scoreRevisionKind({ previous_value: { total_score: 1 }, new_value: { total_score: 2 } })).toBe("updated");
    expect(scoreRevisionKind({ previous_value: { total_score: 1 }, new_value: { total_score: 1, deleted: true } })).toBe("deleted");
  });
});

describe("EventAuditTrail", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ user: { id: "u", is_superuser: false, roles: [], permissions: ["scoring:admin", "users:read"] } as never });
    get.mockImplementation((url: string) => {
      if (url === "/v1/events/e1/registrations") return Promise.resolve({ data: [{ id: "r1", team_id: "t1", team_name: "Alpha" }] });
      if (url === "/auth/users") return Promise.resolve({ data: [{ id: "judge", display_name: "Head Judge" }] });
      if (url === "/scoring/events/e1/revisions") {
        return Promise.resolve({ data: [
          { id: "rv2", match_id: "m1", match_ref: "m1", team_id: "t1", event_id: "e1", revision: 2, previous_value: { total_score: 30, yellow_card: false }, new_value: { total_score: 30, yellow_card: true }, reason: "Unsportlich", changed_by: "judge", created_at: "2026-05-01T10:05:00Z" },
          { id: "rv1", match_id: null, match_ref: "m0", team_id: "t1", event_id: "e1", revision: 3, previous_value: { total_score: 12 }, new_value: { total_score: 12, deleted: true }, reason: "Match deleted", changed_by: null, created_at: "2026-05-01T10:00:00Z" },
        ] });
      }
      if (url === "/scoring/events/e1/result-revisions") {
        return Promise.resolve({ data: [
          { id: "rr1", event_id: "e1", team_id: "t1", kind: "de", previous_value: { de_rank: 4 }, new_value: { de_rank: 2 }, changed_by: "judge", created_at: "2026-05-02T09:00:00Z" },
        ] });
      }
      return Promise.resolve({ data: [] });
    });
  });

  function renderTrail() {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(<QueryClientProvider client={client}><EventAuditTrail eventId="e1" /></QueryClientProvider>);
  }

  it("shows score changes with reason and author, including deleted runs", async () => {
    renderTrail();
    const card = (await screen.findByText("Unsportlich")).closest("tr")!;
    expect(within(card).getByText("Geändert")).toBeInTheDocument();
    expect(card).toHaveTextContent("Gelbe Karte: nein → ja");
    expect(card).toHaveTextContent("Head Judge");
    const deleted = screen.getByText("Match deleted").closest("tr")!;
    expect(within(deleted).getByText("Gelöscht")).toBeInTheDocument();
    expect(deleted).toHaveTextContent("Summe 12");
    expect(deleted).toHaveTextContent("System");
  });

  it("switches to the result revisions and filters by team and kind", async () => {
    renderTrail();
    await screen.findByText("Unsportlich");
    fireEvent.click(screen.getByRole("tab", { name: "Ergebnisse" }));
    const row = (await screen.findByText("de_rank:")).closest("tr")!;
    expect(row).toHaveTextContent("Double Elimination");
    expect(row).toHaveTextContent("de_rank: 4 → 2");
    fireEvent.change(screen.getByRole("combobox", { name: "Team" }), { target: { value: "t1" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Art" }), { target: { value: "de" } });
    await waitFor(() => expect(get).toHaveBeenCalledWith("/scoring/events/e1/result-revisions", { params: { team_id: "t1", kind: "de" } }));
  });
});

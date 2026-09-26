import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import PublicEventPage from "@/pages/PublicEventPage";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn() },
}));

class FakeSocket {
  static instances: FakeSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((message: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: string) {
    FakeSocket.instances.push(this);
  }
  close() {}
  emit(event: string) {
    this.onmessage?.({ data: JSON.stringify({ event }) });
  }
}

const event = {
  id: "e1",
  name: "Live Event",
  slug: "live",
  public_scoreboard: true,
  public_schedule: true,
  public_results: true,
  public_announcements: false,
};

function calls(path: string) {
  return (api.get as ReturnType<typeof vi.fn>).mock.calls.filter(([url]) => url === path);
}

function renderPage(extra: Record<string, unknown> = {}) {
  (api.get as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
    if (url === "/v1/public/events/live") return Promise.resolve({ data: event });
    if (url in extra) return Promise.resolve({ data: extra[url] });
    if (url.endsWith("/ranking")) {
      return Promise.resolve({
        data: [{ rank: 1, team_id: "t1", team_name: "Alpha", team_number: "1", seed_score: 10, best_score: 10, rounds_played: 1 }],
      });
    }
    return Promise.resolve({ data: [] });
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/public/live"]}>
        <Routes>
          <Route path="/public/:eventSlug" element={<PublicEventPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PublicEventPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    FakeSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeSocket);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("asks only for the next matches and the latest results", async () => {
    renderPage();
    await screen.findByText("Alpha");
    await waitFor(() => expect(calls("/v1/public/events/live/results")).toHaveLength(1));
    expect(calls("/v1/public/events/live/results")[0][1]).toEqual({ params: { limit: 12, order: "desc" } });
    expect(calls("/v1/public/events/live/schedule")[0][1]).toEqual({ params: { upcoming: true, limit: 10 } });
  });

  it("shows published awards as a panel of their own", async () => {
    renderPage({
      "/v1/public/events/live/awards": [
        {
          key: "botball_overall",
          label: "Botball – Overall",
          results: [
            { team_id: "t1", team_name: "Alpha", team_number: "26-0001", place: 1, course: null },
            { team_id: "t2", team_name: "Beta", team_number: null, place: 2, course: "Course A" },
          ],
        },
      ],
    });
    await screen.findByText("Alpha");
    fireEvent.click(await screen.findByRole("button", { name: "Awards anzeigen" }));
    const panel = await screen.findByRole("heading", { name: "Awards" });
    const section = panel.closest("section")!;
    expect(within(section).getByRole("heading", { name: "Botball – Overall" })).toBeInTheDocument();
    expect(within(section).getByText("1. Platz")).toBeInTheDocument();
    expect(within(section).getByText("Beta")).toBeInTheDocument();
    expect(within(section).getByText("Course A")).toBeInTheDocument();
  });

  it("re-fetches once per burst of live events and only what is on screen", async () => {
    renderPage();
    await screen.findByText("Alpha");
    await waitFor(() => expect(calls("/v1/public/events/live/results")).toHaveLength(1));
    vi.useFakeTimers();
    const socket = FakeSocket.instances[0];
    act(() => {
      socket.onopen?.();
      // A whole round entered at once.
      for (let i = 0; i < 5; i++) socket.emit("ranking_updated");
    });
    expect(calls("/v1/public/events/live/ranking")).toHaveLength(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(600);
    });
    vi.useRealTimers();
    // The ranking panel is shown: one re-fetch for the burst. The results
    // panel is hidden: marked stale, fetched when it comes into view.
    await waitFor(() => expect(calls("/v1/public/events/live/ranking")).toHaveLength(2));
    expect(calls("/v1/public/events/live/results")).toHaveLength(1);
  });
});

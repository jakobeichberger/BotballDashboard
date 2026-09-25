import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ScanReviewPage from "@/pages/ScanReviewPage";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn() } }));

const registrations = [
  { id: "r2", team_id: "uuid-beta", team_name: "Beta Bots", team_number: null, seed_number: 2 },
  { id: "r1", team_id: "uuid-alpha", team_name: "Alpha", team_number: "AT-1", seed_number: 1 },
];

function renderPage(status = "processing") {
  (api.get as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
    if (url.endsWith("/registrations")) return Promise.resolve({ data: registrations });
    if (url.endsWith("/score-sheet-scans")) {
      return Promise.resolve({ data: [{ id: "s1", template_id: "t", team_id: "uuid-beta", file_name: "sheet.jpg", status, extracted_values: null, error: null, created_at: "" }] });
    }
    if (url === "/v1/events/ev") return Promise.resolve({ data: { id: "ev", season_id: "se" } });
    return Promise.resolve({ data: [] });
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/events/ev/scans"]}>
        <Routes>
          <Route path="/events/:eventId/scans" element={<ScanReviewPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ScanReviewPage upload", () => {
  beforeEach(() => vi.clearAllMocks());

  it.each([
    ["processing", true],
    ["failed", false],
  ])("polls the scan list only while scans are processed (%s)", async (status, polls) => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      renderPage(status);
      await screen.findByText(/sheet\.jpg/);
      const scanCalls = () => (api.get as ReturnType<typeof vi.fn>).mock.calls.filter(([url]) => String(url).endsWith("/score-sheet-scans")).length;
      const before = scanCalls();
      await vi.advanceTimersByTimeAsync(11_000);
      expect(scanCalls() > before).toBe(polls);
    } finally {
      vi.useRealTimers();
    }
  });

  it("selects the team by seed, name and number instead of its UUID", async () => {
    renderPage();
    const select = screen.getByRole("combobox", { name: "Team" });
    expect(await within(select).findByRole("option", { name: "#1 · Alpha (AT-1)" })).toHaveValue("uuid-alpha");
    const options = within(select).getAllByRole("option").map((option) => option.textContent);
    expect(options).toEqual(["Team wählen", "#1 · Alpha (AT-1)", "#2 · Beta Bots"]);
    expect(screen.queryByText(/uuid-/)).not.toBeInTheDocument();
    expect(await screen.findByText("sheet.jpg · #2 · Beta Bots")).toBeInTheDocument();
  });

  it("offers a camera capture input for phones", () => {
    const { container } = renderPage();
    const camera = container.querySelector('input[capture="environment"]');
    expect(camera).not.toBeNull();
    expect(camera).toHaveAttribute("accept", "image/*");
    expect(screen.getByText("Foto aufnehmen")).toBeInTheDocument();
  });
});

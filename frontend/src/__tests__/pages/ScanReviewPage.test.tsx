import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import ScanReviewPage from "@/pages/ScanReviewPage";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn() } }));

const registrations = [
  { id: "r2", team_id: "uuid-beta", team_name: "Beta Bots", team_number: null, seed_number: 2 },
  { id: "r1", team_id: "uuid-alpha", team_name: "Alpha", team_number: "AT-1", seed_number: 1 },
];

function renderPage(status = "processing", extracted: unknown[] | null = null) {
  (api.get as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
    if (url.endsWith("/registrations")) return Promise.resolve({ data: registrations });
    if (url.endsWith("/score-sheet-scans")) {
      return Promise.resolve({ data: [{ id: "s1", template_id: "t", team_id: "uuid-beta", file_name: "sheet.jpg", status, extracted_values: extracted, error: null, created_at: "" }] });
    }
    if (url === "/v1/events/ev") return Promise.resolve({ data: { id: "ev", season_id: "se" } });
    if (url === "/crops/c1") return Promise.resolve({ data: new Blob(["png"]) });
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

  it("shows a protected crop through an object URL that is revoked on unmount", async () => {
    const create = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:crop-1");
    const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    try {
      const { container, unmount } = renderPage("review", [{ key: "cubes", value: 3, confidence: 0.9, cropUrl: "/api/crops/c1", requiresReview: false, reasons: [] }]);
      await waitFor(() => expect(container.querySelector("img")).toHaveAttribute("src", "blob:crop-1"));
      expect(create).toHaveBeenCalledTimes(1);
      expect(revoke).not.toHaveBeenCalled();
      unmount();
      expect(revoke).toHaveBeenCalledWith("blob:crop-1");
    } finally {
      create.mockRestore();
      revoke.mockRestore();
    }
  });

  it("offers a camera capture input for phones", () => {
    const { container } = renderPage();
    const camera = container.querySelector('input[capture="environment"]');
    expect(camera).not.toBeNull();
    expect(camera).toHaveAttribute("accept", "image/*");
    expect(screen.getByText("Foto aufnehmen")).toBeInTheDocument();
  });
});

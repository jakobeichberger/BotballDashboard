import "fake-indexeddb/auto";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import ScoreEntryPage from "@/pages/ScoreEntryPage";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
  isQueuedResponse: (data: { queued?: boolean } | null) => !!data?.queued,
}));

function renderPage() {
  (api.get as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
    if (url === "/seasons/active") return Promise.resolve({ data: { id: "s1" } });
    if (url === "/teams") return Promise.resolve({ data: [{ id: "t1", name: "Alpha" }] });
    if (url === "/scoring/seasons/s1/schema") {
      return Promise.resolve({ data: { fields: [{ key: "cubes", label: "Würfel", multiplier: 3, max_value: null, type: "count" }] } });
    }
    return Promise.resolve({ data: [] });
  });
  (api.post as ReturnType<typeof vi.fn>).mockResolvedValue({ data: { id: "m1" } });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ScoreEntryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function fillForm() {
  const team = await screen.findByRole("combobox");
  await within(team).findByRole("option", { name: "Alpha" });
  fireEvent.change(team, { target: { value: "t1" } });
  const inputs = screen.getAllByRole("spinbutton");
  fireEvent.change(inputs[inputs.length - 1], { target: { value: "5" } });
}

describe("ScoreEntryPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
    useAuthStore.setState({
      user: { id: "j", display_name: "Jury", is_superuser: false, roles: [{ name: "juror", permissions: [] }] } as never,
    });
  });

  it("confirms an official score with its total before sending it", async () => {
    renderPage();
    await fillForm();
    fireEvent.click(screen.getByRole("button", { name: /Wertung prüfen & speichern/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByTestId("confirm-total")).toHaveTextContent("15.00");
    expect(api.post).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Verbindlich absenden" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    const [url, body] = (api.post as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe("/scoring/seasons/s1/matches");
    expect(body).toMatchObject({ team_id: "t1", is_practice: false, raw_scores: { cubes: 5 } });
    expect(body.idempotency_key).toEqual(expect.any(String));
  });

  it("saves practice runs without the confirmation step", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Vorbereitung/ }));
    await fillForm();
    fireEvent.click(screen.getByRole("button", { name: /Übungslauf speichern/ }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect((api.post as ReturnType<typeof vi.fn>).mock.calls[0][1]).toMatchObject({ is_practice: true });
  });
});

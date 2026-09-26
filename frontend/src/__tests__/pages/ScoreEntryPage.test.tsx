import "fake-indexeddb/auto";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import ScoreEntryPage from "@/pages/ScoreEntryPage";
import ConfirmHost from "@/components/ConfirmHost";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
  isQueuedResponse: (data: { queued?: boolean } | null) => !!data?.queued,
}));

function renderPage(matches: unknown[] = []) {
  (api.get as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
    if (url === "/scoring/seasons/s1/matches") return Promise.resolve({ data: matches });
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
        <ConfirmHost />
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
      user: { id: "j", display_name: "Jury", is_superuser: false, roles: [{ name: "juror", permissions: [] }], permissions: ["scoring:read", "scoring:write", "scoring:admin"] } as never,
    });
  });

  it("confirms an official score with its total before sending it", async () => {
    renderPage();
    await fillForm();
    fireEvent.click(screen.getByRole("button", { name: /Wertung prüfen & speichern/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByTestId("confirm-total")).toHaveTextContent("15,00");
    expect(api.post).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Verbindlich absenden" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    const [url, body] = (api.post as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe("/scoring/seasons/s1/matches");
    expect(body).toMatchObject({ team_id: "t1", is_practice: false, raw_scores: { cubes: 5 } });
    expect(body.idempotency_key).toEqual(expect.any(String));
  });

  it("labels every form field", async () => {
    renderPage();
    expect(await screen.findByLabelText("Team")).toBeInTheDocument();
    expect(screen.getByRole("spinbutton", { name: /Würfel/ })).toHaveAttribute("type", "number");
  });

  it("deletes a score only after an explicit confirmation", async () => {
    (api.delete as ReturnType<typeof vi.fn>).mockResolvedValue({});
    renderPage([{ id: "m9", team_id: "t1", round_number: 2, total_score: 42, is_practice: false, confirmed_by: null, raw_scores: {} }]);
    const remove = await screen.findByRole("button", { name: "Wertung von Alpha, Runde 2 löschen" });
    fireEvent.click(remove);
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Alpha (Runde 2, 42 Punkte)");
    fireEvent.click(within(dialog).getByRole("button", { name: "Abbrechen" }));
    expect(api.delete).not.toHaveBeenCalled();

    fireEvent.click(remove);
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/scoring/matches/m9"));
  });

  it("shows loading instead of 'no schema' while the schema loads", async () => {
    (api.get as ReturnType<typeof vi.fn>).mockImplementation((url: string) =>
      url === "/scoring/seasons/s1/schema" ? new Promise(() => undefined) : url === "/seasons/active" ? Promise.resolve({ data: { id: "s1" } }) : Promise.resolve({ data: [] }),
    );
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter><ScoreEntryPage /></MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/scoring/seasons/s1/schema"));
    expect(screen.getByRole("status")).toHaveTextContent("Laden…");
    expect(screen.queryByText(/Kein aktives Wertungsschema/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Keine aktive Saison/)).not.toBeInTheDocument();
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

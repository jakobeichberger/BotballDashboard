import "fake-indexeddb/auto";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import ScoreEntryPage from "@/pages/ScoreEntryPage";
import ConfirmHost from "@/components/ConfirmHost";
import { api } from "@/lib/api";
import { discardQueuedScore, enqueueScore, resetQueueStore } from "@/lib/offlineQueue";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
  isQueuedResponse: (data: { queued?: boolean } | null) => !!data?.queued,
}));

const EVENT = "ev1";
const REGISTRATIONS = [
  { id: "r1", team_id: "t1", team_name: "RoboLions", team_number: "1", category: "botball", seed_number: null },
  { id: "r2", team_id: "t2", team_name: "Owls", team_number: "2", category: "open", seed_number: null },
  { id: "r3", team_id: "t3", team_name: "Drone Masters", team_number: "3", category: "aerial_junior", seed_number: null },
  { id: "r4", team_id: "t4", team_name: "Code Cubs", team_number: "4", category: "jbc", seed_number: null },
];
const SCHEMA = { fields: [{ key: "cubes", label: "Würfel", multiplier: 3, max_value: 20, type: "count" }] };

function renderPage(matches: unknown[] = []) {
  (api.get as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
    if (url === `/v1/events/${EVENT}`) return Promise.resolve({ data: { id: EVENT, season_id: "s1" } });
    if (url === "/seasons/s1") return Promise.resolve({ data: { id: "s1" } });
    if (url === `/v1/events/${EVENT}/registrations`) return Promise.resolve({ data: REGISTRATIONS });
    if (url === `/scoring/seasons/s1/schema?event_id=${EVENT}`) return Promise.resolve({ data: SCHEMA });
    if (url === `/scoring/seasons/s1/matches?event_id=${EVENT}`) return Promise.resolve({ data: matches });
    // "/teams" (every team of the system) must not be the source of the list.
    if (url === "/teams") return Promise.resolve({ data: [{ id: "tx", name: "Somewhere Else" }] });
    return Promise.resolve({ data: [] });
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/events/${EVENT}/scoring/entry`]}>
        <Routes><Route path="/events/:eventId/scoring/entry" element={<ScoreEntryPage />} /></Routes>
        <ConfirmHost />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function chooseTeam(name: string) {
  const select = await screen.findByLabelText("Team");
  const option = await within(select).findByRole("option", { name });
  fireEvent.change(select, { target: { value: (option as HTMLOptionElement).value } });
}

const roundInput = () => screen.getByLabelText("Runde") as HTMLInputElement;
const cubes = () => screen.getByRole("spinbutton", { name: /Würfel/ }) as HTMLInputElement;
const saveButton = () => screen.getByRole("button", { name: /Wertung prüfen & speichern/ });

describe("ScoreEntryPage under an event", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetQueueStore();
    Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
    useAuthStore.setState({
      user: { id: "j", display_name: "Jury", is_superuser: false, roles: [{ name: "juror", permissions: [] }], permissions: ["scoring:read", "scoring:write", "scoring:admin"] } as never,
    });
    (api.post as ReturnType<typeof vi.fn>).mockResolvedValue({ data: { id: "m1" } });
  });

  it("offers only the event's teams whose category plays matches", async () => {
    renderPage();
    const select = await screen.findByLabelText("Team");
    await within(select).findByRole("option", { name: "RoboLions" });
    const names = within(select).getAllByRole("option").map((option) => option.textContent);
    expect(names).toEqual(["— Team wählen —", "RoboLions", "Owls"]);
    expect(api.get).not.toHaveBeenCalledWith("/teams");
  });

  it("edits the round like a phone keyboard would and has steppers", async () => {
    renderPage();
    await chooseTeam("RoboLions");
    expect(roundInput()).toHaveAttribute("inputmode", "numeric");
    expect(roundInput().value).toBe("1");
    // "1", backspace, "2" → 2 (was 12: clearing put the 1 straight back).
    fireEvent.change(roundInput(), { target: { value: "" } });
    expect(roundInput().value).toBe("");
    expect(screen.getByText("Die Runde muss eine ganze Zahl ab 1 sein.")).toBeInTheDocument();
    expect(saveButton()).toBeDisabled();
    fireEvent.change(roundInput(), { target: { value: "2" } });
    expect(roundInput().value).toBe("2");
    fireEvent.click(screen.getByRole("button", { name: "Runde erhöhen" }));
    expect(roundInput().value).toBe("3");
    fireEvent.click(screen.getByRole("button", { name: "Runde verringern" }));
    expect(roundInput().value).toBe("2");
  });

  it("lets count fields be cleared and stepped", async () => {
    renderPage();
    await chooseTeam("RoboLions");
    fireEvent.change(cubes(), { target: { value: "5" } });
    fireEvent.change(cubes(), { target: { value: "" } });
    expect(cubes().value).toBe("");
    fireEvent.click(screen.getByRole("button", { name: "Würfel um 1 erhöhen" }));
    fireEvent.click(screen.getByRole("button", { name: "Würfel um 1 erhöhen" }));
    expect(cubes().value).toBe("2");
    fireEvent.click(screen.getByRole("button", { name: "Würfel um 1 verringern" }));
    expect(cubes().value).toBe("1");
  });

  it("catches negative and too large values with a localized message and blocks saving", async () => {
    renderPage();
    await chooseTeam("RoboLions");
    fireEvent.change(cubes(), { target: { value: "-3" } });
    expect(await screen.findByText("„Würfel“ muss mindestens 0 sein.")).toBeInTheDocument();
    expect(saveButton()).toBeDisabled();
    fireEvent.change(cubes(), { target: { value: "25" } });
    expect(screen.getByText("„Würfel“ darf höchstens 20 sein.")).toBeInTheDocument();
    expect(screen.queryByText(/cubes/)).not.toBeInTheDocument();
    expect(saveButton()).toBeDisabled();
    fireEvent.change(cubes(), { target: { value: "4" } });
    expect(saveButton()).toBeEnabled();
  });

  it("preselects the next free round and refuses a recorded one", async () => {
    renderPage([{ id: "m7", team_id: "t1", round_number: 1, total_score: 120, is_practice: false, confirmed_by: "j", raw_scores: { cubes: 10 } }]);
    await screen.findByText("120");
    await chooseTeam("RoboLions");
    expect(roundInput().value).toBe("2");
    fireEvent.change(roundInput(), { target: { value: "1" } });
    const warning = screen.getByText(/Runde 1 von RoboLions ist schon erfasst \(120 P\.\)/);
    expect(warning).toBeInTheDocument();
    expect(saveButton()).toBeDisabled();
    // The way out: correct the recorded run.
    fireEvent.click(within(warning.parentElement as HTMLElement).getByRole("button", { name: /Vorhandenen Eintrag korrigieren/ }));
    expect(cubes().value).toBe("10");
    expect(screen.getByRole("button", { name: /Änderungen speichern/ })).toBeEnabled();
  });

  it("confirms a saved score visibly with team, round and points", async () => {
    renderPage();
    await chooseTeam("RoboLions");
    fireEvent.change(cubes(), { target: { value: "5" } });
    fireEvent.click(saveButton());
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Verbindlich absenden" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Gespeichert: RoboLions · Runde 1 · 15 P.");
    expect((api.post as ReturnType<typeof vi.fn>).mock.calls[0][1]).toMatchObject({ team_id: "t1", round_number: 1, event_id: EVENT });
    // The form moves on to the next round of the team.
    expect(roundInput().value).toBe("2");
  });

  it("drops the offline notice once the queued entry has been synced", async () => {
    (api.post as ReturnType<typeof vi.fn>).mockImplementation(async (url: string, body: Record<string, unknown>) => {
      const entry = await enqueueScore(url, body, "RoboLions", "j");
      return { status: 202, data: { queued: true, idempotency_key: entry.id } };
    });
    renderPage();
    await chooseTeam("RoboLions");
    fireEvent.change(cubes(), { target: { value: "5" } });
    fireEvent.click(saveButton());
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Verbindlich absenden" }));
    const notice = "Offline gespeichert – wird synchronisiert, sobald eine Verbindung besteht.";
    expect(await screen.findByText(notice)).toBeInTheDocument();
    const key = (api.post as ReturnType<typeof vi.fn>).mock.calls[0][1].idempotency_key as string;
    // The sync removes the entry from the queue.
    await act(async () => { await discardQueuedScore(key); });
    await waitFor(() => expect(screen.queryByText(notice)).not.toBeInTheDocument());
  });
});

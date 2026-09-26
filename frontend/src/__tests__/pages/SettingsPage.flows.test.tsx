import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import SettingsPage from "@/pages/SettingsPage";
import ConfirmHost from "@/components/ConfirmHost";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

// Admin flows before an event (review 2026-09, #5: SettingsPage had 47 %
// line coverage): accounts and roles, competition levels, season modules and
// categories, announcements.
vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() } }));

const get = api.get as ReturnType<typeof vi.fn>;
const post = api.post as ReturnType<typeof vi.fn>;
const patch = api.patch as ReturnType<typeof vi.fn>;
const put = api.put as ReturnType<typeof vi.fn>;
const del = api.delete as ReturnType<typeof vi.fn>;

const ROLES = [{ id: "r-juror", name: "juror" }, { id: "r-admin", name: "admin" }];
const USERS = [
  { id: "u1", display_name: "Jana Jurorin", email: "jana@example.org", is_active: true, roles: [{ id: "r-juror", name: "juror" }] },
  { id: "u2", display_name: "Paul Pause", email: "paul@example.org", is_active: false, roles: [] },
];
const STRONG = "Korrekt-Pferd-Batterie-42";

function mockApi(overrides: Record<string, unknown> = {}) {
  const data: Record<string, unknown> = {
    "/auth/users": USERS,
    "/auth/roles": ROLES,
    "/seasons": [{ id: "s1", name: "Botball 2026", year: 2026, is_active: true }],
    "/seasons/s1": { id: "s1", name: "Botball 2026", use_seeding: true, use_double_elimination: false, use_aerial: false, use_documentation_scoring: false, use_paper_scoring: true, active_categories: ["botball"] },
    "/seasons/s1/categories": [],
    "/seasons/competition-levels/all?include_inactive=true": [
      { id: "l1", name: "ECER", code: "ECER", order: 1, is_active: true, qualifies_from_level_id: null },
      { id: "l2", name: "GCER", code: "GCER", order: 2, is_active: true, qualifies_from_level_id: null },
    ],
    "/dashboard/announcements?include_unpublished=true": [
      { id: "a1", title: "Anreise", audience: "teams", is_published: false },
      { id: "a2", title: "Willkommen", audience: "all", is_published: true },
    ],
    ...overrides,
  };
  get.mockImplementation((url: string) => Promise.resolve({ data: url in data ? data[url] : [] }));
}

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/settings/*" element={<SettingsPage />} />
        </Routes>
        <ConfirmHost />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function confirmDialog(button: string) {
  const dialog = await screen.findByRole("dialog");
  fireEvent.click(within(dialog).getByRole("button", { name: button }));
}

describe("SettingsPage flows", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi();
    for (const method of [post, patch, put, del]) method.mockResolvedValue({ data: {} });
    useAuthStore.setState({
      accessToken: "token",
      user: { id: "admin", email: "admin@example.org", display_name: "Admin", is_superuser: true, preferred_language: "de", theme: "system", roles: [] },
    });
  });

  describe("users", () => {
    it("creates an account with roles once the password is strong enough", async () => {
      renderAt("/settings/users");
      fireEvent.click(await screen.findByRole("button", { name: "+ Benutzer anlegen" }));
      fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Rita Referee" } });
      fireEvent.change(screen.getByLabelText("E-Mail"), { target: { value: "rita@example.org" } });
      const create = screen.getByRole("button", { name: "Anlegen" });
      fireEvent.change(screen.getByLabelText("Passwort"), { target: { value: "kurz" } });
      expect(create).toBeDisabled();
      fireEvent.change(screen.getByLabelText("Passwort"), { target: { value: STRONG } });
      const roles = screen.getByRole("group", { name: "Rollen" });
      fireEvent.click(await within(roles).findByRole("button", { name: "juror" }));
      expect(within(roles).getByRole("button", { name: "juror" })).toHaveAttribute("aria-pressed", "true");
      fireEvent.click(create);
      await waitFor(() => expect(post).toHaveBeenCalledWith("/auth/users", {
        email: "rita@example.org",
        display_name: "Rita Referee",
        password: STRONG,
        role_ids: ["r-juror"],
      }));
      // The form closes again.
      await waitFor(() => expect(screen.queryByLabelText("Passwort")).not.toBeInTheDocument());
    });

    it("activates, re-roles, resets and deletes accounts", async () => {
      renderAt("/settings/users");
      const jana = (await screen.findByText("Jana Jurorin")).closest("tr")!;
      const paul = screen.getByText("Paul Pause").closest("tr")!;

      fireEvent.click(within(paul).getByRole("button", { name: "Aktivieren" }));
      await waitFor(() => expect(patch).toHaveBeenCalledWith("/auth/users/u2", { is_active: true }));

      fireEvent.click(within(jana).getByRole("button", { name: "Rollen" }));
      const group = within(jana).getByRole("group", { name: "Rollen" });
      fireEvent.click(within(group).getByRole("button", { name: "juror" }));
      fireEvent.click(within(group).getByRole("button", { name: "admin" }));
      fireEvent.click(within(jana).getByRole("button", { name: "Speichern" }));
      await waitFor(() => expect(patch).toHaveBeenCalledWith("/auth/users/u1", { role_ids: ["r-admin"] }));

      fireEvent.click(within(jana).getByRole("button", { name: "Passwort setzen" }));
      expect(screen.getByRole("heading", { name: "Neues Passwort für jana@example.org" })).toBeInTheDocument();
      fireEvent.change(screen.getByLabelText("Neues Passwort"), { target: { value: STRONG } });
      const submit = screen.getAllByRole("button", { name: "Passwort setzen" })[0];
      fireEvent.click(submit);
      await waitFor(() => expect(post).toHaveBeenCalledWith("/auth/users/u1/password", { new_password: STRONG }));

      fireEvent.click(within(jana).getByRole("button", { name: "Löschen" }));
      await confirmDialog("Löschen");
      await waitFor(() => expect(del).toHaveBeenCalledWith("/auth/users/u1"));
    });

    it("does not delete when the confirmation is cancelled", async () => {
      renderAt("/settings/users");
      const paul = (await screen.findByText("Paul Pause")).closest("tr")!;
      fireEvent.click(within(paul).getByRole("button", { name: "Löschen" }));
      await confirmDialog("Abbrechen");
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
      expect(del).not.toHaveBeenCalled();
    });
  });

  describe("competition levels", () => {
    it("adds a level, sets order and qualification, toggles and deletes", async () => {
      renderAt("/settings/levels");
      expect(await screen.findByLabelText("GCER qualifiziert aus")).toBeInTheDocument();
      const add = screen.getByRole("button", { name: "+ Stufe" });
      expect(add).toBeDisabled();
      fireEvent.change(screen.getByPlaceholderText("Senior"), { target: { value: "Junior" } });
      fireEvent.change(screen.getByPlaceholderText("SR"), { target: { value: "JR" } });
      fireEvent.click(add);
      await waitFor(() => expect(post).toHaveBeenCalledWith("/seasons/competition-levels", { name: "Junior", code: "JR", description: null }));

      // GCER qualifies from ECER.
      fireEvent.change(screen.getByLabelText("GCER qualifiziert aus"), { target: { value: "l1" } });
      await waitFor(() => expect(patch).toHaveBeenCalledWith("/seasons/competition-levels/l2", { qualifies_from_level_id: "l1" }));
      const order = screen.getByLabelText("Reihenfolge ECER");
      fireEvent.change(order, { target: { value: "5" } });
      fireEvent.blur(order);
      await waitFor(() => expect(patch).toHaveBeenCalledWith("/seasons/competition-levels/l1", { order: 5 }));

      const ecer = screen.getByLabelText("Reihenfolge ECER").closest("tr")!;
      fireEvent.click(within(ecer).getByRole("button", { name: "Deaktivieren" }));
      await waitFor(() => expect(patch).toHaveBeenCalledWith("/seasons/competition-levels/l1", { is_active: false }));
      fireEvent.click(within(ecer).getByRole("button", { name: "Löschen" }));
      await confirmDialog("Löschen");
      await waitFor(() => expect(del).toHaveBeenCalledWith("/seasons/competition-levels/l1"));
    });
  });

  describe("season modules", () => {
    it("saves only after a change, with modules and categories together", async () => {
      renderAt("/settings/modules");
      const save = await screen.findByRole("button", { name: "Speichern" });
      await waitFor(() => expect(screen.getByRole("checkbox", { name: /Seeding \(Robot Game\)/ })).toBeChecked());
      expect(save).toBeDisabled();
      fireEvent.click(screen.getByRole("checkbox", { name: /Double Elimination/ }));
      fireEvent.click(screen.getByRole("checkbox", { name: /Paper-Scoring/ }));
      expect(save).toBeEnabled();
      fireEvent.click(save);
      await waitFor(() => expect(patch).toHaveBeenCalledWith("/seasons/s1", {
        use_seeding: true,
        use_double_elimination: true,
        use_paper_scoring: false,
        use_documentation_scoring: false,
        use_aerial: false,
        active_categories: ["botball"],
      }));
      expect(await screen.findByText(/gespeichert/i)).toBeInTheDocument();
    });
  });

  describe("announcements", () => {
    it("drafts an announcement for an audience and publishes a draft", async () => {
      renderAt("/settings/announcements");
      const draftRow = (await screen.findByText("Anreise")).closest("tr")!;
      expect(within(draftRow).getByText("Entwurf")).toBeInTheDocument();
      const publishedRow = screen.getByText("Willkommen").closest("tr")!;
      expect(within(publishedRow).queryByRole("button", { name: "Veröffentlichen" })).not.toBeInTheDocument();
      fireEvent.click(within(draftRow).getByRole("button", { name: "Veröffentlichen" }));
      await waitFor(() => expect(put).toHaveBeenCalledWith("/dashboard/announcements/a1/publish"));

      fireEvent.click(screen.getByRole("button", { name: "+ Ankündigung" }));
      const saveDraft = screen.getByRole("button", { name: "Als Entwurf speichern" });
      expect(saveDraft).toBeDisabled();
      fireEvent.change(screen.getByLabelText("Titel"), { target: { value: "Finale" } });
      fireEvent.change(screen.getByLabelText("Text"), { target: { value: "16 Uhr, Tisch 1" } });
      fireEvent.change(screen.getByLabelText("Zielgruppe"), { target: { value: "jurors" } });
      fireEvent.click(saveDraft);
      await waitFor(() => expect(post).toHaveBeenCalledWith("/dashboard/announcements", {
        title: "Finale",
        body: "16 Uhr, Tisch 1",
        audience: "jurors",
      }));
    });

    it("says so when there are none", async () => {
      mockApi({ "/dashboard/announcements?include_unpublished=true": [] });
      renderAt("/settings/announcements");
      expect(await screen.findByText("Keine Ankündigungen")).toBeInTheDocument();
    });
  });
});

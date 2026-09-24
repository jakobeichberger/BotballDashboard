import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { api } from "@/lib/api";
import {
  complianceHint,
  seasonPayload,
  teamFilterParams,
  EMPTY_TEAM_FILTERS,
  type ComplianceStatus,
} from "@/lib/teams";
import { cancelNotice, type PrintJobCancelled } from "@/lib/printing";
import { ComplianceChecklist } from "@/components/teams/ComplianceChecklist";
import { SeasonRegistrations } from "@/components/teams/SeasonRegistrations";
import TeamsPage from "@/pages/TeamsPage";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

function wrap(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

const status = (checked: boolean[]): ComplianceStatus => ({
  team_id: "t1",
  season_id: "s1",
  items: checked.map((isChecked, index) => ({
    item: { id: `i${index}`, season_id: "s1", label: `Regel ${index + 1}`, description: null, sort_order: index, is_active: true },
    checked: isChecked,
    note: null,
    checked_by: null,
    checked_at: null,
    verified_by: null,
    verified_at: null,
  })),
  total: checked.length,
  checked: checked.filter(Boolean).length,
  verified: 0,
  complete: checked.every(Boolean),
  is_verified: false,
});

describe("team helpers", () => {
  it("builds team filter params and needs a season for the team type", () => {
    expect(teamFilterParams(EMPTY_TEAM_FILTERS)).toEqual({});
    expect(teamFilterParams({ ...EMPTY_TEAM_FILTERS, q: "  htl ", category: "open" })).toEqual({ q: "htl" });
    expect(
      teamFilterParams({ q: "", country: "AT", status: "archived", season_id: "s1", category: "open" })
    ).toEqual({ country: "AT", status: "archived", season_id: "s1", category: "open" });
  });

  it("sends only contact fields for mentors", () => {
    const form = {
      category: "open",
      fee_status: "paid",
      kit_status: "sent",
      confirmed: true,
      notes: "",
      contact_name: " Frau Direktor ",
      contact_email: "",
      contact_phone: "123",
      address: "Weg 1",
    };
    expect(seasonPayload(form, false)).toEqual({
      contact_name: "Frau Direktor",
      contact_email: null,
      contact_phone: "123",
      address: "Weg 1",
    });
    expect(seasonPayload(form, true)).toMatchObject({ category: "open", fee_status: "paid", notes: null });
  });

  it("warns only about an incomplete checklist", () => {
    expect(complianceHint(null)).toBeNull();
    expect(complianceHint(status([]))).toBeNull();
    expect(complianceHint(status([true, true]))).toBeNull();
    expect(complianceHint(status([true, false, false]))).toMatch(/2 von 3 Punkten offen/);
  });

  it("describes the printer's answer to a cancel", () => {
    const job = { printer_cancel: "failed", printer_message: "timeout" } as PrintJobCancelled;
    expect(cancelNotice(job)).toMatch(/am Gerät stoppen/);
    expect(cancelNotice({ printer_cancel: "sent", printer_message: "ok" } as PrintJobCancelled)).toMatch(/abgebrochen/);
    expect(cancelNotice({ printer_cancel: "not_applicable", printer_message: null } as PrintJobCancelled)).toBeNull();
  });
});

describe("ComplianceChecklist", () => {
  beforeEach(() => vi.clearAllMocks());

  it("lets the team tick an item", async () => {
    (api.get as any).mockResolvedValue({ data: status([false, true]) });
    (api.put as any).mockResolvedValue({ data: status([true, true]) });
    wrap(<ComplianceChecklist teamId="t1" seasonId="s1" canTick canVerify={false} />);
    const box = await screen.findByLabelText("Regel 1");
    expect(screen.getByText("1 von 2 Punkten bestätigt")).toBeInTheDocument();
    await userEvent.click(box);
    expect(api.put).toHaveBeenCalledWith("/teams/t1/seasons/s1/print-compliance/i0", { checked: true });
    expect(await screen.findByText("2 von 2 Punkten bestätigt")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /geprüft/ })).not.toBeInTheDocument();
  });

  it("lets organizers verify a complete list and seed an empty one", async () => {
    (api.get as any).mockResolvedValueOnce({ data: status([true]) });
    (api.put as any).mockResolvedValue({ data: { ...status([true]), is_verified: true } });
    wrap(<ComplianceChecklist teamId="t1" seasonId="s1" canTick={false} canVerify />);
    await userEvent.click(await screen.findByRole("button", { name: /als geprüft markieren/i }));
    expect(api.put).toHaveBeenCalledWith("/teams/t1/seasons/s1/print-compliance/verify", { verified: true });
    expect(await screen.findByText("von Organisation geprüft")).toBeInTheDocument();
  });

  it("offers the default rules when the season has none", async () => {
    (api.get as any).mockResolvedValue({ data: status([]) });
    (api.post as any).mockResolvedValue({ data: [] });
    wrap(<ComplianceChecklist teamId="t1" seasonId="s1" canTick canVerify />);
    await userEvent.click(await screen.findByRole("button", { name: /standardregeln übernehmen/i }));
    expect(api.post).toHaveBeenCalledWith("/teams/print-compliance/items/defaults", null, { params: { season_id: "s1" } });
  });
});

describe("SeasonRegistrations", () => {
  const registration = {
    id: "r1",
    team_id: "t1",
    season_id: "s1",
    competition_level_id: null,
    registered_at: "2026-01-01T00:00:00Z",
    confirmed: false,
    notes: null,
    category: "botball",
    fee_status: "pending",
    kit_status: "not_sent",
    paper_required: true,
    contact_name: null,
    contact_email: null,
    contact_phone: null,
    address: null,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    (api.get as any).mockImplementation((url: string) =>
      Promise.resolve({ data: url === "/teams/t1/seasons" ? [registration] : [] })
    );
    (api.put as any).mockResolvedValue({ data: registration });
  });

  it("mentors edit only the contact details", async () => {
    wrap(
      <SeasonRegistrations
        teamId="t1"
        members={[]}
        seasonName={() => "Saison 2026"}
        levelName={() => "—"}
        canManage
        isOrganizer={false}
      />
    );
    await userEvent.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    expect(screen.queryByLabelText("Teilnahmegebühr")).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Kontaktperson"), "Herr Lehrer");
    await userEvent.click(screen.getByRole("button", { name: /speichern/i }));
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith("/teams/t1/seasons/s1", {
        contact_name: "Herr Lehrer",
        contact_email: null,
        contact_phone: null,
        address: null,
      })
    );
  });

  it("organizers set fee and kit status", async () => {
    wrap(
      <SeasonRegistrations
        teamId="t1"
        members={[]}
        seasonName={() => "Saison 2026"}
        levelName={() => "—"}
        canManage
        isOrganizer
      />
    );
    await userEvent.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await userEvent.selectOptions(screen.getByLabelText("Teilnahmegebühr"), "paid");
    await userEvent.selectOptions(screen.getByLabelText("Kit-Versand"), "sent");
    await userEvent.click(screen.getByRole("button", { name: /speichern/i }));
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith(
        "/teams/t1/seasons/s1",
        expect.objectContaining({ fee_status: "paid", kit_status: "sent", category: "botball" })
      )
    );
  });
});

describe("TeamsPage search", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      accessToken: "token",
      user: { id: "admin", email: "admin@example.org", display_name: "Admin", is_superuser: true, preferred_language: "de", theme: "system", roles: [] } as any,
    });
    (api.get as any).mockImplementation((url: string) => {
      if (url === "/teams/countries") return Promise.resolve({ data: ["AT", "DE"] });
      return Promise.resolve({ data: [] });
    });
  });

  it("passes search text and filters to the API", async () => {
    wrap(<TeamsPage />);
    await userEvent.type(screen.getByPlaceholderText("Name, Nummer, Schule oder Ort"), "htl");
    await userEvent.selectOptions(await screen.findByLabelText("Land"), "AT");
    await userEvent.selectOptions(screen.getByLabelText("Status"), "archived");
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith("/teams", { params: { q: "htl", country: "AT", status: "archived" } })
    );
    expect(await screen.findByText("Keine Teams gefunden")).toBeInTheDocument();
  });
});

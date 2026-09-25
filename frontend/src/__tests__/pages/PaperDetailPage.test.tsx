import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import PaperDetailPage from "@/pages/PaperDetailPage";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }));

const feedback = {
  id: "f1",
  revision_number: 1,
  version_number: 1,
  score_content: 8,
  score_implementation: 7,
  score_results: 6,
  score_language: 9,
  score_format: 10,
  comment_content: null,
  comment_implementation: null,
  comment_results: "Mehr Messdaten",
  comment_language: null,
  comment_format: null,
  total_score: 8,
  comments: "Gute Arbeit",
  revision_notes: "Abschnitt 3 kürzen",
  recommendation: "revision_minor",
  submitted_at: "2026-03-20T10:00:00Z",
};

function makePaper(overrides: Record<string, unknown> = {}) {
  return {
    id: "p1",
    season_id: "s1",
    event_id: "e1",
    team_id: "t1",
    title: "Swarm Robotics",
    abstract: "Abstract",
    competition_level_id: null,
    status: "revision_requested",
    file_name: "v2.pdf",
    file_size_bytes: 2048,
    submitted_at: "2026-03-10T10:00:00Z",
    revision_number: 2,
    current_version: 2,
    final_score: null,
    paper_rank: null,
    format_deduction: 0,
    format_deduction_reason: null,
    finalized_at: null,
    reviews: [],
    assignments: [],
    versions: [
      { id: "v1", version_number: 1, revision_number: 1, file_name: "v1.pdf", file_size_bytes: 1024, uploaded_by: null, uploaded_at: "2026-03-01T10:00:00Z", submitted_at: "2026-03-01T11:00:00Z" },
      { id: "v2", version_number: 2, revision_number: 2, file_name: "v2.pdf", file_size_bytes: 2048, uploaded_by: null, uploaded_at: "2026-03-21T10:00:00Z", submitted_at: null },
    ],
    feedback: [feedback],
    deadline: { deadline_date: "2026-03-15", timezone: "Europe/Vienna", cutoff_at: "2026-03-15T23:00:00Z", passed: true, locked: true, can_override: false },
    ...overrides,
  };
}

function mockApi(paper: ReturnType<typeof makePaper>) {
  (api.get as any).mockImplementation((url: string) => {
    if (url === "/papers/p1") return Promise.resolve({ data: paper });
    if (url === "/teams/mine") return Promise.resolve({ data: [{ id: "t1" }] });
    if (url === "/teams") return Promise.resolve({ data: [{ id: "t1", name: "Team Alpha" }] });
    return Promise.resolve({ data: [] });
  });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/papers/p1"]}>
        <Routes>
          <Route path="/papers/:id" element={<PaperDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function asMentor() {
  useAuthStore.setState({
    user: {
      id: "mentor",
      email: "m@x",
      display_name: "Mentor",
      is_superuser: false,
      preferred_language: "de",
      theme: "light",
      roles: [{ id: "r", name: "mentor", description: null }],
      permissions: ["papers:read", "papers:write"],
    },
  });
}

describe("PaperDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    asMentor();
  });

  it("shows the team its released feedback without reviewer names", async () => {
    mockApi(makePaper());
    renderPage();
    const section = (await screen.findByRole("heading", { name: /feedback der reviewer/i })).closest("section")!;
    expect(within(section).getByText("Mehr Messdaten")).toBeInTheDocument();
    expect(within(section).getByText("Abschnitt 3 kürzen")).toBeInTheDocument();
    expect(within(section).getByText("Kleine Überarbeitung")).toBeInTheDocument();
    expect(within(section).getByText(/Review 1 · Runde 1 · v1/)).toBeInTheDocument();
  });

  it("explains that feedback appears after the decision", async () => {
    mockApi(makePaper({ status: "under_review", feedback: [] }));
    renderPage();
    expect(await screen.findByText(/sobald über die review-runde entschieden ist/i)).toBeInTheDocument();
  });

  it("lists every version with its own download", async () => {
    mockApi(makePaper());
    renderPage();
    expect(await screen.findByText("v1.pdf")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Version 1 herunterladen" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Version 2 herunterladen" })).toBeInTheDocument();
  });

  it("downloads a specific version with ?version=", async () => {
    mockApi(makePaper());
    (globalThis.URL as any).createObjectURL = vi.fn(() => "blob:x");
    (globalThis.URL as any).revokeObjectURL = vi.fn();
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: "Version 1 herunterladen" }));
    expect(api.get).toHaveBeenCalledWith("/papers/p1/download", { params: { version: 1 }, responseType: "blob" });
  });

  it("does not lock a requested revision because of the first-round deadline", async () => {
    mockApi(makePaper());
    renderPage();
    const resubmit = await screen.findByRole("button", { name: /v2 erneut einreichen/i });
    expect(resubmit).toBeEnabled();
  });

  it("locks upload and submit after the deadline in the first round", async () => {
    mockApi(makePaper({ status: "draft", revision_number: 1, feedback: [] }));
    renderPage();
    expect(await screen.findByText("Gesperrt")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^einreichen$/i })).toBeDisabled();
  });

  it("locks the reviewer form once the review is submitted", async () => {
    useAuthStore.setState({
      user: {
        id: "rev",
        email: "r@x",
        display_name: "Rev",
        is_superuser: false,
        preferred_language: "de",
        theme: "light",
        roles: [{ id: "r", name: "reviewer", description: null }],
        permissions: ["papers:read", "papers:review"],
      },
    });
    mockApi(
      makePaper({
        status: "under_review",
        feedback: [],
        assignments: [{ id: "a1", reviewer_id: "rev", assigned_at: "2026-03-02T00:00:00Z", due_at: null, status: "completed", version_number: 2, reminder_sent_at: null, completed_at: null }],
        reviews: [{ ...feedback, id: "rv", revision_number: 2, paper_id: "p1", reviewer_id: "rev", private_notes: null, is_submitted: true, created_at: "2026-03-02T00:00:00Z" }],
      })
    );
    renderPage();
    expect(await screen.findByText(/abgegeben und gesperrt/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /bewertung abgeben/i })).toBeDisabled();
    expect(screen.getByLabelText("Formales (0–10)")).toHaveValue(10);
  });
});

describe("PaperDetailPage reviewer reminders and status history", () => {
  const assignments = [
    { id: "a1", reviewer_id: "rev1", assigned_at: "2026-03-02T10:00:00Z", due_at: null, status: "pending", version_number: 2, reminder_sent_at: "2026-03-05T08:00:00Z", completed_at: null },
    { id: "a2", reviewer_id: "rev2", assigned_at: "2026-03-02T10:00:00Z", due_at: null, status: "completed", version_number: 2, reminder_sent_at: null, completed_at: "2026-03-04T10:00:00Z" },
  ];
  const history = [
    { id: "h2", paper_id: "p1", from_status: "submitted", to_status: "under_review", reason: "Reviewer zugewiesen", changed_by: "org", changed_at: "2026-03-02T10:00:00Z" },
    { id: "h1", paper_id: "p1", from_status: null, to_status: "draft", reason: null, changed_by: "org", changed_at: "2026-03-01T10:00:00Z" },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    const paper = makePaper({ status: "under_review", assignments });
    (api.get as any).mockImplementation((url: string) => {
      if (url === "/papers/p1") return Promise.resolve({ data: paper });
      if (url === "/papers/p1/history") return Promise.resolve({ data: history });
      if (url === "/auth/users") return Promise.resolve({ data: [{ id: "rev1", display_name: "Rita Reviewer" }, { id: "rev2", display_name: "Rolf" }, { id: "org", display_name: "Orga" }] });
      return Promise.resolve({ data: [] });
    });
    (api.post as any).mockResolvedValue({ data: {} });
  });

  function asOrganizer() {
    useAuthStore.setState({
      user: { id: "org", email: "o@x", display_name: "Orga", is_superuser: false, preferred_language: "de", theme: "light", roles: [], permissions: ["papers:read", "papers:admin", "users:read"] },
    });
  }

  it("lets organizers remind reviewers with open reviews", async () => {
    asOrganizer();
    renderPage();
    const remind = await screen.findByRole("button", { name: "Rita Reviewer an das Review erinnern" });
    expect(screen.queryByRole("button", { name: "Rolf an das Review erinnern" })).not.toBeInTheDocument();
    expect(remind.closest("tr")).toHaveTextContent("erinnert am");
    await userEvent.click(remind);
    expect(api.post).toHaveBeenCalledWith("/papers/p1/assignments/a1/remind");
  });

  it("shows the status history to everyone who can read the paper", async () => {
    asMentor();
    renderPage();
    const section = (await screen.findByRole("heading", { name: "Statusverlauf" })).closest("section")!;
    const items = within(section).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Reviewer zugewiesen");
    expect(screen.queryByRole("button", { name: /an das Review erinnern/ })).not.toBeInTheDocument();
  });
});

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { api } from "@/lib/api";
import { DeadlineBanner } from "@/modules/papers/DeadlineBanner";
import { VersionDiff } from "@/modules/papers/VersionDiff";
import { AutoAssignPanel } from "@/modules/papers/AutoAssignPanel";
import { diffLineClass, passedInternalDeadlines, type PaperDeadline, type PaperVersion } from "@/modules/papers/paperMeta";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

function wrap(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{children}</QueryClientProvider>);
}

const version = (n: number): PaperVersion => ({
  id: `v${n}`,
  version_number: n,
  revision_number: 1,
  file_name: `paper-v${n}.pdf`,
  file_size_bytes: 100,
  uploaded_by: null,
  uploaded_at: "2026-03-01T10:00:00Z",
  submitted_at: null,
});

const meta = (n: number) => ({ version_number: n, file_name: `paper-v${n}.pdf`, file_size_bytes: 100, uploaded_at: "2026-03-01T10:00:00Z", pages: 1 });

describe("paper helpers", () => {
  it("colours diff lines", () => {
    expect(diffLineClass("+new")).toContain("green");
    expect(diffLineClass("-old")).toContain("red");
    expect(diffLineClass("@@ -1 +1 @@")).toContain("blue");
    expect(diffLineClass("--- v1")).toBe("text-gray-500");
  });

  it("picks passed internal deadlines only", () => {
    const deadline = {
      deadlines: [
        { id: "1", deadline_type: "internal_draft", due_date: "2026-03-01", label: null, is_hard_block: false, cutoff_at: "", passed: true },
        { id: "2", deadline_type: "official_submission", due_date: "2026-03-02", label: null, is_hard_block: true, cutoff_at: "", passed: true },
        { id: "3", deadline_type: "internal_final", due_date: "2026-04-01", label: null, is_hard_block: false, cutoff_at: "", passed: false },
      ],
    } as PaperDeadline;
    expect(passedInternalDeadlines(deadline).map((d) => d.id)).toEqual(["1"]);
  });

  it("warns about a passed internal deadline without locking", () => {
    const deadline: PaperDeadline = {
      deadline_date: null,
      timezone: "Europe/Vienna",
      cutoff_at: null,
      passed: false,
      locked: false,
      can_override: false,
      deadlines: [
        { id: "1", deadline_type: "internal_draft", due_date: "2026-03-01", label: "Entwurf", is_hard_block: false, cutoff_at: "", passed: true },
      ],
    };
    render(<DeadlineBanner deadline={deadline} />);
    expect(screen.getByText(/Interne Frist abgelaufen/)).toHaveTextContent("Entwurf");
    expect(screen.getByText(/Hochladen bleibt möglich/)).toBeInTheDocument();
  });
});

describe("VersionDiff", () => {
  beforeEach(() => vi.clearAllMocks());

  it("is hidden with a single version", () => {
    const { container } = wrap(<VersionDiff paperId="p1" versions={[version(1)]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the text diff of the previous and latest version", async () => {
    (api.get as any).mockResolvedValue({
      data: {
        from_version: meta(1),
        to_version: meta(2),
        text_available: true,
        reason: null,
        diff: ["--- v1", "+++ v2", "@@ -1 +1 @@", "-We built a robot.", "+We built two robots."],
        added: 1,
        removed: 1,
        truncated: false,
      },
    });
    wrap(<VersionDiff paperId="p1" versions={[version(1), version(2)]} />);
    await userEvent.click(screen.getByRole("button", { name: /versionen vergleichen/i }));
    expect(await screen.findByText("+We built two robots.")).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith("/papers/p1/versions/diff", { params: { from_version: 1, to_version: 2 } });
    expect(screen.getByText("+1 Zeilen")).toBeInTheDocument();
  });

  it("explains when only metadata can be compared", async () => {
    (api.get as any).mockResolvedValue({
      data: {
        from_version: meta(1),
        to_version: meta(2),
        text_available: false,
        reason: "The PDF contains no extractable text",
        diff: [],
        added: 0,
        removed: 0,
        truncated: false,
      },
    });
    wrap(<VersionDiff paperId="p1" versions={[version(1), version(2)]} />);
    await userEvent.click(screen.getByRole("button", { name: /versionen vergleichen/i }));
    expect(await screen.findByText(/Kein Textvergleich möglich/)).toHaveTextContent("no extractable text");
  });
});

describe("AutoAssignPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("previews first, then assigns", async () => {
    (api.post as any)
      .mockResolvedValueOnce({
        data: {
          dry_run: true,
          assignments: [{ paper_id: "p1", paper_title: "Swarm", reviewer_id: "r1", reviewer_name: "Rita" }],
          unfilled: [{ paper_id: "p2", paper_title: "Lonely", missing: 1 }],
        },
      })
      .mockResolvedValueOnce({ data: { dry_run: false, assignments: [], unfilled: [] } });
    wrap(<AutoAssignPanel seasonId="s1" eventId="e1" />);
    const assign = screen.getByRole("button", { name: "Zuweisen" });
    expect(assign).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Vorschau" }));
    expect(await screen.findByText("Swarm → Rita")).toBeInTheDocument();
    expect(screen.getByText(/Lonely \(1 fehlen\)/)).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledWith("/papers/auto-assign", {
      season_id: "s1",
      event_id: "e1",
      reviewers_per_paper: 2,
      dry_run: true,
    });
    await userEvent.click(assign);
    expect(api.post).toHaveBeenLastCalledWith("/papers/auto-assign", expect.objectContaining({ dry_run: false }));
  });
});

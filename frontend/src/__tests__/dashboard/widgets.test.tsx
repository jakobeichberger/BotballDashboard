import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Trophy, Users } from "lucide-react";
import {
  StatCard,
  StatGrid,
  SectionCard,
  PhaseTimeline,
  AnnouncementsList,
  ShortcutGrid,
  RankingList,
  ReviewQueue,
} from "@/pages/dashboard/widgets";

const router = (ui: React.ReactNode) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe("StatCard / StatGrid", () => {
  it("renders label and value as a listitem", () => {
    render(<StatCard label="Teams" value={7} icon={Users} />);
    const item = screen.getByRole("listitem");
    expect(within(item).getByText("Teams")).toBeInTheDocument();
    expect(within(item).getByText("7")).toBeInTheDocument();
  });

  it("renders a labelled list of stat cards", () => {
    render(
      <StatGrid
        ariaLabel="Kennzahlen"
        items={[
          { label: "Teams", value: 3, icon: Users },
          { label: "Wertungen", value: 9, icon: Trophy },
        ]}
      />
    );
    const list = screen.getByRole("list", { name: "Kennzahlen" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
  });
});

describe("SectionCard", () => {
  it("associates the heading with the section via aria-labelledby", () => {
    render(
      <SectionCard title="Phasen" id="x">
        <p>content</p>
      </SectionCard>
    );
    const section = screen.getByRole("region", { name: "Phasen" });
    expect(section).toBeInTheDocument();
    expect(within(section).getByRole("heading", { name: "Phasen" })).toBeInTheDocument();
  });

  it("renders an action node when provided", () => {
    render(
      <SectionCard title="T" id="y" action={<button>Mehr</button>}>
        <p>c</p>
      </SectionCard>
    );
    expect(screen.getByRole("button", { name: "Mehr" })).toBeInTheDocument();
  });
});

describe("PhaseTimeline", () => {
  it("shows an empty hint when no phases", () => {
    render(<PhaseTimeline phases={[]} />);
    expect(screen.getByText(/keine phasen/i)).toBeInTheDocument();
  });

  it("renders phases and marks the active one", () => {
    render(
      <PhaseTimeline
        phases={[
          { id: "1", name: "Quali", phase_type: "qualification", is_active: false },
          { id: "2", name: "Finale", phase_type: "final", is_active: true },
        ]}
      />
    );
    expect(screen.getByText("Quali")).toBeInTheDocument();
    expect(screen.getByText("Finale")).toBeInTheDocument();
    expect(screen.getByText("Aktiv")).toBeInTheDocument();
  });
});

describe("AnnouncementsList", () => {
  it("shows an empty hint when no announcements", () => {
    render(<AnnouncementsList announcements={[]} />);
    expect(screen.getByText(/keine aktuellen ankündigungen/i)).toBeInTheDocument();
  });

  it("renders title, body and a machine-readable date", () => {
    render(
      <AnnouncementsList
        announcements={[
          { id: "a", title: "Hallo", body: "Welt", published_at: "2026-06-20T10:00:00Z" },
        ]}
      />
    );
    expect(screen.getByText("Hallo")).toBeInTheDocument();
    expect(screen.getByText("Welt")).toBeInTheDocument();
    const time = document.querySelector("time");
    expect(time).toHaveAttribute("dateTime", "2026-06-20T10:00:00Z");
  });
});

describe("ShortcutGrid", () => {
  it("renders accessible links", () => {
    router(
      <ShortcutGrid
        items={[
          { to: "/teams", label: "Teams", icon: Users },
          { to: "/scoring", label: "Scoring", icon: Trophy },
        ]}
      />
    );
    expect(screen.getByRole("link", { name: "Teams" })).toHaveAttribute("href", "/teams");
    expect(screen.getByRole("link", { name: "Scoring" })).toHaveAttribute("href", "/scoring");
  });
});

describe("RankingList", () => {
  it("shows an empty hint when no entries", () => {
    render(<RankingList entries={[]} teams={{}} />);
    expect(screen.getByText(/noch keine wertungen/i)).toBeInTheDocument();
  });

  it("renders a ranking table with team names resolved from the map", () => {
    render(
      <RankingList
        entries={[{ team_id: "t1", rank: 1, seed_score: 42.5 }]}
        teams={{ t1: "Alpha Bots" }}
      />
    );
    const table = screen.getByRole("table");
    expect(within(table).getByText("Alpha Bots")).toBeInTheDocument();
    expect(within(table).getByText("42.5")).toBeInTheDocument();
  });

  it("prefers an inline team_name over the map", () => {
    render(
      <RankingList
        entries={[{ team_id: "t1", rank: 1, seed_score: 10, team_name: "Inline Team" }]}
        teams={{ t1: "Map Team" }}
      />
    );
    expect(screen.getByText("Inline Team")).toBeInTheDocument();
  });
});

describe("ReviewQueue", () => {
  it("shows an empty hint when no papers", () => {
    router(<ReviewQueue papers={[]} />);
    expect(screen.getByText(/keine paper zur begutachtung/i)).toBeInTheDocument();
  });

  it("renders papers with status and an open link", () => {
    router(
      <ReviewQueue
        papers={[{ id: "p1", title: "CV Navigation", status: "under_review" }]}
      />
    );
    expect(screen.getByText("CV Navigation")).toBeInTheDocument();
    expect(screen.getByText("under_review")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /öffnen/i })[0]).toHaveAttribute("href", "/papers");
  });
});

import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import BracketView from "@/components/BracketView";
import { groupBracket, isDecidable, winnerOf } from "@/lib/bracket";
import type { BracketPhase, ScheduledMatch } from "@/api/types";

function match(
  code: string,
  bracket: string,
  round: number,
  teams: Array<[string, string | null]> = [],
  extra: Partial<ScheduledMatch> = {},
): ScheduledMatch {
  return {
    id: code,
    event_id: "e1",
    phase_id: "p1",
    code,
    round_number: round,
    sequence_number: 1,
    table_number: 1,
    scheduled_at: null,
    duration_minutes: 10,
    status: "scheduled",
    bracket,
    round_kind: bracket === "loser" ? (round % 2 ? "minor" : "major") : null,
    version: 1,
    participants: teams.map(([id, result], index) => ({
      id: `${code}-${id}`,
      team_id: id,
      team_name: `Team ${id}`,
      team_number: null,
      position: index + 1,
      side: null,
      result,
    })),
    ...extra,
  };
}

const MATCHES = [
  match("2-W2-1", "winner", 2),
  match("2-W1-2", "winner", 1, [["c", null], ["d", null]]),
  match("2-W1-1", "winner", 1, [["a", "win"], ["b", "loss"]], { status: "completed" }),
  match("2-L2-1", "loser", 2),
  match("2-L1-1", "loser", 1, [["b", null]]),
  match("2-GF", "final", 1),
  match("2-GF2", "final", 2, [], { status: "cancelled" }),
];

describe("groupBracket", () => {
  it("groups sections and rounds in display order", () => {
    const groups = groupBracket(MATCHES);
    expect(groups.map((group) => group.section)).toEqual(["winner", "loser", "final"]);
    const [winners, losers] = groups;
    expect(winners.columns.map((column) => column.round)).toEqual([1, 2]);
    expect(winners.columns[0].matches.map((item) => item.code)).toEqual(["2-W1-1", "2-W1-2"]);
    expect(losers.columns.map((column) => column.kind)).toEqual(["minor", "major"]);
  });

  it("knows decidable matches and winners", () => {
    expect(isDecidable(MATCHES[1])).toBe(true);
    expect(isDecidable(MATCHES[4])).toBe(false);
    expect(isDecidable(MATCHES[6])).toBe(false);
    expect(winnerOf(MATCHES[2])).toBe("a");
    expect(winnerOf(MATCHES[1])).toBeNull();
  });
});

describe("BracketView", () => {
  const phase: BracketPhase = {
    phase_id: "p1",
    phase_name: "Double Elimination",
    phase_type: "double_elimination",
    status: "live",
    bracket_label: "A",
    matches: MATCHES,
    placements: [{ team_id: "a", team_name: "Team a", team_number: null, rank: 1 }],
  };

  it("renders every match and the placements", () => {
    render(<BracketView phases={[phase]} />);
    for (const item of MATCHES) {
      expect(screen.getByTestId(`bracket-match-${item.code}`)).toBeInTheDocument();
    }
    expect(screen.getByText("1.")).toBeInTheDocument();
    // Read-only without a handler.
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("lets scorers pick the winner of a decidable match", () => {
    const onPick = vi.fn();
    render(<BracketView phases={[phase]} onPickWinner={onPick} />);
    const card = screen.getByTestId("bracket-match-2-W1-2");
    fireEvent.click(within(card).getAllByRole("button")[1]);
    expect(onPick).toHaveBeenCalledWith(MATCHES[1], "d");
    // Matches with an unknown opponent cannot be decided yet.
    expect(within(screen.getByTestId("bracket-match-2-L1-1")).queryAllByRole("button")).toHaveLength(0);
  });

  it("names the tie-breaker that ordered a shared placement", () => {
    const shared: BracketPhase = {
      ...phase,
      placements: [
        { team_id: "c", team_name: "Team c", team_number: null, rank: 5, placement: 5, decided_by: "Most full cups" },
        { team_id: "d", team_name: "Team d", team_number: null, rank: 5, placement: 6, decided_by: null },
      ],
    };
    render(<BracketView phases={[shared]} />);
    expect(screen.getAllByText("5.")).toHaveLength(2);
    expect(screen.getByText("(Most full cups)")).toBeInTheDocument();
  });

  it("renders nothing without elimination phases", () => {
    const { container } = render(<BracketView phases={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

import type { ScheduledMatch } from "@/api/types";

export type BracketSection = "winner" | "loser" | "final";

export interface BracketColumn {
  round: number;
  /** "minor" / "major" for loser-bracket rounds. */
  kind: string | null;
  matches: ScheduledMatch[];
}

export interface BracketSectionGroup {
  section: BracketSection;
  columns: BracketColumn[];
}

const SECTION_ORDER: BracketSection[] = ["winner", "loser", "final"];

/**
 * Group the matches of one elimination phase into sections (winner bracket,
 * loser bracket, finals) with one column per round, ordered for display.
 */
export function groupBracket(matches: ScheduledMatch[]): BracketSectionGroup[] {
  const sections = new Map<BracketSection, Map<number, ScheduledMatch[]>>();
  for (const match of matches) {
    const section = (match.bracket ?? "winner") as BracketSection;
    if (!SECTION_ORDER.includes(section)) continue;
    const rounds = sections.get(section) ?? new Map<number, ScheduledMatch[]>();
    rounds.set(match.round_number, [...(rounds.get(match.round_number) ?? []), match]);
    sections.set(section, rounds);
  }
  return SECTION_ORDER.filter((section) => sections.has(section)).map((section) => ({
    section,
    columns: [...(sections.get(section) ?? new Map()).entries()]
      .sort(([a], [b]) => a - b)
      .map(([round, roundMatches]) => ({
        round,
        kind: roundMatches[0]?.round_kind ?? null,
        matches: [...roundMatches].sort((a, b) => a.code.localeCompare(b.code, undefined, { numeric: true })),
      })),
  }));
}

/** A match can be decided once both teams are known and it is not finished or void. */
export function isDecidable(match: ScheduledMatch): boolean {
  return (
    match.participants.filter((participant) => participant.team_id).length === 2 &&
    match.status !== "cancelled"
  );
}

export function winnerOf(match: ScheduledMatch): string | null {
  return match.participants.find((participant) => participant.result === "win")?.team_id ?? null;
}

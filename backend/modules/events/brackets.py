"""Pure bracket construction and placement logic (no database access).

Single and double elimination brackets are built for the next power of two
(``size``) and then pruned: a match with a bye is not played, its only real
participant moves straight on. Seeds are placed in the standard recursive
order (1, 8, 4, 5, 2, 7, 3, 6 for eight slots), so every seed meets the
weakest remaining seed first, byes go to the top seeds, and seeds 1 and 2 can
only meet in the (winner-bracket) final.

Double elimination layout for ``k = log2(size)`` winner rounds:

* Winner bracket (``W``) rounds 1..k.
* Loser bracket (``L``) rounds 1..2(k-1), alternating:
  - odd rounds are *minor* rounds: loser-bracket teams play each other
    (round 1: the losers of winner round 1);
  - even round ``2j`` is a *major* round: the survivors meet the losers of
    winner round ``j + 1`` dropping down. The last major round receives the
    loser of the winner-bracket final.
  Drop-downs are fed in reversed order on every other major round so teams
  that met in the winner bracket do not meet again straight away.
* Grand final (``GF``): winner-bracket champion (position 1) against the
  loser-bracket champion (position 2), and a conditional reset final
  (``GF2``) that is only played when the loser-bracket champion wins the
  grand final — nobody is out before their second loss.

With byes pruned a field of ``n`` teams plays ``2n - 2`` matches, or
``2n - 1`` when the reset final is needed.
"""

from dataclasses import dataclass, field

WINNER = "winner"
LOSER = "loser"
FINAL = "final"

# ("team", team_id) | ("bye", None) | ("winner", node_key) | ("loser", node_key)
Source = tuple[str, str | None]


@dataclass
class BracketNode:
    """One match of the pruned bracket that is actually played."""

    key: str
    bracket: str  # winner | loser | final
    round_number: int
    position: int  # 0-based index within its round (before pruning)
    teams: dict[int, str] = field(default_factory=dict)  # slot (1|2) → team placed up front
    next_winner: str | None = None
    next_winner_slot: int | None = None
    next_loser: str | None = None
    next_loser_slot: int | None = None
    depth: int = 0  # earliest wave in which the match can be played

    @property
    def is_reset(self) -> bool:
        return self.bracket == FINAL and self.round_number == 2

    @property
    def round_kind(self) -> str | None:
        if self.bracket != LOSER:
            return None
        return "minor" if self.round_number % 2 else "major"


def bracket_order(size: int) -> list[int]:
    """Seed of every bracket slot, top to bottom (``size`` is a power of two).

    Built recursively: each seed ``s`` of the half-size order is followed by
    its opponent ``2 * len + 1 - s``. The two halves of the result contain
    seeds 1 and 2 respectively.
    """
    if size < 1 or size & (size - 1):
        raise ValueError("Bracket size must be a power of two")
    order = [1]
    while len(order) < size:
        total = len(order) * 2 + 1
        order = [seed for top in order for seed in (top, total - top)]
    return order


def bracket_size(team_count: int) -> int:
    return 1 if team_count <= 1 else 1 << (team_count - 1).bit_length()


def seed_pairings(team_ids: list[str]) -> list[tuple[str | None, str | None]]:
    """First-round pairs in bracket order; ``None`` marks a bye.

    ``team_ids`` must be sorted by seed (index 0 = seed 1). With a field that
    is not a power of two the top seeds face a bye.
    """
    size = max(2, bracket_size(len(team_ids)))
    order = bracket_order(size)

    def team(seed: int) -> str | None:
        return team_ids[seed - 1] if seed <= len(team_ids) else None

    return [(team(order[i]), team(order[i + 1])) for i in range(0, size, 2)]


@dataclass
class _Raw:
    key: str
    bracket: str
    round_number: int
    position: int
    sources: list[Source]


def _winner_key(round_number: int, index: int) -> str:
    return f"W{round_number}-{index + 1}"


def _loser_key(round_number: int, index: int) -> str:
    return f"L{round_number}-{index + 1}"


def _raw_bracket(team_ids: list[str], double_elimination: bool) -> list[_Raw]:
    size = max(2, bracket_size(len(team_ids)))
    rounds = size.bit_length() - 1
    raw: list[_Raw] = []

    for index, (top, bottom) in enumerate(seed_pairings(team_ids)):
        raw.append(
            _Raw(
                _winner_key(1, index),
                WINNER,
                1,
                index,
                [
                    ("team", top) if top else ("bye", None),
                    ("team", bottom) if bottom else ("bye", None),
                ],
            )
        )
    for round_number in range(2, rounds + 1):
        for index in range(size >> round_number):
            raw.append(
                _Raw(
                    _winner_key(round_number, index),
                    WINNER,
                    round_number,
                    index,
                    [
                        ("winner", _winner_key(round_number - 1, 2 * index)),
                        ("winner", _winner_key(round_number - 1, 2 * index + 1)),
                    ],
                )
            )
    if not double_elimination:
        return raw

    if rounds == 1:
        # Two teams: the loser of the only winner-bracket match gets a second
        # chance directly in the grand final.
        grand_final_sources: list[Source] = [
            ("winner", _winner_key(1, 0)),
            ("loser", _winner_key(1, 0)),
        ]
    else:
        for index in range(size >> 2):
            raw.append(
                _Raw(
                    _loser_key(1, index),
                    LOSER,
                    1,
                    index,
                    [
                        ("loser", _winner_key(1, 2 * index)),
                        ("loser", _winner_key(1, 2 * index + 1)),
                    ],
                )
            )
        for step in range(1, rounds):
            major = 2 * step
            count = size >> (step + 1)
            for index in range(count):
                drop = count - 1 - index if step % 2 else index
                raw.append(
                    _Raw(
                        _loser_key(major, index),
                        LOSER,
                        major,
                        index,
                        [
                            ("winner", _loser_key(major - 1, index)),
                            ("loser", _winner_key(step + 1, drop)),
                        ],
                    )
                )
            if step < rounds - 1:
                for index in range(size >> (step + 2)):
                    raw.append(
                        _Raw(
                            _loser_key(major + 1, index),
                            LOSER,
                            major + 1,
                            index,
                            [
                                ("winner", _loser_key(major, 2 * index)),
                                ("winner", _loser_key(major, 2 * index + 1)),
                            ],
                        )
                    )
        grand_final_sources = [
            ("winner", _winner_key(rounds, 0)),
            ("winner", _loser_key(2 * (rounds - 1), 0)),
        ]
    raw.append(_Raw("GF", FINAL, 1, 0, grand_final_sources))
    return raw


def elimination_blueprint(team_ids: list[str], double_elimination: bool) -> list[BracketNode]:
    """Build the pruned bracket for ``team_ids`` (sorted by seed).

    Returns the matches that are actually played, in dependency order, each
    with the teams already known (byes resolved) and links telling where its
    winner and loser go. The loser of a match without ``next_loser`` is out.
    The grand final links both teams to the reset final, which is played only
    when the loser-bracket side wins the grand final.
    """
    if len(team_ids) < 2:
        raise ValueError("An elimination bracket needs at least two teams")
    if len(set(team_ids)) != len(team_ids):
        raise ValueError("A team can only be seeded once")

    # What each match hands on after bye pruning: the real match it came from,
    # a team moving on without playing, or a bye.
    outputs: dict[tuple[str, str], Source] = {}
    nodes: dict[str, BracketNode] = {}
    ordered: list[BracketNode] = []

    for item in _raw_bracket(team_ids, double_elimination):
        resolved: list[Source] = [
            source if source[0] in ("team", "bye") else outputs[(source[0], str(source[1]))]
            for source in item.sources
        ]
        real = [source for source in resolved if source[0] != "bye"]
        if len(real) < 2:
            # Not played: the only real participant (if any) advances, the
            # "loser" is a bye.
            outputs[("winner", item.key)] = real[0] if real else ("bye", None)
            outputs[("loser", item.key)] = ("bye", None)
            continue
        node = BracketNode(item.key, item.bracket, item.round_number, item.position)
        depth = 0
        for slot, source in enumerate(resolved, start=1):
            kind, ref = source
            if kind == "team":
                node.teams[slot] = str(ref)
                continue
            origin = nodes[str(ref)]
            depth = max(depth, origin.depth + 1)
            if kind == "winner":
                origin.next_winner, origin.next_winner_slot = node.key, slot
            else:
                origin.next_loser, origin.next_loser_slot = node.key, slot
        node.depth = depth
        nodes[node.key] = node
        ordered.append(node)
        outputs[("winner", item.key)] = ("winner", item.key)
        outputs[("loser", item.key)] = ("loser", item.key)

    if double_elimination:
        grand_final = nodes["GF"]
        reset = BracketNode("GF2", FINAL, 2, 0, depth=grand_final.depth + 1)
        grand_final.next_winner, grand_final.next_winner_slot = reset.key, None
        grand_final.next_loser, grand_final.next_loser_slot = reset.key, None
        nodes[reset.key] = reset
        ordered.append(reset)
    return ordered


@dataclass
class MatchOutcome:
    """The state of one played bracket match, as needed for placements."""

    key: str
    bracket: str
    round_number: int
    next_loser: str | None
    winner: str | None = None
    loser: str | None = None
    winner_position: int | None = None  # participant position (1|2) of the winner
    completed: bool = False
    cancelled: bool = False


def elimination_placements(matches: list[MatchOutcome], team_count: int) -> dict[str, int]:
    """Final placements known so far (1, 2, 3, 4, 5-6, 7-8, … style).

    Teams knocked out in the same round share a placement: a team eliminated
    in a round is placed behind every team still in the bracket after that
    round, i.e. ``team_count - eliminated_up_to_this_round + 1``. The number
    eliminated per round is fixed by the bracket structure (every eliminating
    match removes exactly one team), so placements are final as soon as a team
    is out. Teams still in the bracket are not included.
    """
    eliminating = [
        match for match in matches if match.bracket != FINAL and match.next_loser is None
    ]
    per_round: dict[tuple[str, int], int] = {}
    for match in eliminating:
        stage = (match.bracket, match.round_number)
        per_round[stage] = per_round.get(stage, 0) + 1
    cumulative: dict[tuple[str, int], int] = {}
    running = 0
    for stage in sorted(per_round, key=lambda item: (item[0] == WINNER, item[1])):
        running += per_round[stage]
        cumulative[stage] = running

    places: dict[str, int] = {}
    for match in eliminating:
        if match.completed and match.loser:
            places[match.loser] = team_count - cumulative[(match.bracket, match.round_number)] + 1

    by_key = {match.key: match for match in matches}
    grand_final = by_key.get("GF")
    reset = by_key.get("GF2")
    if grand_final and grand_final.completed and grand_final.winner and grand_final.loser:
        if grand_final.winner_position == 1:
            # The winner-bracket champion wins: second loss for the other side.
            places[grand_final.winner] = 1
            places[grand_final.loser] = 2
        elif reset and reset.completed and reset.winner and reset.loser:
            places[reset.winner] = 1
            places[reset.loser] = 2
    elif not grand_final:
        final = next(
            (
                match
                for match in matches
                if match.bracket == WINNER
                and match.next_loser is None
                and match.completed
                # the single-elimination final is the only match left in its round
                and per_round.get((WINNER, match.round_number)) == 1
                and match.round_number == max(item.round_number for item in eliminating)
            ),
            None,
        )
        if final and final.winner:
            places[final.winner] = 1
    return places

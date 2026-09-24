"""Structure tests for the seeded single/double elimination bracket generator."""

import random
from collections import Counter

import pytest

from modules.events.brackets import (
    FINAL,
    LOSER,
    WINNER,
    BracketNode,
    MatchOutcome,
    bracket_order,
    elimination_blueprint,
    elimination_placements,
    seed_pairings,
)

FIELD_SIZES = [2, 3, 4, 5, 7, 8, 9, 16]


def _teams(n: int) -> list[str]:
    return [f"seed{i}" for i in range(1, n + 1)]


def _seed(team: str) -> int:
    return int(team.removeprefix("seed"))


def _simulate(nodes: list[BracketNode], pick) -> tuple[dict[str, int], list[MatchOutcome], str]:
    """Play the bracket with ``pick(node, team1, team2) -> winner``.

    Returns the loss count per team, the match outcomes and the champion.
    """
    by_key = {node.key: node for node in nodes}
    slots: dict[str, dict[int, str]] = {node.key: dict(node.teams) for node in nodes}
    losses: Counter[str] = Counter()
    outcomes: list[MatchOutcome] = []
    champion = ""
    for node in nodes:
        teams = slots[node.key]
        if node.is_reset and not teams:
            outcomes.append(
                MatchOutcome(node.key, node.bracket, node.round_number, None, cancelled=True)
            )
            continue
        assert set(teams) == {1, 2}, f"{node.key} is missing a participant: {teams}"
        winner = pick(node, teams[1], teams[2])
        loser = teams[2] if winner == teams[1] else teams[1]
        position = 1 if winner == teams[1] else 2
        losses[loser] += 1
        outcomes.append(
            MatchOutcome(
                node.key,
                node.bracket,
                node.round_number,
                node.next_loser,
                winner=winner,
                loser=loser,
                winner_position=position,
                completed=True,
            )
        )
        if node.key == "GF":
            if position == 1:
                champion = winner
            else:
                slots["GF2"] = {1: teams[1], 2: teams[2]}
            continue
        if node.is_reset:
            champion = winner
            continue
        if node.next_winner:
            assert node.next_winner_slot not in slots[node.next_winner]
            slots[node.next_winner][node.next_winner_slot or 1] = winner
        elif node.bracket == WINNER and "GF" not in by_key:
            champion = winner
        if node.next_loser:
            assert node.next_loser_slot not in slots[node.next_loser]
            slots[node.next_loser][node.next_loser_slot or 1] = loser
    return dict(losses), outcomes, champion


def _first_matches(nodes: list[BracketNode]) -> dict[str, BracketNode]:
    first: dict[str, BracketNode] = {}
    for node in nodes:
        for team in node.teams.values():
            first.setdefault(team, node)
    return first


def test_bracket_order_is_the_standard_recursive_order():
    assert bracket_order(2) == [1, 2]
    assert bracket_order(4) == [1, 4, 2, 3]
    assert bracket_order(8) == [1, 8, 4, 5, 2, 7, 3, 6]
    order = bracket_order(16)
    assert order[:8].count(1) == 1 and 2 in order[8:]
    # Every first-round pair sums to size + 1 (1 v 16, 8 v 9, …).
    assert all(order[i] + order[i + 1] == 17 for i in range(0, 16, 2))
    with pytest.raises(ValueError):
        bracket_order(6)


def test_seed_pairings_give_byes_to_the_top_seeds():
    pairs = seed_pairings(_teams(5))
    assert pairs == [
        ("seed1", None),
        ("seed4", "seed5"),
        ("seed2", None),
        ("seed3", None),
    ]


@pytest.mark.parametrize("n", FIELD_SIZES)
def test_double_elimination_match_count(n):
    nodes = elimination_blueprint(_teams(n), True)
    # 2n - 2 matches are always played, the reset final makes it 2n - 1.
    assert len(nodes) == 2 * n - 1
    assert sum(1 for node in nodes if node.is_reset) == 1
    assert sum(1 for node in nodes if node.bracket == WINNER) == n - 1
    assert sum(1 for node in nodes if node.bracket == LOSER) == max(0, n - 2)


@pytest.mark.parametrize("n", FIELD_SIZES)
def test_every_team_is_out_only_after_two_losses(n):
    nodes = elimination_blueprint(_teams(n), True)
    rng = random.Random(n)
    for _ in range(60):
        losses, outcomes, champion = _simulate(nodes, lambda node, a, b: rng.choice((a, b)))
        assert champion
        assert losses.get(champion, 0) <= 1
        eliminated = [team for team in _teams(n) if team != champion]
        assert all(losses[team] == 2 for team in eliminated), losses
        played = sum(1 for outcome in outcomes if outcome.completed)
        assert played in (2 * n - 2, 2 * n - 1)


@pytest.mark.parametrize("n", FIELD_SIZES)
def test_every_winner_bracket_loser_drops_into_the_loser_bracket(n):
    nodes = elimination_blueprint(_teams(n), True)
    by_key = {node.key: node for node in nodes}
    winner_final = max(
        (node for node in nodes if node.bracket == WINNER), key=lambda node: node.round_number
    )
    for node in nodes:
        if node.bracket == WINNER:
            assert node.next_loser, f"{node.key} loser is eliminated after one loss"
            target = by_key[node.next_loser]
            if n > 2:
                assert target.bracket == LOSER
            if node is winner_final and n > 2:
                # The winner-bracket final loser plays the loser-bracket final.
                assert target.round_number == max(
                    item.round_number for item in nodes if item.bracket == LOSER
                )
        if node.bracket == LOSER:
            assert node.next_loser is None
            assert node.round_kind == ("minor" if node.round_number % 2 else "major")
    grand_final = by_key["GF"]
    assert grand_final.bracket == FINAL and grand_final.next_winner == "GF2"


@pytest.mark.parametrize("n", FIELD_SIZES)
def test_loser_rounds_alternate_minor_and_major(n):
    nodes = elimination_blueprint(_teams(n), True)
    rounds = sorted({node.round_number for node in nodes if node.bracket == LOSER})
    for round_number in rounds:
        drops = [
            node
            for node in nodes
            if node.bracket == WINNER
            and node.next_loser
            and next(item for item in nodes if item.key == node.next_loser).round_number
            == round_number
        ]
        if round_number % 2 == 0:
            assert drops, f"major round {round_number} receives no winner-bracket losers"


@pytest.mark.parametrize("n", FIELD_SIZES)
def test_top_seeds_get_byes(n):
    nodes = elimination_blueprint(_teams(n), True)
    size = 1 << (n - 1).bit_length()
    byes = size - n
    first = _first_matches(nodes)
    for seed in range(1, n + 1):
        starts_later = first[f"seed{seed}"].round_number > 1
        assert starts_later == (seed <= byes), (seed, first[f"seed{seed}"].key)


@pytest.mark.parametrize("n", FIELD_SIZES)
def test_seeds_one_and_two_only_meet_in_the_final(n):
    nodes = elimination_blueprint(_teams(n), True)
    by_key = {node.key: node for node in nodes}
    first = _first_matches(nodes)

    def winner_path(team: str) -> list[str]:
        path, node = [], first[team]
        while node.bracket == WINNER:
            path.append(node.key)
            if not node.next_winner:
                break
            node = by_key[node.next_winner]
        return path

    common = set(winner_path("seed1")) & set(winner_path("seed2"))
    top_round = max(node.round_number for node in nodes if node.bracket == WINNER)
    assert [by_key[key].round_number for key in common] == [top_round]


@pytest.mark.parametrize("n", FIELD_SIZES)
def test_favourites_win_gives_seed_order_placements(n):
    nodes = elimination_blueprint(_teams(n), True)
    _, outcomes, champion = _simulate(nodes, lambda node, a, b: min(a, b, key=_seed))
    assert champion == "seed1"
    places = elimination_placements(outcomes, n)
    assert places["seed1"] == 1
    assert places["seed2"] == 2
    if n >= 3:
        assert places["seed3"] == 3
    assert sorted(places) == sorted(_teams(n))
    # Placements are 1, 2, 3, 4, 5-6, 7-8, … : shared ranks within one round.
    if n == 8:
        assert sorted(places.values()) == [1, 2, 3, 4, 5, 5, 7, 7]
    if n == 16:
        assert sorted(places.values()) == [1, 2, 3, 4, 5, 5, 7, 7, *[9] * 4, *[13] * 4]


def test_reset_final_decides_when_the_loser_bracket_side_wins():
    nodes = elimination_blueprint(_teams(4), True)

    def pick(node, a, b):
        # seed1 loses the grand final once, then wins the reset.
        if node.key == "GF":
            return b
        return min(a, b, key=_seed)

    losses, outcomes, champion = _simulate(nodes, pick)
    assert champion == "seed1"
    assert losses["seed1"] == 1
    assert sum(1 for outcome in outcomes if outcome.completed) == 2 * 4 - 1
    places = elimination_placements(outcomes, 4)
    assert places["seed1"] == 1 and places["seed2"] == 2


@pytest.mark.parametrize("n", [2, 3, 5, 8, 9])
def test_single_elimination(n):
    nodes = elimination_blueprint(_teams(n), False)
    assert len(nodes) == n - 1
    assert all(node.next_loser is None for node in nodes)
    _, outcomes, champion = _simulate(nodes, lambda node, a, b: min(a, b, key=_seed))
    assert champion == "seed1"
    places = elimination_placements(outcomes, n)
    assert places["seed1"] == 1 and places["seed2"] == 2
    if n == 8:
        assert sorted(places.values()) == [1, 2, 3, 3, 5, 5, 5, 5]


def test_invalid_fields_are_rejected():
    with pytest.raises(ValueError):
        elimination_blueprint(["only"], True)
    with pytest.raises(ValueError):
        elimination_blueprint(["a", "a"], True)

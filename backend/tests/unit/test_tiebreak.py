"""Tie-breakers and special round conditions (game reviews 2024–2026)."""

import itertools

from modules.scoring import tiebreak
from modules.scoring.extras_schemas import TiebreakerCriterion
from modules.scoring.sheet_templates import TEMPLATES
from modules.scoring.tiebreak import Contestant, RankedItem

CRITERIA = [
    {"key": "full_cups", "label": "Full cups", "direction": "max", "source": "entry"},
    {
        "key": "full_trays",
        "label": "Full trays",
        "direction": "max",
        "source": "sheet",
        "sheet_keys": ["serving_full_trays"],
    },
    {
        "key": "closest",
        "label": "Closest to Botguy",
        "direction": "min",
        "source": "entry",
        "replay_only": True,
    },
]
DEF_2025 = TEMPLATES["botball_2025"]["definition"]


def test_presets_parse_and_reference_existing_sheet_keys():
    for preset_id, preset in tiebreak.TIEBREAKER_PRESETS.items():
        template_inputs = {
            field["key"]
            for section in TEMPLATES[preset_id]["definition"]["sections"]
            for field in section["fields"]
            + [
                option
                for multiplier in section["multipliers"]
                for option in multiplier.get("either", [multiplier])
            ]
        }
        for criterion in preset["tiebreakers"]:
            TiebreakerCriterion.model_validate(criterion)
            for key in criterion["sheet_keys"]:
                assert key in template_inputs, (preset_id, key)


def test_2025_and_2026_lists_follow_the_game_review():
    labels_2025 = [c["label"] for c in tiebreak.TIEBREAKER_PRESETS["botball_2025"]["tiebreakers"]]
    assert labels_2025[0] == "Largest number of full Cups"
    assert len(labels_2025) == 11
    preset_2026 = tiebreak.TIEBREAKER_PRESETS["botball_2026"]
    assert len(preset_2026["tiebreakers"]) == 12
    assert preset_2026["tiebreakers"][-1]["replay_only"] is True
    assert preset_2026["finals_replay"] is True


def test_criterion_values_come_from_sheet_over_both_sides_or_from_entry():
    raw = {"A.serving_full_trays": 2, "B.serving_full_trays": 1}
    values = tiebreak.match_values(CRITERIA, raw, {"full_cups": 3}, DEF_2025)
    assert values == {"full_cups": 3.0, "full_trays": 3.0, "closest": None}


def test_compare_walks_criteria_in_order_and_respects_direction():
    a = {"full_cups": 1.0, "full_trays": 5.0, "closest": 10.0}
    b = {"full_cups": 1.0, "full_trays": 2.0, "closest": 3.0}
    result, criterion = tiebreak.compare(a, b, CRITERIA)
    assert result == 1 and criterion["key"] == "full_trays"
    tied = {"full_cups": 1.0, "full_trays": 2.0, "closest": 10.0}
    result, criterion = tiebreak.compare(tied, b, CRITERIA)
    assert result == -1 and criterion["key"] == "closest"  # smaller distance wins
    # replay-only criteria are skipped until the match has been replayed
    assert tiebreak.compare(tied, b, CRITERIA, replayed=False) == (0, None)


def test_recorded_value_beats_missing_value():
    result, _ = tiebreak.compare({"full_cups": 0.0}, {}, CRITERIA[:1])
    assert result == 1


def test_rank_with_tiebreakers_orders_ties_and_names_the_decider():
    items = [
        RankedItem("low", 100.0),
        RankedItem("b", 200.0, {"full_cups": 1.0}),
        RankedItem("a", 200.0, {"full_cups": 2.0}),
        RankedItem("top", 300.0),
    ]
    ordered = tiebreak.rank_with_tiebreakers(items, CRITERIA)
    assert [(i.id, i.rank, i.decided_by) for i in ordered] == [
        ("top", 1, None),
        ("a", 2, "Full cups"),
        ("b", 3, "Full cups"),
        ("low", 4, None),
    ]


def test_unresolved_ties_share_a_rank_without_fallback():
    items = [RankedItem("x", 50.0), RankedItem("y", 50.0), RankedItem("z", 10.0)]
    ordered = tiebreak.rank_with_tiebreakers(items, CRITERIA)
    assert [i.rank for i in ordered] == [1, 1, 3]
    items = [RankedItem("x", 50.0, fallback=2), RankedItem("y", 50.0, fallback=1)]
    ordered = tiebreak.rank_with_tiebreakers(items, [], fallback_label="Seeding rank")
    assert [(i.id, i.rank, i.decided_by) for i in ordered] == [
        ("y", 1, "Seeding rank"),
        ("x", 2, "Seeding rank"),
    ]


def test_team_without_fallback_ranks_after_those_with_one_in_any_input_order():
    """A missing seeding rank sorts last; the comparison stays transitive.

    With a missing fallback comparing equal to everything, seed 3 and seed 1
    were never separated when the team without a rank sat between them, and
    the result depended on the input order.
    """
    expected = [("c", 1, "Seeding rank"), ("a", 2, "Seeding rank"), ("b", 3, "Seeding rank")]
    for order in itertools.permutations(["a", "b", "c"]):
        fallbacks = {"a": 3.0, "b": None, "c": 1.0}
        items = [RankedItem(key, 7.0, fallback=fallbacks[key]) for key in order]
        ordered = tiebreak.rank_with_tiebreakers(items, [], fallback_label="Seeding rank")
        assert [(i.id, i.rank, i.decided_by) for i in ordered] == expected, order


def test_unresolved_ties_come_out_in_the_same_order_for_any_input_order():
    for order in itertools.permutations(["x", "y", "z"]):
        ordered = tiebreak.rank_with_tiebreakers([RankedItem(k, 1.0) for k in order], CRITERIA)
        assert [(i.id, i.rank) for i in ordered] == [("x", 1), ("y", 1), ("z", 1)]


def _duel(**overrides):
    a = Contestant("a", 100.0, values={"full_cups": 1.0})
    b = Contestant("b", 100.0, values={"full_cups": 2.0})
    for key, value in overrides.items():
        target, _, attr = key.partition("__")
        setattr(a if target == "a" else b, attr, value)
    return a, b


def test_head_to_head_higher_score_wins():
    a, b = _duel(a__total=120.0)
    outcome = tiebreak.decide_head_to_head(a, b, CRITERIA)
    assert (outcome.winner, outcome.reason) == ("a", "score")


def test_head_to_head_tie_goes_to_the_tiebreakers():
    outcome = tiebreak.decide_head_to_head(*_duel(), CRITERIA)
    assert (outcome.winner, outcome.reason, outcome.decided_by) == ("b", "tiebreaker", "Full cups")


def test_head_to_head_dq_and_lose_the_round_beat_the_score():
    a, b = _duel(a__total=500.0, a__disqualified=True)
    assert tiebreak.decide_head_to_head(a, b, CRITERIA).winner == "b"
    a, b = _duel(a__total=500.0, a__round_lost=True, a__round_lost_reason="motors_running")
    outcome = tiebreak.decide_head_to_head(a, b, CRITERIA)
    assert (outcome.winner, outcome.reason) == ("b", "round_lost")


def test_never_leaving_the_start_box_is_worse_than_motors_running():
    a, b = _duel(
        a__round_lost=True,
        a__round_lost_reason="motors_running",
        b__round_lost=True,
        b__round_lost_reason="never_left_start_box",
    )
    assert tiebreak.decide_head_to_head(a, b, CRITERIA).winner == "a"


def test_finals_are_replayed_instead_of_tie_broken():
    outcome = tiebreak.decide_head_to_head(*_duel(), CRITERIA, is_final=True, finals_replay=True)
    assert outcome.replay and outcome.winner is None and outcome.reason == "finals_replay"
    # without the flag, finals use the tie-breakers like any DE round
    outcome = tiebreak.decide_head_to_head(*_duel(), CRITERIA, is_final=True)
    assert outcome.winner == "b"


def test_fully_equal_match_is_replayed():
    a, b = _duel(b__values={"full_cups": 1.0})
    outcome = tiebreak.decide_head_to_head(a, b, CRITERIA)
    assert outcome.replay and outcome.reason == "replay"


def test_end_contact_bonus_is_25_percent_of_the_offender():
    assert tiebreak.end_contact_bonus(200.0) == 50.0
    assert tiebreak.end_contact_bonus(-40.0) == 0.0
    assert tiebreak.end_contact_bonus(90.0, 10) == 9.0

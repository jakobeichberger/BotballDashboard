"""Tests for the scoring formula language."""

import pytest

from modules.scoring.formula import FormulaError, evaluate, parse_formula, resolve_order
from modules.scoring.formula_engine import run_formula_set


def calc(expression: str, **row) -> float:
    parsed = parse_formula("result", expression)
    return evaluate(parsed, row, {})


class TestArithmetic:
    def test_basic_operators(self):
        assert calc("1 + 2 * 3") == 7.0
        assert calc("(1 + 2) * 3") == 9.0
        assert calc("7 / 2") == 3.5
        assert calc("2 ** 8") == 256.0
        assert calc("-x", x=5) == -5.0

    def test_fractions_read_like_the_game_document(self):
        assert calc("3/4 * 8 + 1/4 * 4") == 7.0

    def test_variables(self):
        assert calc("n - rank + 1", n=16, rank=4) == 13.0

    def test_ternary(self):
        assert calc("10 if flag else 20", flag=1) == 10.0
        assert calc("10 if flag else 20", flag=0) == 20.0

    def test_division_by_zero_is_reported(self):
        with pytest.raises(FormulaError, match="Division by zero"):
            calc("1 / 0")

    def test_safe_div_returns_default(self):
        assert calc("safe_div(5, 0)") == 0.0
        assert calc("safe_div(5, 0, 9)") == 9.0
        assert calc("safe_div(9, 3)") == 3.0


class TestRowFunctions:
    def test_avg_and_sum(self):
        assert calc("avg(runs)", runs=[10, 20, 30]) == 20.0
        assert calc("sum(runs)", runs=[10, 20, 30]) == 60.0
        assert calc("count(runs)", runs=[10, 20, 30]) == 3.0

    def test_avg_best_takes_the_top_k(self):
        assert calc("avg_best(runs, 2)", runs=[149, 289, 518]) == 403.5

    def test_avg_best_divides_by_what_is_available(self):
        """A single run of 10 scores 10, not 5 — this was a real bug."""
        assert calc("avg_best(runs, 2)", runs=[10]) == 10.0

    def test_avg_best_ignores_missing_runs(self):
        assert calc("avg_best(runs, 2)", runs=[10, None, 30]) == 20.0

    def test_min_max_clamp_round(self):
        assert calc("max(a, b)", a=3, b=9) == 9.0
        assert calc("min(a, b)", a=3, b=9) == 3.0
        assert calc("clamp(x, 0, 1)", x=2.5) == 1.0
        assert calc("round(x, 2)", x=1.23456) == 1.23

    def test_iif(self):
        assert calc("iif(x > 5, 1, 0)", x=9) == 1.0


class TestRejectsUnsafeInput:
    @pytest.mark.parametrize(
        "expression",
        [
            "__import__('os').system('ls')",
            "open('/etc/passwd')",
            "(1).__class__",
            "[x for x in range(3)]",
            "lambda: 1",
            "eval('1+1')",
            "exec('x=1')",
            "globals()",
            "x.attribute",
            "x[0]",
            "'a string'",
        ],
    )
    def test_dangerous_expressions_are_rejected(self, expression):
        with pytest.raises(FormulaError):
            parse_formula("result", expression)

    def test_unknown_function_is_rejected(self):
        with pytest.raises(FormulaError, match="Unknown function"):
            parse_formula("result", "frobnicate(1)")

    def test_unknown_variable_is_reported_at_evaluation(self):
        with pytest.raises(FormulaError, match="Unknown variable"):
            calc("nope + 1")

    def test_empty_formula_is_rejected(self):
        with pytest.raises(FormulaError, match="empty"):
            parse_formula("result", "   ")

    def test_syntax_error_is_readable(self):
        with pytest.raises(FormulaError, match="Syntax error"):
            parse_formula("result", "1 +")

    def test_huge_exponent_is_rejected(self):
        with pytest.raises(FormulaError, match="Exponent"):
            calc("2 ** 5000")


class TestDependencyResolution:
    def test_orders_by_dependency_not_by_declaration(self):
        formulas = [
            parse_formula("overall", "a + b"),
            parse_formula("b", "a * 2"),
            parse_formula("a", "x + 1"),
        ]
        order = [p.key for p in resolve_order(formulas, {"x"})]
        assert order == ["a", "b", "overall"]

    def test_cycle_is_reported_with_the_keys_involved(self):
        formulas = [parse_formula("a", "b + 1"), parse_formula("b", "a + 1")]
        with pytest.raises(FormulaError, match="cycle: a, b"):
            resolve_order(formulas, set())

    def test_self_reference_is_rejected(self):
        with pytest.raises(FormulaError, match="refers to itself"):
            parse_formula("a", "a + 1")

    def test_unknown_dependency_names_the_formula(self):
        formulas = [parse_formula("a", "missing + 1")]
        with pytest.raises(FormulaError, match="'a' uses unknown variable 'missing'"):
            resolve_order(formulas, set())


class TestScopeFunctions:
    def test_rank_is_competition_style_with_ties(self):
        rows = [{"team_id": t, "v": v} for t, v in [("a", 10), ("b", 5), ("c", 5), ("d", 1)]]
        res = run_formula_set([("r", "rank(v)")], rows)
        assert [r["r"] for r in res.rows] == [1.0, 2.0, 2.0, 4.0]

    def test_rank_asc_inverts_the_order(self):
        rows = [{"team_id": t, "v": v} for t, v in [("a", 10), ("b", 5)]]
        res = run_formula_set([("r", "rank_asc(v)")], rows)
        assert [r["r"] for r in res.rows] == [2.0, 1.0]

    def test_aggregates_span_every_team(self):
        rows = [{"team_id": "a", "v": 3}, {"team_id": "b", "v": 7}]
        res = run_formula_set(
            [
                ("mx", "max_all(v)"),
                ("mn", "min_all(v)"),
                ("av", "avg_all(v)"),
                ("sm", "sum_all(v)"),
            ],
            rows,
        )
        assert (res.rows[0]["mx"], res.rows[0]["mn"]) == (7.0, 3.0)
        assert (res.rows[0]["av"], res.rows[0]["sm"]) == (5.0, 10.0)

    def test_max_all_flattens_list_inputs(self):
        """MaxTournamentSeedScore is the best single run anywhere in the field."""
        rows = [{"team_id": "a", "runs": [10, 602]}, {"team_id": "b", "runs": [30]}]
        res = run_formula_set([("m", "max_all(runs)")], rows)
        assert res.rows[0]["m"] == 602.0

    def test_n_is_injected(self):
        rows = [{"team_id": "a"}, {"team_id": "b"}, {"team_id": "c"}]
        res = run_formula_set([("teams", "n")], rows)
        assert res.rows[0]["teams"] == 3.0

    def test_scope_function_needs_a_bare_column_name(self):
        with pytest.raises(FormulaError, match="exactly one column name"):
            parse_formula("r", "rank(v + 1)")


class TestRunFormulaSet:
    def test_reports_a_bad_formula_without_crashing(self):
        res = run_formula_set([("a", "1 +")], [{"team_id": "t"}])
        assert not res.ok
        assert "Syntax error" in res.issues[0].message

    def test_reports_the_team_a_runtime_error_happened_on(self):
        rows = [{"team_id": "good", "v": 2}, {"team_id": "bad", "v": 0}]
        res = run_formula_set([("a", "10 / v")], rows)
        assert [i.team_id for i in res.issues] == ["bad"]
        assert res.rows[0]["a"] == 5.0


class TestResourceLimits:
    """Bounds that keep a pathological formula from becoming a 500 or a CPU sink."""

    def test_overlong_expression_is_rejected(self):
        with pytest.raises(FormulaError, match="too long"):
            parse_formula("x", "1+" * 600 + "1")

    def test_deeply_nested_expression_is_rejected(self):
        """A long chain would otherwise blow the evaluator's stack (RecursionError)."""
        with pytest.raises(FormulaError, match="nests too deeply"):
            parse_formula("x", "+".join(["1"] * 400))

    def test_deeply_nested_calls_are_rejected(self):
        with pytest.raises(FormulaError, match="nests too deeply"):
            parse_formula("x", "abs(" * 60 + "1" + ")" * 60)

    def test_formulas_at_realistic_depth_still_parse(self):
        parse_formula(
            "seed_score",
            "3/4 * ((n - rank(seed_total) + 1) / n)"
            " + 1/4 * safe_div(seed_total, max_all(seed_runs))",
        )

    def test_growing_base_overflow_is_reported_not_raised(self):
        """The exponent is capped, but the base can still explode."""
        with pytest.raises(FormulaError, match="too large"):
            calc("((((2**64)**64)**64)**64)**64")

    def test_too_many_formulas_is_reported(self):
        from modules.scoring.formula_engine import MAX_FORMULAS_PER_SET

        formulas = [(f"k{i}", "1") for i in range(MAX_FORMULAS_PER_SET + 1)]
        res = run_formula_set(formulas, [{"team_id": "t"}])
        assert not res.ok
        assert "Too many formulas" in res.issues[0].message


class TestScopeCaching:
    """Scope aggregates are shared across teams; they must stay correct."""

    def test_ranks_and_aggregates_match_a_naive_computation(self):
        values = [10.0, 5.0, 5.0, 1.0, 99.0]
        rows = [{"team_id": f"t{i}", "v": v} for i, v in enumerate(values)]
        res = run_formula_set(
            [
                ("r", "rank(v)"),
                ("ra", "rank_asc(v)"),
                ("mx", "max_all(v)"),
                ("av", "avg_all(v)"),
            ],
            rows,
        )
        assert res.ok, res.issues
        for row, v in zip(res.rows, values, strict=True):
            assert row["r"] == 1 + sum(1 for o in values if o > v)
            assert row["ra"] == 1 + sum(1 for o in values if o < v)
            assert row["mx"] == max(values)
            assert row["av"] == pytest.approx(sum(values) / len(values))

    def test_a_column_computed_later_is_visible_to_later_formulas(self):
        """The cache must not hide a column that a previous formula produced."""
        rows = [{"team_id": "a", "v": 1.0}, {"team_id": "b", "v": 3.0}]
        res = run_formula_set(
            [("doubled", "v * 2"), ("top", "max_all(doubled)"), ("pos", "rank(doubled)")],
            rows,
        )
        assert res.ok, res.issues
        assert [r["top"] for r in res.rows] == [6.0, 6.0]
        assert [r["pos"] for r in res.rows] == [2.0, 1.0]

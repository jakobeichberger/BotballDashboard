"""Error branches of the formula language: every mistake is a FormulaError.

The formula editor shows these messages verbatim, and the ranking reports a
failing team instead of crashing, so none of them may surface as another
exception type.
"""

import pytest

from modules.scoring.formula import (
    MAX_EXPRESSION_LENGTH,
    FormulaError,
    ScopeContext,
    evaluate,
    parse_formula,
)


def calc(expression: str, scope: dict | None = None, **row) -> float:
    return evaluate(parse_formula("result", expression), row, scope or {})


@pytest.mark.parametrize(
    "expression, message",
    [
        ("   ", "empty"),
        ("1 + " * (MAX_EXPRESSION_LENGTH // 4 + 1) + "1", "too long"),
        ("1 +", "Syntax error"),
        ("-" * 60 + "1", "nests too deeply"),
        ("'text'", "literals are not allowed"),
        ("x.y", "not allowed"),
        ("(abs)(1)(2)", "Only direct function calls"),
        ("round(x, n=1)", "keyword arguments"),
        ("count_all(x)", "takes no arguments"),
        ("max_all(1)", "exactly one column name"),
        ("max_all(a, b)", "exactly one column name"),
        ("launch(x)", "Unknown function"),
        ("result + 1", "refers to itself"),
        ("rank(result)", "refers to itself"),
    ],
)
def test_parse_rejects(expression, message):
    with pytest.raises(FormulaError, match=message):
        parse_formula("result", expression)


@pytest.mark.parametrize(
    "expression, row, message",
    [
        ("missing + 1", {}, "Unknown variable 'missing'"),
        ("sqrt(x)", {"x": -4}, "negative"),
        ("x // 0", {"x": 1}, "Division by zero"),
        ("x % 0", {"x": 1}, "Division by zero"),
        ("x / 0", {"x": 1}, "Division by zero"),
        ("2 ** 65", {}, "Exponent is too large"),
        ("((10.0 ** 60) ** 6) ** 2", {}, "too large"),
        ("clamp(1)", {}, r"clamp\(\):"),
        ("avg_best(runs, x)", {"runs": [1.0], "x": "two"}, r"avg_best\(\):"),
        ("[1, 2]", {}, "did not produce a number"),
        ("x * 1", {"x": float("inf")}, "not a finite number"),
    ],
)
def test_evaluate_rejects(expression, row, message):
    with pytest.raises(FormulaError, match=message):
        calc(expression, **row)


def test_comparisons_and_boolean_operators():
    assert calc("1 != 2") == 1.0
    assert calc("2 <= 2 >= 1") == 1.0
    assert calc("3 >= 4") == 0.0
    assert calc("1 < 2 < 1") == 0.0
    assert calc("a and not b", a=1, b=0) == 1.0
    assert calc("a or b", a=0, b=0) == 0.0
    assert calc("+x", x=3) == 3.0


def test_scope_functions_over_the_field():
    scope = ScopeContext({"seed": [10.0, 30.0, 20.0, 30.0], "empty": []})
    assert calc("min_all(seed)", scope) == 10.0
    assert calc("avg_all(seed)", scope) == 22.5
    assert calc("sum_all(seed)", scope) == 90.0
    assert calc("max_all(empty)", scope) == 0.0
    assert calc("count_all()", scope) == 4.0
    # Competition ranking: the tied 30s share rank 1, 20 is third.
    assert calc("rank(seed)", scope, seed=30.0) == 1.0
    assert calc("rank(seed)", scope, seed=20.0) == 3.0
    assert calc("rank_asc(seed)", scope, seed=10.0) == 1.0
    assert calc("count_all()", ScopeContext({})) == 0.0


def test_scope_errors():
    with pytest.raises(FormulaError, match="not available yet"):
        calc("max_all(later)", ScopeContext({}))
    with pytest.raises(FormulaError, match="not available for this team"):
        calc("rank(seed)", ScopeContext({"seed": [1.0]}))

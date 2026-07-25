"""Safe evaluator for user-supplied scoring formulas.

Formulas are written the way the Botball game documents write them, e.g.

    seed_score = 3/4 * ((n - rank(seed_total) + 1) / n)
               + 1/4 * (seed_total / max_all(seed_runs))

Expressions are parsed with `ast` and walked over an explicit node whitelist.
There is deliberately no `eval`/`exec`, no attribute access, no subscripting,
no comprehensions and no name that is not either a declared input, another
formula's key, or a whitelisted function — so a formula cannot reach the
interpreter, the filesystem or the ORM no matter what an admin types.

Two families of functions exist:

* row functions  — operate on the current team's values: avg, avg_best, ...
* scope functions — operate on one column across every team in scope:
  rank, rank_asc, max_all, min_all, avg_all, sum_all, count_all.
  Their first argument must be a bare name (a column), because the engine has
  to resolve the whole column, not a single value.
"""

from __future__ import annotations

import ast
import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

# Nodes a formula may contain. Anything else is rejected at parse time.
_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Call,
    ast.IfExp,
    ast.Compare,
    ast.BoolOp,
    ast.List,
    ast.Tuple,
    # operators
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Not,
    ast.And,
    ast.Or,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
)

SCOPE_FUNCTIONS = frozenset(
    {"rank", "rank_asc", "max_all", "min_all", "avg_all", "sum_all", "count_all"}
)


class FormulaError(ValueError):
    """Raised for anything wrong with a formula: syntax, unknown name, bad maths."""


# ── Row helpers ───────────────────────────────────────────────────────────────


def _flatten(values: Iterable[Any]) -> list[float]:
    out: list[float] = []
    for v in values:
        if v is None:
            continue
        if isinstance(v, list | tuple):
            out.extend(_flatten(v))
        else:
            out.append(float(v))
    return out


def _avg(*args: Any) -> float:
    vals = _flatten(args)
    return sum(vals) / len(vals) if vals else 0.0


def _avg_best(values: Any, k: Any) -> float:
    """Average of the best `k` values.

    Divides by the number of values actually available when a team has fewer
    than `k` of them, so a single run of 10 with k=2 scores 10 and not 5.
    """
    vals = sorted(_flatten([values]), reverse=True)
    k = int(k)
    if k <= 0 or not vals:
        return 0.0
    top = vals[:k]
    return sum(top) / len(top)


def _sum(*args: Any) -> float:
    return sum(_flatten(args))


def _min(*args: Any) -> float:
    vals = _flatten(args)
    return min(vals) if vals else 0.0


def _max(*args: Any) -> float:
    vals = _flatten(args)
    return max(vals) if vals else 0.0


def _count(*args: Any) -> float:
    return float(len(_flatten(args)))


def _clamp(x: Any, lo: Any, hi: Any) -> float:
    return max(float(lo), min(float(hi), float(x)))


def _iif(cond: Any, then: Any, otherwise: Any) -> Any:
    """Conditional as a function. `a if cond else b` also works and reads better."""
    return then if cond else otherwise


def _safe_div(a: Any, b: Any, default: Any = 0.0) -> float:
    b = float(b)
    return float(a) / b if b else float(default)


def _sqrt(x: Any) -> float:
    x = float(x)
    if x < 0:
        raise FormulaError("sqrt() of a negative number")
    return math.sqrt(x)


ROW_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "avg": _avg,
    "mean": _avg,
    "avg_best": _avg_best,
    "sum": _sum,
    "min": _min,
    "max": _max,
    "count": _count,
    "abs": lambda x: abs(float(x)),
    "round": lambda x, n=0: round(float(x), int(n)),
    "floor": lambda x: float(math.floor(float(x))),
    "ceil": lambda x: float(math.ceil(float(x))),
    "sqrt": _sqrt,
    "clamp": _clamp,
    "iif": _iif,
    "safe_div": _safe_div,
}


# ── Parsing / validation ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class ParsedFormula:
    key: str
    expression: str
    tree: ast.Expression
    names: frozenset[str] = field(default_factory=frozenset)
    scope_names: frozenset[str] = field(default_factory=frozenset)

    @property
    def dependencies(self) -> frozenset[str]:
        """Every column this formula needs before it can be evaluated."""
        return self.names | self.scope_names


def parse_formula(key: str, expression: str) -> ParsedFormula:
    """Parse and validate a formula, returning its dependencies.

    Raises FormulaError with a human-readable message for anything invalid.
    """
    if not expression or not expression.strip():
        raise FormulaError("Formula is empty")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"Syntax error: {exc.msg}") from exc

    names: set[str] = set()
    scope_names: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise FormulaError(f"{type(node).__name__} is not allowed in a formula")

        # Catch non-numeric literals here rather than at evaluation, so the
        # editor reports them while the formula is being written.
        if isinstance(node, ast.Constant) and not isinstance(node.value, bool | int | float):
            raise FormulaError(
                f"{type(node.value).__name__} literals are not allowed — formulas return numbers"
            )

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise FormulaError("Only direct function calls are allowed")
            fname = node.func.id
            if node.keywords:
                raise FormulaError(f"{fname}() does not take keyword arguments")
            if fname in SCOPE_FUNCTIONS:
                if fname == "count_all":
                    if node.args:
                        raise FormulaError("count_all() takes no arguments")
                    continue
                if len(node.args) != 1 or not isinstance(node.args[0], ast.Name):
                    raise FormulaError(
                        f"{fname}() takes exactly one column name, e.g. {fname}(seed_total)"
                    )
                scope_names.add(node.args[0].id)
            elif fname not in ROW_FUNCTIONS:
                raise FormulaError(f"Unknown function {fname}()")

    # Collect plain variable references, skipping names that are function calls
    # and the column names consumed by scope functions.
    called: set[str] = {
        n.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    consumed: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in SCOPE_FUNCTIONS
            and node.args
            and isinstance(node.args[0], ast.Name)
        ):
            consumed.add(node.args[0].id)

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in called and node.id not in consumed:
            names.add(node.id)

    if key in names or key in scope_names:
        raise FormulaError(f"Formula '{key}' refers to itself")

    return ParsedFormula(
        key=key,
        expression=expression,
        tree=tree,
        names=frozenset(names),
        scope_names=frozenset(scope_names),
    )


# ── Evaluation ────────────────────────────────────────────────────────────────


def _competition_rank(value: float, population: Sequence[float], *, descending: bool) -> float:
    """1224-style ranking: ties share a rank and the next rank skips.

    Matches how the tournament sheets rank teams (…, 5, 5, 7, …).
    """
    if descending:
        better = sum(1 for v in population if v > value)
    else:
        better = sum(1 for v in population if v < value)
    return float(better + 1)


class _Evaluator(ast.NodeVisitor):
    def __init__(self, row: dict[str, Any], columns: dict[str, list[float]]):
        self.row = row
        self.columns = columns

    # -- scope helpers
    def _column(self, name: str) -> list[float]:
        if name not in self.columns:
            raise FormulaError(f"Column '{name}' is not available yet")
        return self.columns[name]

    def visit_Expression(self, node: ast.Expression) -> Any:
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> Any:
        if isinstance(node.value, bool | int | float):
            return node.value
        raise FormulaError(f"Constant {node.value!r} is not allowed")

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id in self.row:
            return self.row[node.id]
        raise FormulaError(f"Unknown variable '{node.id}'")

    def visit_List(self, node: ast.List) -> Any:
        return [self.visit(e) for e in node.elts]

    visit_Tuple = visit_List

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        val = self.visit(node.operand)
        if isinstance(node.op, ast.USub):
            return -float(val)
        if isinstance(node.op, ast.UAdd):
            return +float(val)
        return not val

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        left, right = float(self.visit(node.left)), float(self.visit(node.right))
        op = node.op
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, ast.Div):
            if right == 0:
                raise FormulaError("Division by zero")
            return left / right
        if isinstance(op, ast.FloorDiv):
            if right == 0:
                raise FormulaError("Division by zero")
            return float(left // right)
        if isinstance(op, ast.Mod):
            if right == 0:
                raise FormulaError("Division by zero")
            return math.fmod(left, right)
        if isinstance(op, ast.Pow):
            if abs(right) > 64:
                raise FormulaError("Exponent is too large")
            return left**right
        raise FormulaError(f"Operator {type(op).__name__} is not allowed")

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        vals = [self.visit(v) for v in node.values]
        return all(vals) if isinstance(node.op, ast.And) else any(vals)

    def visit_Compare(self, node: ast.Compare) -> Any:
        left = self.visit(node.left)
        for op, comp in zip(node.ops, node.comparators, strict=True):
            right = self.visit(comp)
            if isinstance(op, ast.Eq):
                ok = left == right
            elif isinstance(op, ast.NotEq):
                ok = left != right
            elif isinstance(op, ast.Lt):
                ok = left < right
            elif isinstance(op, ast.LtE):
                ok = left <= right
            elif isinstance(op, ast.Gt):
                ok = left > right
            elif isinstance(op, ast.GtE):
                ok = left >= right
            else:
                raise FormulaError("Comparison is not allowed")
            if not ok:
                return False
            left = right
        return True

    def visit_IfExp(self, node: ast.IfExp) -> Any:
        return self.visit(node.body) if self.visit(node.test) else self.visit(node.orelse)

    def visit_Call(self, node: ast.Call) -> Any:
        fname = node.func.id  # validated by parse_formula
        if fname in SCOPE_FUNCTIONS:
            if fname == "count_all":
                any_col = next(iter(self.columns.values()), [])
                return float(len(any_col))
            col_name = node.args[0].id
            column = self._column(col_name)
            if fname == "max_all":
                return max(column) if column else 0.0
            if fname == "min_all":
                return min(column) if column else 0.0
            if fname == "avg_all":
                return sum(column) / len(column) if column else 0.0
            if fname == "sum_all":
                return sum(column)
            # rank / rank_asc need this team's own value for that column
            if col_name not in self.row:
                raise FormulaError(f"Column '{col_name}' is not available for this team")
            own = _flatten([self.row[col_name]])
            own_value = own[0] if own else 0.0
            return _competition_rank(own_value, column, descending=(fname == "rank"))

        func = ROW_FUNCTIONS[fname]
        args = [self.visit(a) for a in node.args]
        try:
            return func(*args)
        except FormulaError:
            raise
        except Exception as exc:  # bad arity, bad cast, ...
            raise FormulaError(f"{fname}(): {exc}") from exc

    def generic_visit(self, node: ast.AST) -> Any:
        raise FormulaError(f"{type(node).__name__} is not allowed in a formula")


def evaluate(parsed: ParsedFormula, row: dict[str, Any], columns: dict[str, list[float]]) -> float:
    """Evaluate one formula for one team.

    `row` holds this team's inputs plus every previously computed formula value.
    `columns` holds each already-computed column across all teams in scope,
    which is what the scope functions (rank, max_all, …) read.
    """
    result = _Evaluator(row, columns).visit(parsed.tree)
    if isinstance(result, bool):
        return float(result)
    if isinstance(result, int | float):
        if math.isnan(result) or math.isinf(result):
            raise FormulaError("Result is not a finite number")
        return float(result)
    raise FormulaError(f"Formula '{parsed.key}' did not produce a number")


# ── Dependency ordering ───────────────────────────────────────────────────────


def resolve_order(parsed: Sequence[ParsedFormula], inputs: Iterable[str]) -> list[ParsedFormula]:
    """Topologically sort formulas so each runs after everything it references.

    Raises FormulaError naming the formulas involved in a cycle, or the missing
    variable, so the admin gets an actionable message instead of a stack trace.
    """
    available = set(inputs)
    by_key = {p.key: p for p in parsed}

    duplicates = [p.key for p in parsed if list(by_key).count(p.key) > 1]
    if duplicates:
        raise FormulaError(f"Duplicate formula key: {duplicates[0]}")

    for p in parsed:
        for dep in p.dependencies:
            if dep not in available and dep not in by_key:
                raise FormulaError(f"Formula '{p.key}' uses unknown variable '{dep}'")

    ordered: list[ParsedFormula] = []
    done: set[str] = set(available)
    remaining = list(parsed)

    while remaining:
        progressed = False
        for p in list(remaining):
            if all(d in done for d in p.dependencies):
                ordered.append(p)
                done.add(p.key)
                remaining.remove(p)
                progressed = True
        if not progressed:
            stuck = ", ".join(sorted(p.key for p in remaining))
            raise FormulaError(f"Formulas reference each other in a cycle: {stuck}")

    return ordered

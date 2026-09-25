"""Competition ranking ("1224"): equal values share a rank, the next rank skips.

The one definition behind every ranking of the app: the seeding table and the
aerial and documentation rankings (``scoring.service``,
``scoring.competition_service``), the formula scoreboards
(``scoring.formula_service``) and the ``rank()`` function of the formula
engine (``scoring.formula``). Higher values rank first everywhere except in
``rank(..., "asc")`` formulas.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Callable, Iterable, Sequence
from typing import TypeVar

T = TypeVar("T")


def rank_descending(items: Iterable[T], value: Callable[[T], float]) -> list[tuple[int, T]]:
    """Sort by ``value`` (highest first) and pair each item with its rank.

    The sort is stable, so tied items keep their input order. Single pass over
    the sorted list: O(n log n) on any field size.
    """
    ordered = sorted(items, key=value, reverse=True)
    ranked: list[tuple[int, T]] = []
    previous: float | None = None
    rank = 0
    for position, item in enumerate(ordered, start=1):
        current = value(item)
        if previous is None or current < previous:
            rank = position  # a new value takes its own position; ties keep the first
            previous = current
        ranked.append((rank, item))
    return ranked


def competition_ranks(values: Iterable[tuple[str, float]]) -> dict[str, int]:
    """Rank ``(key, value)`` pairs: ``{key: rank}``, highest value = 1."""
    return {key: rank for rank, (key, _) in rank_descending(sorted(values), lambda kv: kv[1])}


def rank_in_sorted(value: float, ordered: Sequence[float], *, descending: bool) -> int:
    """Rank of ``value`` within ``ordered`` (a column sorted ascending).

    O(log n) per lookup, for callers that rank every member of one column.
    """
    if descending:
        better = len(ordered) - bisect_right(ordered, value)
    else:
        better = bisect_left(ordered, value)
    return better + 1

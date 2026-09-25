"""Pure statistics helpers for the analytics endpoints.

Kept free of database access so the maths (quantiles, robust outlier scores,
anomaly rules) can be unit-tested with plain lists.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import median
from typing import Any

#: A run whose modified z-score against its reference exceeds this is an
#: outlier. 3.5 is the cut-off recommended by Iglewicz & Hoaglin for the
#: MAD-based score.
ROBUST_Z_THRESHOLD = 3.5
#: Tukey's "far out" fence: beyond Q1 - 3·IQR or Q3 + 3·IQR.
FAR_OUT_IQR = 3.0
#: Minimum number of reference values before a statistical rule may flag
#: anything — with fewer, every score looks unusual.
MIN_TEAM_REFERENCE = 3
MIN_FIELD_REFERENCE = 8
MIN_JUMP_REFERENCE = 6


def quantile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolated quantile of already sorted values (numpy's default)."""
    if not sorted_values:
        raise ValueError("quantile of an empty sequence")
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    position = (len(sorted_values) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return float(sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction)


def box_summary(values: Sequence[float]) -> dict[str, float | int] | None:
    """Five-number summary plus mean and count, as drawn by a boxplot."""
    if not values:
        return None
    ordered = sorted(float(v) for v in values)
    return {
        "n": len(ordered),
        "min": ordered[0],
        "q1": round(quantile(ordered, 0.25), 3),
        "median": round(quantile(ordered, 0.5), 3),
        "q3": round(quantile(ordered, 0.75), 3),
        "max": ordered[-1],
        "mean": round(sum(ordered) / len(ordered), 3),
    }


def robust_z(value: float, reference: Sequence[float]) -> float | None:
    """Modified z-score of `value` against `reference` (median / MAD based).

    Robust against the very outliers it is meant to find, unlike mean and
    standard deviation. When more than half of the reference is identical the
    MAD is 0; the mean absolute deviation (scaled to match σ for normal data)
    takes over then. Returns None when the reference has no spread at all.
    """
    if not reference:
        return None
    center = median(reference)
    deviations = [abs(v - center) for v in reference]
    mad = median(deviations)
    if mad > 0:
        return 0.6745 * (value - center) / mad
    mean_ad = sum(deviations) / len(deviations)
    if mean_ad > 0:
        return (value - center) / (1.2533 * mean_ad)
    return None


def tukey_fences(values: Sequence[float], k: float = FAR_OUT_IQR) -> tuple[float, float] | None:
    if not values:
        return None
    ordered = sorted(values)
    q1, q3 = quantile(ordered, 0.25), quantile(ordered, 0.75)
    iqr = q3 - q1
    return q1 - k * iqr, q3 + k * iqr


@dataclass
class RunSample:
    """One scored run as seen by the anomaly rules."""

    match_id: str
    team_id: str
    total: float
    order: tuple[Any, ...]
    is_disqualified: bool = False
    raw_scores: dict[str, Any] = field(default_factory=dict)
    schema_fields: list[dict[str, Any]] = field(default_factory=list)
    recomputed_total: float | None = None


@dataclass
class Finding:
    kind: str
    message: str
    severity: str = "warning"
    score: float | None = None


def _field_range_findings(run: RunSample) -> list[Finding]:
    """Raw values a scoring sheet cannot produce: over the maximum, under the
    minimum, negative counts or values that are not numbers."""
    findings: list[Finding] = []
    fields = {f.get("key"): f for f in run.schema_fields}
    for key, raw in (run.raw_scores or {}).items():
        spec = fields.get(key, {})
        label = spec.get("label") or key
        if isinstance(raw, bool):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            findings.append(Finding("invalid_value", f"{label}: kein Zahlenwert", "error"))
            continue
        max_value = spec.get("max_value")
        min_value = spec.get("min_value")
        if max_value is not None and value > float(max_value):
            findings.append(
                Finding(
                    "out_of_range",
                    f"{label}: {value:g} über dem Maximum {float(max_value):g}",
                    "error",
                )
            )
        elif min_value is not None and value < float(min_value):
            findings.append(
                Finding(
                    "out_of_range",
                    f"{label}: {value:g} unter dem Minimum {float(min_value):g}",
                    "error",
                )
            )
        elif value < 0 and spec.get("type", "count") == "count":
            findings.append(Finding("out_of_range", f"{label}: negative Anzahl {value:g}", "error"))
    return findings


def detect_anomalies(runs: Sequence[RunSample]) -> dict[str, list[Finding]]:
    """Flag runs a juror should double-check, keyed by match id.

    Rules:
    - ``out_of_range`` / ``invalid_value``: a raw field value the sheet does not allow.
    - ``total_mismatch``: the stored total differs from the one recomputed from
      the raw values (e.g. a total typed in by hand or a schema change).
    - ``team_outlier``: the total is far from the team's *other* runs
      (modified z-score, leave-one-out, at least 3 other runs).
    - ``field_outlier``: the total lies outside Tukey's far-out fences of all
      runs in the field (at least 8 runs).
    - ``jump``: the change from the team's previous run is far larger than the
      run-to-run changes seen across the whole field.

    Disqualified runs are only checked for impossible values; their total of 0
    would otherwise distort every statistical rule.
    """
    findings: dict[str, list[Finding]] = {}

    def add(match_id: str, finding: Finding) -> None:
        findings.setdefault(match_id, []).append(finding)

    for run in runs:
        for finding in _field_range_findings(run):
            add(run.match_id, finding)
        if run.recomputed_total is not None and abs(run.recomputed_total - run.total) > 0.01:
            add(
                run.match_id,
                Finding(
                    "total_mismatch",
                    f"Gespeicherte Summe {run.total:g} ≠ berechnet {run.recomputed_total:g}",
                    "error",
                ),
            )

    valid = [r for r in runs if not r.is_disqualified]
    by_team: dict[str, list[RunSample]] = {}
    for run in valid:
        by_team.setdefault(run.team_id, []).append(run)

    # Team-internal outliers (leave-one-out, so the run cannot hide itself).
    for team_runs in by_team.values():
        if len(team_runs) <= MIN_TEAM_REFERENCE:
            continue
        for run in team_runs:
            others = [r.total for r in team_runs if r.match_id != run.match_id]
            z = robust_z(run.total, others)
            if z is not None and abs(z) > ROBUST_Z_THRESHOLD:
                direction = "über" if z > 0 else "unter"
                add(
                    run.match_id,
                    Finding(
                        "team_outlier",
                        f"Deutlich {direction} den übrigen Läufen des Teams "
                        f"(Median {median(others):g}, z = {z:.1f})",
                        score=round(z, 2),
                    ),
                )

    # Outliers against the whole field.
    totals = [r.total for r in valid]
    if len(totals) >= MIN_FIELD_REFERENCE:
        fences = tukey_fences(totals)
        if fences is not None and fences[1] > fences[0]:
            low, high = fences
            for run in valid:
                if run.total > high or run.total < low:
                    add(
                        run.match_id,
                        Finding(
                            "field_outlier",
                            f"Außerhalb der Verteilung aller Läufe ({low:g} … {high:g})",
                            score=round(robust_z(run.total, totals) or 0.0, 2),
                        ),
                    )

    # Implausible jumps between consecutive runs of the same team.
    steps: list[tuple[RunSample, RunSample, float]] = []
    for team_runs in by_team.values():
        ordered = sorted(team_runs, key=lambda r: r.order)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            steps.append((previous, current, abs(current.total - previous.total)))
    if len(steps) >= MIN_JUMP_REFERENCE and totals:
        fences = tukey_fences([s[2] for s in steps])
        spread = max(totals) - min(totals)
        if fences is not None:
            # A jump must also be large in absolute terms: a quarter of the
            # field's score range. Otherwise a field of near-identical runs
            # would flag every small wobble.
            limit = max(fences[1], 0.25 * spread)
            for previous, current, delta in steps:
                if delta > limit and delta > 0:
                    add(
                        current.match_id,
                        Finding(
                            "jump",
                            f"Sprung von {previous.total:g} auf {current.total:g} "
                            f"gegenüber dem vorigen Lauf",
                            score=round(delta, 2),
                        ),
                    )
    return findings


def field_points(
    raw_scores: dict[str, Any], schema_fields: list[dict[str, Any]]
) -> dict[str, float]:
    """Points each schema field contributed to a run (value × multiplier).

    Values that are not numbers count as 0 here; the anomaly rules report them.
    """
    points: dict[str, float] = {}
    for spec in schema_fields:
        key = spec.get("key")
        if not key:
            continue
        raw = (raw_scores or {}).get(key, 0)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = 0.0
        points[key] = value * float(spec.get("multiplier", 1) or 0)
    return points


def mean(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None

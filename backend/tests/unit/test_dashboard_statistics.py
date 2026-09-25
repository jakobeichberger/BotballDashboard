"""Unit tests for the pure statistics behind the analytics dashboards."""

from datetime import UTC, date, datetime

import pytest

from modules.dashboard.calendar import _fold, render_ics
from modules.dashboard.statistics import (
    RunSample,
    box_summary,
    detect_anomalies,
    field_points,
    quantile,
    robust_z,
)


class TestQuantilesAndBoxes:
    def test_quantile_interpolates_like_numpy(self):
        values = [1.0, 2.0, 3.0, 4.0]
        assert quantile(values, 0.25) == pytest.approx(1.75)
        assert quantile(values, 0.5) == pytest.approx(2.5)
        assert quantile(values, 0.75) == pytest.approx(3.25)

    def test_quantile_of_single_value(self):
        assert quantile([7.0], 0.9) == 7.0

    def test_box_summary(self):
        box = box_summary([10, 20, 30, 40, 50])
        assert box == {
            "n": 5,
            "min": 10.0,
            "q1": 20.0,
            "median": 30.0,
            "q3": 40.0,
            "max": 50.0,
            "mean": 30.0,
        }

    def test_box_summary_empty(self):
        assert box_summary([]) is None


class TestRobustZ:
    def test_flags_far_value(self):
        z = robust_z(300, [100, 110, 90, 105, 95])
        assert z is not None and z > 3.5

    def test_uses_mean_deviation_when_mad_is_zero(self):
        # More than half identical → MAD 0; the fallback must still score.
        z = robust_z(300, [100, 100, 100, 120])
        assert z is not None and z > 3.5

    def test_no_spread_returns_none(self):
        assert robust_z(100, [100, 100, 100]) is None


def _run(match_id, team, total, order, **kwargs):
    return RunSample(match_id=match_id, team_id=team, total=total, order=(order,), **kwargs)


class TestAnomalies:
    def test_team_outlier_is_flagged(self):
        runs = [_run(f"a{i}", "A", score, i) for i, score in enumerate([100, 105, 98, 102])]
        runs.append(_run("a-odd", "A", 400, 10))
        findings = detect_anomalies(runs)
        assert any(f.kind == "team_outlier" for f in findings["a-odd"])
        # The ordinary runs are not flagged as team outliers.
        for i in range(4):
            assert not any(f.kind == "team_outlier" for f in findings.get(f"a{i}", []))

    def test_too_few_runs_flag_nothing_statistical(self):
        runs = [_run("x1", "A", 10, 1), _run("x2", "A", 500, 2)]
        assert detect_anomalies(runs) == {}

    def test_field_outlier(self):
        runs = [_run(f"r{i}", f"T{i}", 100 + i, i) for i in range(10)]
        runs.append(_run("huge", "T99", 1000, 1))
        findings = detect_anomalies(runs)
        assert any(f.kind == "field_outlier" for f in findings["huge"])
        assert "r3" not in findings

    def test_impossible_jump(self):
        runs = []
        for team in "ABCD":
            for i, score in enumerate([100, 104, 101]):
                runs.append(_run(f"{team}{i}", team, score, i))
        runs.append(_run("E0", "E", 100, 0))
        runs.append(_run("E1", "E", 480, 1))
        findings = detect_anomalies(runs)
        assert any(f.kind == "jump" for f in findings["E1"])

    def test_out_of_range_and_mismatch(self):
        fields = [{"key": "cubes", "label": "Würfel", "max_value": 5, "multiplier": 10}]
        run = _run(
            "m1",
            "A",
            80,
            1,
            raw_scores={"cubes": 8},
            schema_fields=fields,
            recomputed_total=70,
        )
        kinds = {f.kind for f in detect_anomalies([run])["m1"]}
        assert kinds == {"out_of_range", "total_mismatch"}

    def test_disqualified_runs_are_not_statistical_outliers(self):
        runs = [_run(f"a{i}", "A", 100 + i, i) for i in range(5)]
        runs.append(_run("dq", "A", 0, 9, is_disqualified=True))
        assert "dq" not in detect_anomalies(runs)


def test_field_points_multiplies_and_ignores_garbage():
    fields = [
        {"key": "a", "multiplier": 3},
        {"key": "b", "multiplier": 2},
        {"key": "flag", "multiplier": 5, "type": "boolean"},
    ]
    assert field_points({"a": 2, "b": "x", "flag": True}, fields) == {
        "a": 6.0,
        "b": 0.0,
        "flag": 5.0,
    }


class TestIcs:
    def test_fold_keeps_lines_short(self):
        folded = _fold("SUMMARY:" + "ä" * 100)
        for line in folded.split("\r\n"):
            assert len(line.encode("utf-8")) <= 75

    def test_render_all_day_and_timed_events(self):
        entries = [
            {
                "id": "season-1-paper",
                "title": "Paper; offiziell, final",
                "kind": "paper",
                "start": date(2026, 3, 1),
                "end": None,
                "season_name": "Saison 2026",
                "description": None,
            },
            {
                "id": "event-1",
                "title": "ECER",
                "kind": "event",
                "start": datetime(2026, 4, 1, 8, 0, tzinfo=UTC),
                "end": datetime(2026, 4, 3, 18, 0, tzinfo=UTC),
                "season_name": "Saison 2026",
                "description": "Wien",
            },
        ]
        ics = render_ics(entries)
        assert ics.startswith("BEGIN:VCALENDAR\r\n")
        assert "DTSTART;VALUE=DATE:20260301" in ics
        assert "DTEND;VALUE=DATE:20260302" in ics
        assert "SUMMARY:Paper\\; offiziell\\, final (Saison 2026)" in ics
        assert "DTSTART:20260401T080000Z" in ics
        assert "DTEND:20260403T180000Z" in ics
        assert ics.count("BEGIN:VEVENT") == 2

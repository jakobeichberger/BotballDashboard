"""scripts/migration_roundtrip.py: the comparison CI relies on (review #9)."""

import json

from scripts import migration_roundtrip as mr


def _write(tmp_path, name, counts, revision="0034", runs=None, outbox="sending"):
    path = tmp_path / name
    path.write_text(
        json.dumps(
            {
                "revision": revision,
                "counts": counts,
                "aerial_runs": runs,
                "outbox_status": outbox,
            }
        )
    )
    return str(path)


def test_round_trip_accepts_only_documented_losses(tmp_path, capsys):
    before = _write(tmp_path, "b.json", {"teams": 6, "season_categories": 1}, runs=mr.AERIAL_RUNS)
    ok = _write(
        tmp_path,
        "a.json",
        {"teams": 6, "season_categories": 0},
        runs=mr.AERIAL_RUNS[:4],
        outbox="pending",
    )
    assert mr.compare(before, ok) == 0
    lost = _write(tmp_path, "l.json", {"teams": 5, "season_categories": 1}, runs=mr.AERIAL_RUNS[:4])
    assert mr.compare(before, lost) == 1
    assert "teams: 6 rows before, 5 after" in capsys.readouterr().out


def test_round_trip_checks_the_transformed_values(tmp_path, capsys):
    before = _write(tmp_path, "b.json", {"teams": 6}, runs=mr.AERIAL_RUNS)
    wrong_runs = _write(tmp_path, "a.json", {"teams": 6}, runs=[11.5, 12.0])
    assert mr.compare(before, wrong_runs) == 1
    assert "aerial runs after the round trip" in capsys.readouterr().out


def test_update_mode_allows_new_tables_but_no_loss(tmp_path, capsys):
    before = _write(tmp_path, "b.json", {"teams": 6, "events": 1}, revision="0033")
    after = _write(tmp_path, "a.json", {"teams": 6, "events": 1, "awards": 0}, revision="0034")
    assert mr.main(["x", "compare", "--update", before, after]) == 0
    lost = _write(tmp_path, "l.json", {"teams": 6}, revision="0034")
    assert mr.main(["x", "compare", "--update", before, lost]) == 1
    assert "events: 1 rows before, None after" in capsys.readouterr().out

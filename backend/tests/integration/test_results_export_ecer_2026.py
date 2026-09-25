"""The ECER 2026 event, entered through the API, exports the official results.

Every team of the published results (tests/unit/fixtures/ecer_2026_results.json)
is registered, its seeding runs, DE rank, documentation, paper, aerial runs
and JBC points are entered, and the XLSX export in the ECER layout must show
the published values: seeding, DE, paper (rank over Botball and Open),
documentation normalised per period, Doc+Paper, overall score and rank.
"""

import io
import json
import re
import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pytest

from modules.events.models import EventRegistration
from modules.paper_review.models import Paper
from modules.teams.models import Team

DATA = json.loads(
    (Path(__file__).parents[1] / "unit" / "fixtures" / "ecer_2026_results.json").read_text()
)
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def read_xlsx(content: bytes) -> dict[str, list[list]]:
    """Sheets of an XLSX written by modules.exports.xlsx: name -> rows."""
    archive = zipfile.ZipFile(io.BytesIO(content))
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    names = [s.get("name") for s in workbook.find("m:sheets", NS)]
    sheets = {}
    for index, name in enumerate(names, start=1):
        root = ElementTree.fromstring(archive.read(f"xl/worksheets/sheet{index}.xml"))
        rows = []
        for row in root.find("m:sheetData", NS):
            values: dict[int, object] = {}
            for cell in row:
                column = re.match(r"[A-Z]+", cell.get("r")).group(0)
                position = 0
                for char in column:
                    position = position * 26 + ord(char) - 64
                if cell.get("t") == "inlineStr":
                    values[position - 1] = cell.find("m:is/m:t", NS).text
                else:
                    values[position - 1] = float(cell.find("m:v", NS).text)
            rows.append([values.get(i) for i in range(max(values, default=-1) + 1)])
        sheets[name] = rows
    return sheets


def _approx(value):
    return pytest.approx(value, rel=1e-8, abs=1e-9)


@pytest.fixture(autouse=True)
async def _modules_on(db, season, event):
    season.use_double_elimination = True
    season.use_documentation_scoring = True
    season.use_aerial = True
    season.use_paper_scoring = True
    event.active_modules = ["seeding", "double_elimination", "documentation", "aerial"]
    await db.commit()


async def _register(db, event, teams, category):
    created = {}
    for entry in teams:
        team = Team(name=entry["name"], team_number=entry["id"], country="AT", school="S")
        db.add(team)
        await db.flush()
        db.add(EventRegistration(event_id=event.id, team_id=team.id, category=category))
        created[entry["id"]] = team
    await db.commit()
    return created


@pytest.mark.asyncio
async def test_ecer_2026_results_export(client, db, auth_headers, season, event):
    for preset, category in (
        ("ecer_2026_botball", "botball"),
        ("ecer_2026_open", "open"),
        ("aerial_2026", "aerial_junior"),
        ("jbc_2026", "jbc"),
    ):
        resp = await client.post(
            f"/api/scoring/formulas/seasons/{season.id}/presets/{preset}?category={category}",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text

    botball = await _register(db, event, DATA["botball"], "botball")
    open_ = await _register(db, event, DATA["open"], "open")
    aerial = await _register(db, event, DATA["aerial"], "aerial_junior")
    jbc = await _register(db, event, DATA["jbc"], "jbc")

    for group, teams in ((DATA["botball"], botball), (DATA["open"], open_)):
        for entry in group:
            team = teams[entry["id"]]
            for points in entry["seeding"]:
                resp = await client.post(
                    f"/api/v1/events/{event.id}/matches",
                    headers=auth_headers,
                    json={
                        "team_id": team.id,
                        "raw_scores": {"points": points},
                        "idempotency_key": str(uuid.uuid4()),
                    },
                )
                assert resp.status_code == 201, resp.text
            if entry["paper"] is not None:
                db.add(
                    Paper(
                        season_id=season.id,
                        team_id=team.id,
                        title=entry["name"],
                        final_score=entry["paper"] / 100,
                    )
                )
        resp = await client.put(
            f"/api/scoring/events/{event.id}/de-results",
            headers=auth_headers,
            json=[
                {"team_id": teams[e["id"]].id, "bracket": "A", "de_rank": e["de_rank"]}
                for e in group
            ],
        )
        assert resp.status_code == 200, resp.text
    await db.commit()
    resp = await client.put(
        f"/api/scoring/events/{event.id}/doc-scores",
        headers=auth_headers,
        json=[
            {
                "team_id": botball[e["id"]].id,
                "part1": e["doc"][0],
                "part2": e["doc"][1],
                "part3": e["doc"][2],
            }
            for e in DATA["botball"]
            if any(v is not None for v in e["doc"])
        ],
    )
    assert resp.status_code == 200, resp.text
    await client.put(
        f"/api/scoring/events/{event.id}/aerial-results",
        headers=auth_headers,
        json=[{"team_id": aerial[e["id"]].id, "runs": e["runs"]} for e in DATA["aerial"]],
    )
    await client.put(
        f"/api/scoring/events/{event.id}/jbc-results",
        headers=auth_headers,
        json=[{"team_id": jbc[e["id"]].id, "points": e["points"]} for e in DATA["jbc"]],
    )

    resp = await client.get(f"/api/exports/events/{event.id}/results.xlsx", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    sheets = read_xlsx(resp.content)
    assert list(sheets) == ["Teams", "Botball & Open", "Aerial", "Junior Botball Challenge"]

    rows = sheets["Botball & Open"]
    header = rows[0]
    assert header[:8] == [
        "Team ID",
        "Team Name",
        "Seeding 1",
        "Seeding 2",
        "Seeding 3",
        "Seeding Total",
        "Seeding Rank",
        "Seeding Score",
    ]
    assert header[-4:] == ["Doc+Paper Score", "Doc+Paper Rank", "Overall Score", "Overall Rank"]
    col = {name: i for i, name in enumerate(header)}
    exported = {r[0]: r for r in rows if r and r[0] not in ("Team ID",)}

    for entry in DATA["botball"]:
        row, expected = exported[entry["id"]], entry["expected"]
        assert row[col["Seeding Total"]] == _approx(expected["seed_total"])
        assert row[col["Seeding Rank"]] == expected["seed_rank"]
        assert row[col["Seeding Score"]] == _approx(expected["seed_score"]), entry["name"]
        assert row[col["DE Score"]] == _approx(expected["de_score"])
        assert row[col["Paper Rank"]] == expected["paper_rank"], entry["name"]
        assert row[col["Doc Score"]] == _approx(expected["doc_score"]), entry["name"]
        assert row[col["Doc+Paper Score"]] == _approx(expected["adapted_doc_score"])
        assert row[col["Doc+Paper Rank"]] == expected["adapted_doc_rank"], entry["name"]
        assert row[col["Overall Score"]] == _approx(expected["overall"]), entry["name"]
        assert row[col["Overall Rank"]] == expected["overall_rank"], entry["name"]
    for entry in DATA["open"]:
        row, expected = exported[entry["id"]], entry["expected"]
        assert row[col["Seeding Rank"]] == expected["seed_rank"]
        assert row[col["Seeding Score"]] == _approx(expected["seed_score"])
        assert row[col["DE Score"]] == _approx(expected["de_score"])
        assert row[col["Paper Rank"]] == expected["paper_rank"], entry["name"]
        assert row[col["Doc Score"]] is None

    aerial_rows = {r[0]: r for r in sheets["Aerial"][1:]}
    for entry in DATA["aerial"]:
        assert aerial_rows[entry["id"]][-2] == _approx(entry["score"])
        assert aerial_rows[entry["id"]][-1] == entry["rank"]
    jbc_rows = {r[0]: r for r in sheets["Junior Botball Challenge"][1:]}
    assert {k: (v[2], v[3]) for k, v in jbc_rows.items()} == {
        e["id"]: (e["points"], e["rank"]) for e in DATA["jbc"]
    }

    csv = await client.get(
        f"/api/exports/events/{event.id}/results.csv?sheet=Junior Botball Challenge",
        headers=auth_headers,
    )
    assert csv.status_code == 200
    assert csv.text.splitlines()[0] == "Team ID,Team Name,Points for Solved Challenges,Rank"
    missing = await client.get(
        f"/api/exports/events/{event.id}/results.csv?sheet=Alliance", headers=auth_headers
    )
    assert missing.status_code == 404

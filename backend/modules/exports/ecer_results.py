"""Event results in the layout of the official ECER results spreadsheet.

The ECER 2026 results (docs/assets, test fixture ecer_2026_results.json) are
one workbook with the sheets "Teams", "Botball & Open", "Aerial", "Alliance"
and "Junior Botball Challenge"; within a sheet every category is its own
block with a header row. The columns of "Botball & Open":

    Team ID, Team Name, Seeding 1–3, Seeding Total, Seeding Rank, Seeding
    Score, DE Rank, DE Score, Paper, Paper Score, Paper Rank, Doc P1–P3,
    Onsite, Doc Score, Doc+Paper Score, Doc+Paper Rank, Overall Score,
    Overall Rank

Every value comes from the category's formula set (formula_service), so the
export shows exactly what the scoreboard ranks on. The paper rank is one list
over Botball and Open (teams without a paper share the last rank); the
Doc+Paper rank is within the category. Categories are laid out by kind:
botball and open in "Botball & Open", aerial in "Aerial", jbc in "Junior
Botball Challenge"; custom categories get a sheet of their own with their
formula values.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.exports.xlsx import Sheet
from modules.scoring.ranking import competition_ranks
from modules.seasons.categories import kind_of
from modules.teams.models import Team

BOTBALL_HEADER = [
    "Team ID",
    "Team Name",
    "Seeding 1",
    "Seeding 2",
    "Seeding 3",
    "Seeding Total",
    "Seeding Rank",
    "Seeding Score",
    "DE Rank",
    "DE Score",
    "Paper",
    "Paper Score",
    "Paper Rank",
    "Doc P1",
    "Doc P2",
    "Doc P3",
    "Onsite",
    "Doc Score",
    "Doc+Paper Score",
    "Doc+Paper Rank",
    "Overall Score",
    "Overall Rank",
]

SHEET_TEAMS = "Teams"
SHEET_BOTBALL = "Botball & Open"
SHEET_AERIAL = "Aerial"
SHEET_ALLIANCE = "Alliance"
SHEET_JBC = "Junior Botball Challenge"


def _num(value: Any) -> float | int | None:
    if value is None or isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return int(number) if number.is_integer() else round(number, 10)


def _team_id(team: Team | None, team_id: str) -> str:
    return (team.team_number if team and team.team_number else None) or team_id


def _block(sheet: Sheet, header: list[Any], rows: list[list[Any]]) -> None:
    sheet.header_rows.add(len(sheet.rows))
    sheet.rows.append(header)
    sheet.rows.extend(rows)


async def build_results(db: AsyncSession, event_id: str) -> list[Sheet]:
    from modules.events import service as event_service
    from modules.events.models import EventPhase
    from modules.scoring import formula_service

    data = await formula_service.load_event_inputs(db, event_id)
    categories = list(data.categories) + sorted(
        {c for c in data.participants.values() if c not in data.categories}
    )
    categories = [c for c in categories if c in set(data.participants.values())]
    ranked: dict[str, list[dict[str, Any]]] = {}
    for category in categories:
        computed, _ = await formula_service.compute_category_ranking(
            db, event_id, category, data=data
        )
        # By overall rank like the official sheet (disqualified teams last).
        ranked[category] = sorted(
            computed,
            key=lambda r: (r.get("rank") is None, r.get("rank") or 0, r.get("team_name") or ""),
        )
    team_ids = {r["team_id"] for group in ranked.values() for r in group}
    teams = (
        {t.id: t for t in (await db.execute(select(Team).where(Team.id.in_(team_ids)))).scalars()}
        if team_ids
        else {}
    )

    def ident(row: dict[str, Any]) -> list[Any]:
        team = teams.get(row["team_id"])
        return [_team_id(team, row["team_id"]), row.get("team_name")]

    sheets: list[Sheet] = []

    # ── Teams ────────────────────────────────────────────────────────────────
    team_sheet = Sheet(SHEET_TEAMS, [])
    for category in categories:
        rows: list[list[Any]] = [
            [*ident(r), teams[r["team_id"]].country if r["team_id"] in teams else None]
            + [teams[r["team_id"]].school if r["team_id"] in teams else None]
            for r in sorted(ranked[category], key=lambda r: ident(r)[0])
        ]
        _block(team_sheet, ["Team ID", "Team Name", "Country", "Organization"], rows)
    sheets.append(team_sheet)

    # ── Botball & Open ───────────────────────────────────────────────────────
    game = [c for c in categories if kind_of(data.categories, c) in ("botball", "open")]
    game_rows = [r for c in game for r in ranked[c] if r.get("rank") is not None]
    paper_ranks = competition_ranks((r["team_id"], float(r.get("paper") or 0.0)) for r in game_rows)
    seed_columns = max([3, *(len(r.get("seed_runs") or []) for c in game for r in ranked[c])])
    header = BOTBALL_HEADER[:2] + [f"Seeding {i}" for i in range(1, seed_columns + 1)]
    header += BOTBALL_HEADER[5:]
    botball_sheet = Sheet(SHEET_BOTBALL, [])
    for category in game:
        with_docs = kind_of(data.categories, category) == "botball"
        adapted = competition_ranks(
            (r["team_id"], float(r.get("adapted_doc_score") or 0.0))
            for r in ranked[category]
            if r.get("rank") is not None
        )
        rows = []
        for r in ranked[category]:
            runs = list(r.get("seed_runs") or [])
            doc = data.doc_by_team.get(r["team_id"])
            paper = data.paper_by_team.get(r["team_id"])
            rows.append(
                [
                    *ident(r),
                    *[_num(v) for v in runs[:seed_columns]],
                    *([None] * (seed_columns - len(runs[:seed_columns]))),
                    _num(r.get("seed_total")),
                    _num(r.get("seed_rank")) or None,
                    _num(r.get("seed_score")),
                    _num(r.get("de_rank")) or None,
                    _num(r.get("de_score")),
                    _num(paper),
                    _num(r.get("paper_score")),
                    paper_ranks.get(r["team_id"]),
                    _num(doc.part1) if with_docs and doc else None,
                    _num(doc.part2) if with_docs and doc else None,
                    _num(doc.part3) if with_docs and doc else None,
                    _num(doc.onsite) if with_docs and doc else None,
                    _num(r.get("doc_score")) if with_docs else None,
                    _num(r.get("adapted_doc_score")) if with_docs else None,
                    adapted.get(r["team_id"]) if with_docs else None,
                    _num(r.get("overall")),
                    r.get("rank"),
                ]
            )
        _block(botball_sheet, header, rows)
    if game:
        sheets.append(botball_sheet)

    # ── Aerial ───────────────────────────────────────────────────────────────
    aerial = [c for c in categories if kind_of(data.categories, c) == "aerial"]
    if aerial:
        aerial_sheet = Sheet(SHEET_AERIAL, [])
        for category in aerial:
            runs_of = {
                r["team_id"]: list(data.aerial_by_team[r["team_id"]].runs or [])
                if r["team_id"] in data.aerial_by_team
                else []
                for r in ranked[category]
            }
            count = max([1, *(len(v) for v in runs_of.values())])
            rows = [
                [
                    *ident(r),
                    *[_num(v) for v in runs_of[r["team_id"]]],
                    *([None] * (count - len(runs_of[r["team_id"]]))),
                    _num(r.get("aerial_score", r.get("overall"))),
                    r.get("rank"),
                ]
                for r in ranked[category]
            ]
            header = ["Team ID", "Team Name", *[f"Run {i}" for i in range(1, count + 1)]]
            _block(aerial_sheet, [*header, "Score", "Rank"], rows)
        sheets.append(aerial_sheet)

    # ── Alliance ─────────────────────────────────────────────────────────────
    phases = (
        await db.execute(
            select(EventPhase)
            .where(EventPhase.event_id == event_id, EventPhase.phase_type == "alliance")
            .order_by(EventPhase.sort_order)
        )
    ).scalars()
    alliance_rows: list[list[Any]] = []
    for phase in phases:
        for entry in await event_service.alliance_standings(db, event_id, phase.id):
            alliance_rows.append(
                [
                    f"AL-{len(alliance_rows) + 1:04d}",
                    " & ".join(name for name in entry["team_names"] if name),
                    _num(entry["best_score"]),
                    entry["rank"],
                ]
            )
    if alliance_rows:
        alliance_sheet = Sheet(SHEET_ALLIANCE, [])
        _block(alliance_sheet, ["Team ID", "Team Name", "Best Score", "Rank"], alliance_rows)
        sheets.append(alliance_sheet)

    # ── Junior Botball Challenge ─────────────────────────────────────────────
    jbc = [c for c in categories if kind_of(data.categories, c) == "jbc"]
    if jbc:
        jbc_sheet = Sheet(SHEET_JBC, [])
        for category in jbc:
            rows = []
            for r in ranked[category]:
                result = data.jbc_by_team.get(r["team_id"])
                rows.append(
                    [
                        *ident(r),
                        _num(result.points) if result else None,
                        result.rank if result else None,
                    ]
                )
            rows.sort(key=lambda row: (row[3] is None, row[3] or 0, row[1] or ""))
            _block(
                jbc_sheet, ["Team ID", "Team Name", "Points for Solved Challenges", "Rank"], rows
            )
        sheets.append(jbc_sheet)

    # ── Custom categories: their formula values ──────────────────────────────
    for category in categories:
        if kind_of(data.categories, category) != "custom" or not ranked[category]:
            continue
        keys = [k for k, _ in data.formula_set(category)]
        rows = [
            [*ident(r), *[_num(r.get(k)) for k in keys], r.get("rank")] for r in ranked[category]
        ]
        custom = Sheet(category, [])
        _block(custom, ["Team ID", "Team Name", *keys, "Rank"], rows)
        sheets.append(custom)
    return sheets

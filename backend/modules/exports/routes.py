"""Export routes – PDF and CSV downloads."""

import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import assert_team_access, require_any_permission, require_permission
from core.database import get_db
from modules.dashboard.analytics import all_teams_history, team_history
from modules.events.models import EventRegistration
from modules.events.service import get_event
from modules.exports.pdf_builder import (
    build_overall_ranking_pdf,
    build_paper_review_pdf,
    build_print_report_pdf,
    build_ranking_pdf,
    build_team_list_pdf,
    build_team_report_pdf,
)
from modules.paper_review.service import list_papers
from modules.printing.service import list_print_jobs, list_printers
from modules.scoring.formula_service import compute_overall_ranking
from modules.scoring.service import get_ranking, list_matches
from modules.seasons.service import get_season
from modules.teams.models import Team
from modules.teams.service import get_team, list_teams

#: Team reports include practice runs, which are internal to a team: the team
#: itself and organizers only.
TEAM_REPORT_ELEVATED = ("scoring:admin", "teams:admin")

router = APIRouter(prefix="/exports", tags=["exports"])


# ── Helper: build ID → name maps ──────────────────────────────────────────────


async def _teams_map(db: AsyncSession, season_id: str | None = None) -> dict[str, str]:
    teams = await list_teams(db, season_id=season_id)
    return {t.id: t.name for t in teams}


async def _printers_map(db: AsyncSession) -> dict[str, str]:
    printers = await list_printers(db)
    return {p.id: p.name for p in printers}


async def _event_teams_map(db: AsyncSession, event_id: str) -> dict[str, str]:
    result = await db.execute(
        select(Team)
        .join(EventRegistration, EventRegistration.team_id == Team.id)
        .where(EventRegistration.event_id == event_id)
    )
    return {team.id: team.name for team in result.scalars().all()}


@router.get("/events/{event_id}/ranking.csv")
async def export_event_ranking_csv(
    event_id: str,
    _=Depends(require_any_permission("scoring:read", "dashboard:read")),
    db: AsyncSession = Depends(get_db),
):
    event = await get_event(db, event_id)
    ranking = await get_ranking(db, event_id=event.id)
    teams = await _event_teams_map(db, event.id)
    buf = io.StringIO()
    writer = _SafeWriter(buf)
    writer.writerow(["Rank", "Team", "Seed Score", "Best Score", "Average", "Rounds"])
    for item in ranking:
        writer.writerow(
            [
                item.rank,
                teams.get(item.team_id, item.team_id),
                item.seed_score,
                item.best_score,
                item.average_score,
                item.rounds_played,
            ]
        )
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="ranking-{event.slug}.csv"'},
    )


@router.get("/events/{event_id}/ranking.pdf")
async def export_event_ranking_pdf(
    event_id: str,
    _=Depends(require_any_permission("scoring:read", "dashboard:read")),
    db: AsyncSession = Depends(get_db),
):
    event = await get_event(db, event_id)
    ranking = await get_ranking(db, event_id=event.id)
    teams = await _event_teams_map(db, event.id)
    content = build_ranking_pdf(
        event.name,
        "",
        [
            {
                "rank": item.rank,
                "team_id": item.team_id,
                "seed_score": item.seed_score,
                "best_score": item.best_score,
                "average_score": item.average_score,
                "rounds_played": item.rounds_played,
            }
            for item in ranking
        ],
        teams,
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="ranking-{event.slug}.pdf"'},
    )


async def _overall_entries(db: AsyncSession, event) -> list[dict]:
    """Formula-engine overall ranking of every active category of the event."""
    season = await get_season(db, event.season_id)
    categories = list(season.active_categories or ["botball"])
    return await compute_overall_ranking(db, event.id, categories)


@router.get("/events/{event_id}/overall-ranking.csv")
async def export_event_overall_ranking_csv(
    event_id: str,
    _=Depends(require_any_permission("scoring:read", "dashboard:read")),
    db: AsyncSession = Depends(get_db),
):
    """Overall ranking with every value the season's formula set computed."""
    event = await get_event(db, event_id)
    entries = await _overall_entries(db, event)
    value_keys: list[str] = []
    for entry in entries:
        for key in entry.get("values", {}):
            if key not in value_keys:
                value_keys.append(key)
    buf = io.StringIO()
    writer = _SafeWriter(buf)
    writer.writerow(["Rank", "Team", "Category", *value_keys])
    for entry in entries:
        values = entry.get("values", {})
        writer.writerow(
            [
                entry["rank"],
                entry.get("team_name") or entry["team_id"],
                entry.get("category", ""),
                *(f"{values[k]:.4f}" if k in values else "" for k in value_keys),
            ]
        )
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="overall-ranking-{event.slug}.csv"'},
    )


@router.get("/events/{event_id}/overall-ranking.pdf")
async def export_event_overall_ranking_pdf(
    event_id: str,
    _=Depends(require_any_permission("scoring:read", "dashboard:read")),
    db: AsyncSession = Depends(get_db),
):
    event = await get_event(db, event_id)
    season = await get_season(db, event.season_id)
    content = build_overall_ranking_pdf(event.name, season.name, await _overall_entries(db, event))
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="overall-ranking-{event.slug}.pdf"'},
    )


@router.get("/events/{event_id}/matches.csv")
async def export_event_matches_csv(
    event_id: str,
    _=Depends(require_any_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    event = await get_event(db, event_id)
    matches = await list_matches(db, event_id=event.id)
    teams = await _event_teams_map(db, event.id)
    buf = io.StringIO()
    writer = _SafeWriter(buf)
    writer.writerow(["Match ID", "Team", "Round", "Table", "Total", "Disqualified", "Created"])
    for item in matches:
        writer.writerow(
            [
                item.id,
                teams.get(item.team_id, item.team_id),
                item.round_number,
                item.table_number or "",
                item.total_score,
                item.is_disqualified,
                item.created_at.isoformat(),
            ]
        )
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="matches-{event.slug}.csv"'},
    )


# ── Ranking PDF ───────────────────────────────────────────────────────────────


def _csv_safe(value):
    """Neutralise spreadsheet formula injection.

    Team names, paper titles and match notes are user-supplied (a mentor can set
    them on their own records). Excel/LibreOffice execute a cell starting with
    =, +, - or @, so prefix those with an apostrophe.
    """
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


class _SafeWriter:
    """csv.writer wrapper that escapes every field via _csv_safe."""

    def __init__(self, buf):
        self._w = csv.writer(buf)

    def writerow(self, row):
        self._w.writerow([_csv_safe(v) for v in row])

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


@router.get("/seasons/{season_id}/ranking.pdf")
async def export_ranking_pdf(
    season_id: str,
    competition_level_id: str | None = Query(None),
    competition_level_name: str | None = Query(None, alias="level_name"),
    _=Depends(require_any_permission("scoring:read", "dashboard:read")),
    db: AsyncSession = Depends(get_db),
):
    season = await get_season(db, season_id)
    ranking = await get_ranking(db, season_id, competition_level_id)
    teams = await _teams_map(db, season_id)

    pdf_bytes = build_ranking_pdf(
        season_name=season.name,
        competition_level=competition_level_name or "",
        ranking_rows=[
            {
                "rank": r.rank,
                "team_id": r.team_id,
                "seed_score": r.seed_score,
                "best_score": r.best_score,
                "average_score": r.average_score,
                "rounds_played": r.rounds_played,
            }
            for r in ranking
        ],
        teams_by_id=teams,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="rangliste-{season.year}.pdf"'},
    )


# ── Ranking CSV ───────────────────────────────────────────────────────────────


@router.get("/seasons/{season_id}/ranking.csv")
async def export_ranking_csv(
    season_id: str,
    competition_level_id: str | None = Query(None),
    _=Depends(require_any_permission("scoring:read", "dashboard:read")),
    db: AsyncSession = Depends(get_db),
):
    season = await get_season(db, season_id)
    ranking = await get_ranking(db, season_id, competition_level_id)
    teams = await _teams_map(db, season_id)

    buf = io.StringIO()
    writer = _SafeWriter(buf)
    writer.writerow(["Rang", "Team", "Seed-Score", "Best-Score", "Durchschnitt", "Runden"])
    for r in ranking:
        writer.writerow(
            [
                r.rank,
                teams.get(r.team_id, r.team_id),
                f"{r.seed_score:.2f}",
                f"{r.best_score:.2f}",
                f"{r.average_score:.2f}",
                r.rounds_played,
            ]
        )

    return Response(
        content=buf.getvalue().encode("utf-8-sig"),  # BOM for Excel
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="rangliste-{season.year}.csv"'},
    )


# ── Matches CSV ───────────────────────────────────────────────────────────────


@router.get("/seasons/{season_id}/matches.csv")
async def export_matches_csv(
    season_id: str,
    _=Depends(require_any_permission("scoring:read")),
    db: AsyncSession = Depends(get_db),
):
    season = await get_season(db, season_id)
    matches = await list_matches(db, season_id)
    teams = await _teams_map(db, season_id)

    buf = io.StringIO()
    writer = _SafeWriter(buf)
    writer.writerow(
        [
            "Match-ID",
            "Team",
            "Runde",
            "Tisch",
            "Total-Score",
            "DQ",
            "Yellow Card",
            "Red Card",
            "Notizen",
            "Eingetragen am",
        ]
    )
    for m in matches:
        writer.writerow(
            [
                m.id,
                teams.get(m.team_id, m.team_id),
                m.round_number,
                m.table_number or "",
                f"{m.total_score:.2f}",
                "Ja" if m.is_disqualified else "Nein",
                "Ja" if m.yellow_card else "Nein",
                "Ja" if m.red_card else "Nein",
                m.notes or "",
                m.created_at.strftime("%d.%m.%Y %H:%M"),
            ]
        )

    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="wertungen-{season.year}.csv"'},
    )


# ── Paper Review PDF ──────────────────────────────────────────────────────────


@router.get("/seasons/{season_id}/papers.pdf")
async def export_papers_pdf(
    season_id: str,
    _=Depends(require_any_permission("papers:admin")),
    db: AsyncSession = Depends(get_db),
):
    season = await get_season(db, season_id)
    papers = await list_papers(db, season_id=season_id)
    teams = await _teams_map(db, season_id)

    papers_data = []
    for p in papers:
        papers_data.append(
            {
                "team_id": p.team_id,
                "title": p.title,
                "status": p.status,
                "revision_number": p.revision_number,
                "reviews": [
                    {"is_submitted": r.is_submitted, "total_score": r.total_score}
                    for r in p.reviews
                ],
                "assignments": [{"id": a.id} for a in p.assignments],
            }
        )

    pdf_bytes = build_paper_review_pdf(
        season_name=season.name,
        papers=papers_data,
        teams_by_id=teams,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="paper-review-{season.year}.pdf"'},
    )


# ── Paper Review CSV ──────────────────────────────────────────────────────────


@router.get("/seasons/{season_id}/papers.csv")
async def export_papers_csv(
    season_id: str,
    _=Depends(require_any_permission("papers:admin")),
    db: AsyncSession = Depends(get_db),
):
    season = await get_season(db, season_id)
    papers = await list_papers(db, season_id=season_id)
    teams = await _teams_map(db, season_id)

    buf = io.StringIO()
    writer = _SafeWriter(buf)
    writer.writerow(
        [
            "Team",
            "Titel",
            "Status",
            "Revision",
            "Reviewer",
            "Ø Score",
            "Eingereicht am",
        ]
    )
    for p in papers:
        submitted_reviews = [r for r in p.reviews if r.is_submitted]
        avg = (
            (
                sum(r.total_score for r in submitted_reviews if r.total_score)
                / len(submitted_reviews)
            )
            if submitted_reviews
            else None
        )
        writer.writerow(
            [
                teams.get(p.team_id, p.team_id),
                p.title,
                p.status,
                p.revision_number,
                len(p.assignments),
                f"{avg:.2f}" if avg else "—",
                p.submitted_at.strftime("%d.%m.%Y") if p.submitted_at else "—",
            ]
        )

    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="papers-{season.year}.csv"'},
    )


# ── Print Report PDF ──────────────────────────────────────────────────────────


@router.get("/seasons/{season_id}/printing.pdf")
async def export_printing_pdf(
    season_id: str,
    _=Depends(require_any_permission("printing:admin")),
    db: AsyncSession = Depends(get_db),
):
    season = await get_season(db, season_id)
    jobs = await list_print_jobs(db, season_id=season_id)
    teams = await _teams_map(db, season_id)
    printers = await _printers_map(db)

    jobs_data = [
        {
            "team_id": j.team_id,
            "file_name": j.file_name,
            "material": j.material,
            "status": j.status,
            "printer_id": j.printer_id,
            "actual_grams": j.actual_grams,
            "estimated_grams": j.estimated_grams,
        }
        for j in jobs
    ]

    pdf_bytes = build_print_report_pdf(
        season_name=season.name,
        jobs=jobs_data,
        teams_by_id=teams,
        printers_by_id=printers,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="3d-druck-{season.year}.pdf"'},
    )


# ── Team List PDF ─────────────────────────────────────────────────────────────


@router.get("/seasons/{season_id}/teams.pdf")
async def export_teams_pdf(
    season_id: str,
    _=Depends(require_any_permission("teams:read")),
    db: AsyncSession = Depends(get_db),
):
    season = await get_season(db, season_id)
    teams = await list_teams(db, season_id=season_id)

    teams_data = [
        {
            "name": t.name,
            "team_number": t.team_number,
            "school": t.school,
            "city": t.city,
            "country": t.country,
            "is_active": t.is_active,
        }
        for t in teams
    ]

    pdf_bytes = build_team_list_pdf(season_name=season.name, teams=teams_data)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="teams-{season.year}.pdf"'},
    )


# ── Team List CSV ─────────────────────────────────────────────────────────────


@router.get("/seasons/{season_id}/teams.csv")
async def export_teams_csv(
    season_id: str,
    _=Depends(require_any_permission("teams:read")),
    db: AsyncSession = Depends(get_db),
):
    season = await get_season(db, season_id)
    teams = await list_teams(db, season_id=season_id)

    buf = io.StringIO()
    writer = _SafeWriter(buf)
    writer.writerow(["Name", "Nummer", "Schule", "Stadt", "Land", "Status"])
    for t in teams:
        writer.writerow(
            [
                t.name,
                t.team_number or "",
                t.school or "",
                t.city or "",
                t.country,
                "Aktiv" if t.is_active else "Inaktiv",
            ]
        )

    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="teams-{season.year}.csv"'},
    )


# ── Team report & multi-year history ──────────────────────────────────────────

_HISTORY_HEADER = [
    "Saison-Jahr",
    "Saison",
    "Event",
    "Event-Typ",
    "Beginn",
    "Team",
    "Team-Nr.",
    "Kategorie",
    "Seeding-Rang",
    "Seeding-Teams",
    "Seed-Score",
    "Bester Lauf",
    "Ø Lauf",
    "Läufe",
    "Gesamtrang",
    "Gesamt-Teams",
    "Gesamt-Score",
    "DE-Score",
    "Doku-Score",
    "Paper-Score",
]


def _num(value, digits: int = 3) -> str:
    return f"{value:.{digits}f}" if isinstance(value, int | float) else ""


def _history_csv(rows: list[dict], with_practice: bool) -> bytes:
    buf = io.StringIO()
    writer = _SafeWriter(buf)
    writer.writerow(_HISTORY_HEADER + (["Übungsläufe", "Ø Übung"] if with_practice else []))
    for r in rows:
        line = [
            r["season_year"],
            r["season_name"],
            r["event_name"],
            r["event_type"],
            r["starts_at"].date().isoformat() if r.get("starts_at") else "",
            r["team_name"],
            r.get("team_number") or "",
            r["category"],
            r.get("seeding_rank") or "",
            r.get("seeding_teams") or "",
            _num(r.get("seeding_score"), 2),
            _num(r.get("best_score"), 2),
            _num(r.get("official_avg"), 2),
            r.get("official_runs", 0),
            r.get("overall_rank") or "",
            r.get("overall_teams") or "",
            _num(r.get("overall_score")),
            _num(r.get("de_score")),
            _num(r.get("doc_score")),
            _num(r.get("paper_score")),
        ]
        if with_practice:
            line += [r.get("practice_runs", 0), _num(r.get("practice_avg"), 2)]
        writer.writerow(line)
    return buf.getvalue().encode("utf-8-sig")


@router.get("/teams/{team_id}/report.pdf")
async def export_team_report_pdf(
    team_id: str,
    current_user=Depends(require_permission("teams:read")),
    db: AsyncSession = Depends(get_db),
):
    """Results of one team across every event and season."""
    await assert_team_access(db, current_user, team_id, TEAM_REPORT_ELEVATED)
    team = await get_team(db, team_id)
    history = await team_history(db, team_id, include_practice=True)
    content = build_team_report_pdf(
        {
            "name": team.name,
            "team_number": team.team_number,
            "school": team.school,
            "city": team.city,
            "country": team.country,
        },
        history,
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="teambericht-{team.id[:8]}.pdf"'},
    )


@router.get("/teams/{team_id}/history.csv")
async def export_team_history_csv(
    team_id: str,
    current_user=Depends(require_permission("teams:read")),
    db: AsyncSession = Depends(get_db),
):
    """Multi-year results of one team as CSV."""
    await assert_team_access(db, current_user, team_id, TEAM_REPORT_ELEVATED)
    team = await get_team(db, team_id)
    rows = await team_history(db, team_id, include_practice=True)
    return Response(
        content=_history_csv(rows, with_practice=True),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="historie-{team.id[:8]}.csv"'},
    )


@router.get("/history.csv")
async def export_all_history_csv(
    _=Depends(require_any_permission(*TEAM_REPORT_ELEVATED)),
    db: AsyncSession = Depends(get_db),
):
    """Official results of every team at every event over all seasons."""
    rows = await all_teams_history(db)
    return Response(
        content=_history_csv(rows, with_practice=False),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="mehrjahresvergleich.csv"'},
    )

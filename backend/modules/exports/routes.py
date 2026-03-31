"""Export routes – PDF and CSV downloads."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import csv
import io

from core.auth import require_any_permission
from core.database import get_db
from modules.exports.pdf_builder import (
    build_ranking_pdf,
    build_paper_review_pdf,
    build_print_report_pdf,
    build_team_list_pdf,
)
from modules.scoring.service import get_ranking, list_matches
from modules.paper_review.service import list_papers
from modules.printing.service import list_print_jobs, list_printers
from modules.teams.service import list_teams
from modules.teams.models import Team
from modules.printing.models import Printer
from modules.seasons.service import get_season

router = APIRouter(prefix="/exports", tags=["exports"])


# ── Helper: build ID → name maps ──────────────────────────────────────────────

async def _teams_map(db: AsyncSession, season_id: str | None = None) -> dict[str, str]:
    teams = await list_teams(db, season_id=season_id)
    return {t.id: t.name for t in teams}


async def _printers_map(db: AsyncSession) -> dict[str, str]:
    printers = await list_printers(db)
    return {p.id: p.name for p in printers}


# ── Ranking PDF ───────────────────────────────────────────────────────────────

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
        ranking_rows=[{
            "rank": r.rank,
            "team_id": r.team_id,
            "seed_score": r.seed_score,
            "best_score": r.best_score,
            "average_score": r.average_score,
            "rounds_played": r.rounds_played,
        } for r in ranking],
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
    writer = csv.writer(buf)
    writer.writerow(["Rang", "Team", "Seed-Score", "Best-Score", "Durchschnitt", "Runden"])
    for r in ranking:
        writer.writerow([
            r.rank,
            teams.get(r.team_id, r.team_id),
            f"{r.seed_score:.2f}",
            f"{r.best_score:.2f}",
            f"{r.average_score:.2f}",
            r.rounds_played,
        ])

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
    writer = csv.writer(buf)
    writer.writerow([
        "Match-ID", "Team", "Runde", "Tisch", "Total-Score",
        "DQ", "Yellow Card", "Red Card", "Notizen", "Eingetragen am",
    ])
    for m in matches:
        writer.writerow([
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
        ])

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
        papers_data.append({
            "team_id": p.team_id,
            "title": p.title,
            "status": p.status,
            "revision_number": p.revision_number,
            "reviews": [{"is_submitted": r.is_submitted, "total_score": r.total_score}
                        for r in p.reviews],
            "assignments": [{"id": a.id} for a in p.assignments],
        })

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
    writer = csv.writer(buf)
    writer.writerow([
        "Team", "Titel", "Status", "Revision",
        "Reviewer", "Ø Score", "Eingereicht am",
    ])
    for p in papers:
        submitted_reviews = [r for r in p.reviews if r.is_submitted]
        avg = (sum(r.total_score for r in submitted_reviews if r.total_score)
               / len(submitted_reviews)) if submitted_reviews else None
        writer.writerow([
            teams.get(p.team_id, p.team_id),
            p.title,
            p.status,
            p.revision_number,
            len(p.assignments),
            f"{avg:.2f}" if avg else "—",
            p.submitted_at.strftime("%d.%m.%Y") if p.submitted_at else "—",
        ])

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

    jobs_data = [{
        "team_id": j.team_id,
        "file_name": j.file_name,
        "material": j.material,
        "status": j.status,
        "printer_id": j.printer_id,
        "actual_grams": j.actual_grams,
        "estimated_grams": j.estimated_grams,
    } for j in jobs]

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

    teams_data = [{
        "name": t.name,
        "team_number": t.team_number,
        "school": t.school,
        "city": t.city,
        "country": t.country,
        "is_active": t.is_active,
    } for t in teams]

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
    writer = csv.writer(buf)
    writer.writerow(["Name", "Nummer", "Schule", "Stadt", "Land", "Status"])
    for t in teams:
        writer.writerow([
            t.name, t.team_number or "", t.school or "",
            t.city or "", t.country, "Aktiv" if t.is_active else "Inaktiv",
        ])

    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="teams-{season.year}.csv"'},
    )

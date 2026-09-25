"""The Playwright fixtures of scripts/seed_e2e.py: complete and idempotent."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import func, select

from modules.auth.models import Role, User, UserRole
from modules.auth.service import verify_password
from modules.bots.models import Bot
from modules.events.models import Event, EventRegistration
from modules.paper_review.models import Paper
from modules.printing.models import Printer, PrintJob, TeamSeasonPrintQuota
from modules.scoring import service as scoring_service
from modules.scoring.models import Match, Ranking
from modules.teams.models import Team, TeamMember

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seed_e2e.py"
_spec = importlib.util.spec_from_file_location("seed_e2e", _SCRIPT)
assert _spec and _spec.loader
seed_e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_e2e)


@pytest.fixture
async def roles(db):
    # Migrations create the roles; the test database is built from the models.
    for name in ("admin", "juror", "reviewer", "mentor", "guest"):
        db.add(Role(name=name, description=name))
    await db.flush()


async def _count(db, model, *where) -> int:
    return (await db.execute(select(func.count()).select_from(model).where(*where))).scalar_one()


async def test_seed_creates_everything_the_specs_use(db, roles):
    result = await seed_e2e.seed(db, password="e2e-secret")
    await db.commit()

    users = {u.email: u for u in (await db.execute(select(User))).scalars()}
    assert set(users) == {email for email, *_ in seed_e2e.USERS}
    assert verify_password("e2e-secret", users["juror@test.local"].hashed_password)
    assert users["admin@test.local"].is_superuser
    assert not users["guest@test.local"].is_superuser
    guest_roles = (
        await db.execute(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == users["guest@test.local"].id)
        )
    ).scalars()
    assert list(guest_roles) == ["guest"]

    event = await db.get(Event, result.event_id)
    assert event.slug == seed_e2e.EVENT_SLUG
    assert event.status == "live" and event.public_scoreboard
    assert {"bots", "paper", "printing", "seeding"} <= set(event.active_modules)
    assert await _count(db, EventRegistration, EventRegistration.event_id == event.id) == 6

    # The mentor belongs to exactly one team (the scoring spec counts options).
    memberships = (
        await db.execute(
            select(TeamMember.team_id).where(TeamMember.user_id == users["mentor@test.local"].id)
        )
    ).scalars()
    assert list(memberships) == [result.teams["RoboLions"]]

    ranking = {
        row.team_id: row
        for row in (await db.execute(select(Ranking).where(Ranking.event_id == event.id))).scalars()
    }
    assert ranking[result.teams["RoboLions"]].rank == 1
    assert ranking[result.teams["RoboLions"]].best_score == 140
    assert result.teams["Byte Busters"] not in ranking
    assert await _count(db, Match, Match.confirmed_by.is_(None)) == 0

    assert {b.name for b in (await db.execute(select(Bot))).scalars()} == {
        "RoboLion X1",
        "Zurich Crusher",
    }
    assert await _count(db, Paper, Paper.team_id == result.teams["RoboLions"]) == 1
    assert (await db.execute(select(Printer.printer_type))).scalar_one() == "generic"
    assert await _count(db, PrintJob, PrintJob.status == "pending") == 1


async def test_seed_is_idempotent_and_resets_the_flow_teams(db, roles):
    first = await seed_e2e.seed(db)
    # A run of the scoring flow leaves a result for "Byte Busters" …
    await scoring_service.create_match(
        db,
        {
            "season_id": first.season_id,
            "event_id": first.event_id,
            "team_id": first.teams["Byte Busters"],
            "round_number": 1,
            "raw_scores": {"objects": 17},
        },
        first.users["juror"],
    )
    # … and a spec changed a password.
    juror = await db.get(User, first.users["juror"])
    juror.hashed_password = "changed"
    await db.commit()

    second = await seed_e2e.seed(db)
    await db.commit()

    assert second.event_id == first.event_id
    assert second.teams == first.teams
    assert await _count(db, User) == len(seed_e2e.USERS)
    assert await _count(db, Team) == 6
    assert await _count(db, UserRole) == len(seed_e2e.USERS)
    assert await _count(db, Bot) == 2
    assert await _count(db, Paper) == 1
    assert await _count(db, PrintJob) == 1
    assert await _count(db, Match, Match.team_id == first.teams["Byte Busters"]) == 0
    assert await _count(db, Match) == 8  # two confirmed rounds of four teams
    await db.refresh(juror)
    assert verify_password(seed_e2e.DEFAULT_PASSWORD, juror.hashed_password)
    quota = (await db.execute(select(TeamSeasonPrintQuota))).scalar_one()
    assert quota.max_parts >= 1000


async def test_seed_refuses_to_run_outside_development(monkeypatch):
    monkeypatch.setattr(seed_e2e.get_settings(), "app_env", "production")
    with pytest.raises(SystemExit, match="APP_ENV=development"):
        await seed_e2e.main()

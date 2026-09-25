"""Create deterministic, non-production data for the Playwright end-to-end suite.

Everything the specs in ``frontend/e2e`` rely on is created here: one login per
role, six teams registered to a live, public event with a seeding phase and a
scoring schema, official seeding scores, gallery bots, a paper, a printer and a
print job.

The script is idempotent: running it again updates the fixtures in place
(passwords, roles, memberships, event flags) instead of duplicating them, and
resets the few records the flows change (the scores of the two teams the
scoring flows enter results for), so a rerun starts from the same state.

    APP_ENV=development python scripts/seed_e2e.py

Passwords default to ``test1234``; set ``E2E_PASSWORD`` to change them. The
script refuses to run outside ``APP_ENV=development``: it creates accounts with
well-known passwords.
"""

import asyncio
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

import core.modules  # noqa: E402,F401  (registers every model with the metadata)
from core.config import get_settings  # noqa: E402
from modules.auth.models import Role, User, UserRole  # noqa: E402
from modules.auth.service import hash_password  # noqa: E402
from modules.bots.models import Bot  # noqa: E402
from modules.events.models import Event, EventPhase, EventRegistration  # noqa: E402
from modules.paper_review.models import Paper  # noqa: E402
from modules.printing.models import Printer, PrintJob, TeamSeasonPrintQuota  # noqa: E402
from modules.scoring import service as scoring_service  # noqa: E402
from modules.scoring.models import Match, ScoringSchema  # noqa: E402
from modules.seasons.models import Season  # noqa: E402
from modules.teams.models import Team, TeamMember  # noqa: E402

DEFAULT_PASSWORD = "test1234"
EVENT_SLUG = "e2e-event"
SEASON_NAME = "E2E Season"

# email, display name, roles, superuser. "mentor2" files the papers of the
# teams the paper flow creates, so the first mentor keeps exactly one team.
USERS: list[tuple[str, str, list[str], bool]] = [
    ("admin@test.local", "E2E Admin", ["admin"], True),
    ("juror@test.local", "E2E Jurorin", ["juror"], False),
    ("reviewer@test.local", "E2E Reviewer", ["reviewer"], False),
    ("mentor@test.local", "E2E Mentor", ["mentor"], False),
    ("mentor2@test.local", "E2E Mentorin Paper", ["mentor"], False),
    ("guest@test.local", "E2E Gast", ["guest"], False),
]

# name, number, school, seeding scores ("objects" per round; None = no scores).
TEAMS: list[tuple[str, str, str, list[int] | None]] = [
    ("RoboLions", "E2E-1", "HTL Löwenstadt", [12, 14]),
    ("Circuit Breakers", "E2E-2", "BRG Stromfeld", [9, 11]),
    ("Gear Grinders", "E2E-3", "HTL Zahnrad", [6, 8]),
    ("Servo Squad", "E2E-4", "BG Servoberg", [4, 5]),
    # The scoring flows enter results for these two; the seed clears them.
    ("Byte Busters", "E2E-5", "HTL Bytehausen", None),
    ("Offline Otters", "E2E-6", "BRG Funkloch", None),
]
MENTOR_TEAM = "RoboLions"

SCHEMA_FIELDS = [
    {
        "key": "objects",
        "label": "Objekte",
        "type": "count",
        "multiplier": 10,
        "min_value": 0,
        "max_value": 20,
        "required": True,
    }
]


@dataclass
class SeedResult:
    event_id: str
    season_id: str
    users: dict[str, str] = field(default_factory=dict)
    teams: dict[str, str] = field(default_factory=dict)


async def _one(db: AsyncSession, statement):
    return (await db.execute(statement)).scalars().first()


async def _seed_users(db: AsyncSession, password: str) -> dict[str, User]:
    roles = {role.name: role for role in (await db.execute(select(Role))).scalars()}
    hashed = hash_password(password)
    users: dict[str, User] = {}
    for email, name, role_names, superuser in USERS:
        user = await _one(db, select(User).where(User.email == email))
        if user is None:
            user = User(email=email, display_name=name, hashed_password=hashed)
            db.add(user)
        # Reset on every run: a spec may have changed them, and a stale
        # password would lock the whole suite out.
        user.display_name = name
        user.hashed_password = hashed
        user.is_active = True
        user.is_superuser = superuser
        user.preferred_language = "de"
        await db.flush()
        assigned = set(
            (await db.execute(select(UserRole.role_id).where(UserRole.user_id == user.id)))
            .scalars()
            .all()
        )
        for role_name in role_names:
            role = roles.get(role_name)
            if role is None:
                raise SystemExit(
                    f"Role '{role_name}' is missing - run 'alembic upgrade head' first."
                )
            if role.id not in assigned:
                db.add(UserRole(user_id=user.id, role_id=role.id))
        users[email.split("@")[0]] = user
    await db.flush()
    return users


async def _seed_season_and_event(db: AsyncSession) -> tuple[Season, Event]:
    season = await _one(db, select(Season).where(Season.name == SEASON_NAME))
    if season is None:
        season = Season(name=SEASON_NAME, year=2026)
        db.add(season)
    season.is_active = True
    season.status = "active"
    season.use_seeding = True
    await db.flush()
    # Exactly one active season: the specs resolve "the" season through it.
    for other in (await db.execute(select(Season).where(Season.id != season.id))).scalars():
        if other.is_active or other.status == "active":
            other.is_active = False
            other.status = "finished"

    event = await _one(db, select(Event).where(Event.slug == EVENT_SLUG))
    if event is None:
        event = Event(season_id=season.id, name="E2E Regional", slug=EVENT_SLUG)
        db.add(event)
    event.season_id = season.id
    # "live": the app opens the live event by default, so events the specs
    # create themselves never become the landing page.
    event.status = "live"
    event.timezone = "Europe/Vienna"
    event.venue = "Test Arena"
    event.active_modules = ["seeding", "paper", "printing", "bots"]
    event.public_scoreboard = True
    event.public_schedule = True
    event.public_results = True
    event.public_announcements = True
    await db.flush()

    phase = await _one(db, select(EventPhase).where(EventPhase.event_id == event.id))
    if phase is None:
        db.add(
            EventPhase(
                event_id=event.id, name="Seeding", phase_type="seeding", rounds=3, status="live"
            )
        )
    schema = await _one(
        db,
        select(ScoringSchema).where(
            ScoringSchema.event_id == event.id, ScoringSchema.is_active.is_(True)
        ),
    )
    if schema is None:
        schema = ScoringSchema(season_id=season.id, event_id=event.id, version=1, is_active=True)
        db.add(schema)
    # The specs fill in the "Objekte" field by its label.
    schema.fields = SCHEMA_FIELDS
    schema.definition = None
    await db.flush()
    return season, event


async def _seed_teams(db: AsyncSession, event: Event, users: dict[str, User]) -> dict[str, Team]:
    teams: dict[str, Team] = {}
    for seed_number, (name, number, school, _scores) in enumerate(TEAMS, start=1):
        team = await _one(db, select(Team).where(Team.team_number == number))
        if team is None:
            team = Team(team_number=number, name=name)
            db.add(team)
        team.name = name
        team.school = school
        team.country = "AT"
        team.is_active = True
        await db.flush()
        registration = await _one(
            db,
            select(EventRegistration).where(
                EventRegistration.event_id == event.id, EventRegistration.team_id == team.id
            ),
        )
        if registration is None:
            db.add(
                EventRegistration(
                    event_id=event.id, team_id=team.id, seed_number=seed_number, category="botball"
                )
            )
        teams[name] = team

    # The mentor belongs to exactly one team; the scoring spec relies on it.
    mentor = users["mentor"]
    memberships = (
        (await db.execute(select(TeamMember).where(TeamMember.user_id == mentor.id)))
        .scalars()
        .all()
    )
    lions = teams[MENTOR_TEAM]
    for membership in memberships:
        if membership.team_id != lions.id:
            await db.delete(membership)
    if not any(m.team_id == lions.id for m in memberships):
        db.add(
            TeamMember(
                team_id=lions.id,
                user_id=mentor.id,
                name=mentor.display_name,
                email=mentor.email,
                role="mentor",
            )
        )
    await db.flush()
    return teams


async def _seed_scores(
    db: AsyncSession, season: Season, event: Event, teams: dict[str, Team], juror: User
) -> None:
    for name, _number, _school, scores in TEAMS:
        team = teams[name]
        if scores is None:
            # Flow teams start without results on every run.
            for match in (
                await db.execute(
                    select(Match).where(Match.event_id == event.id, Match.team_id == team.id)
                )
            ).scalars():
                await scoring_service.delete_match(db, match.id, reason="E2E seed reset")
            continue
        for round_number, objects in enumerate(scores, start=1):
            match = await scoring_service.create_match(
                db,
                {
                    "season_id": season.id,
                    "event_id": event.id,
                    "team_id": team.id,
                    "round_number": round_number,
                    "raw_scores": {"objects": objects},
                    "idempotency_key": f"e2e-seed-{team.team_number}-{round_number}",
                },
                juror.id,
            )
            if match.confirmed_by is None:
                await scoring_service.confirm_match(db, match.id, juror.id)
    await db.flush()


async def _seed_gallery_paper_printing(
    db: AsyncSession, season: Season, event: Event, teams: dict[str, Team], users: dict[str, User]
) -> None:
    lions = teams[MENTOR_TEAM]
    bots = [
        {
            "name": "RoboLion X1",
            "team_id": lions.id,
            "external_team_name": None,
            "description": "Schneller Sammelroboter der RoboLions.",
            "functionality": "Differentialantrieb mit zwei Motoren; ein Greifer sammelt die "
            "Objekte, eine Kamera erkennt die Farben.",
            "drive_type": "Differential",
            "sensors": "2x IR, Kamera",
        },
        {
            "name": "Zurich Crusher",
            "team_id": None,
            "external_team_name": "Team Zürich",
            "description": "Gegner aus der Schweiz, beobachtet beim ECER.",
            "functionality": "Kettenantrieb, schiebt Objekte mit einer Schaufel.",
            "drive_type": "Kette",
            "sensors": "Ultraschall",
        },
    ]
    for data in bots:
        bot = await _one(db, select(Bot).where(Bot.name == data["name"]))
        if bot is None:
            bot = Bot(name=data["name"], created_by=users["admin"].id)
            db.add(bot)
        for key, value in data.items():
            setattr(bot, key, value)
        bot.season_id = season.id
        bot.is_published = True

    paper = await _one(
        db, select(Paper).where(Paper.season_id == season.id, Paper.team_id == lions.id)
    )
    if paper is None:
        db.add(
            Paper(
                season_id=season.id,
                event_id=event.id,
                team_id=lions.id,
                title="RoboLions: Sammeln mit Kamera",
                abstract="Wie unser Roboter Farben erkennt.",
                status="draft",
            )
        )

    printer = await _one(db, select(Printer).where(Printer.name == "E2E Drucker"))
    if printer is None:
        printer = Printer(name="E2E Drucker", printer_type="generic")
        db.add(printer)
    printer.is_active = True
    await db.flush()

    # Every run of the print flow files and completes one more part; lift the
    # team's hard limit (default 4 parts) so reruns never hit it.
    quota = await _one(
        db,
        select(TeamSeasonPrintQuota).where(
            TeamSeasonPrintQuota.event_id == event.id, TeamSeasonPrintQuota.team_id == lions.id
        ),
    )
    if quota is None:
        quota = TeamSeasonPrintQuota(team_id=lions.id, season_id=season.id, event_id=event.id)
        db.add(quota)
    quota.max_parts = 10_000
    quota.soft_limit_parts = 10_000

    job = await _one(
        db,
        select(PrintJob).where(
            PrintJob.team_id == lions.id, PrintJob.file_name == "robolion-greifer.stl"
        ),
    )
    if job is None:
        db.add(
            PrintJob(
                team_id=lions.id,
                season_id=season.id,
                event_id=event.id,
                submitted_by=users["mentor"].id,
                file_name="robolion-greifer.stl",
                material="PLA",
                estimated_grams=25,
                status="pending",
            )
        )
    await db.flush()


async def seed(db: AsyncSession, password: str = DEFAULT_PASSWORD) -> SeedResult:
    """Create or refresh the E2E fixtures in ``db`` (the caller commits)."""
    users = await _seed_users(db, password)
    season, event = await _seed_season_and_event(db)
    teams = await _seed_teams(db, event, users)
    await _seed_scores(db, season, event, teams, users["juror"])
    await _seed_gallery_paper_printing(db, season, event, teams, users)
    return SeedResult(
        event_id=event.id,
        season_id=season.id,
        users={key: user.id for key, user in users.items()},
        teams={name: team.id for name, team in teams.items()},
    )


async def main() -> None:
    if not get_settings().is_dev:
        raise SystemExit("seed_e2e.py creates well-known logins; run it with APP_ENV=development.")
    from core.database import AsyncSessionLocal, engine

    engine.echo = False  # development echoes every statement; keep CI logs readable
    async with AsyncSessionLocal() as db:
        result = await seed(db, os.environ.get("E2E_PASSWORD") or DEFAULT_PASSWORD)
        await db.commit()
    print(f"E2E_EVENT_ID={result.event_id}")
    print(f"E2E_EVENT_SLUG={EVENT_SLUG}")


if __name__ == "__main__":
    asyncio.run(main())

"""Create deterministic, non-production data for the Playwright smoke suite."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from core.database import AsyncSessionLocal  # noqa: E402
from modules.auth.models import User  # noqa: E402
from modules.auth.service import hash_password  # noqa: E402
from modules.events.models import Event, EventPhase, EventRegistration  # noqa: E402
from modules.scoring.models import ScoringSchema  # noqa: E402
from modules.seasons.models import Season  # noqa: E402
from modules.teams.models import Team  # noqa: E402


async def main() -> None:
    async with AsyncSessionLocal() as db:
        user_result = await db.execute(select(User).where(User.email == "admin@example.com"))
        user = user_result.scalar_one_or_none()
        if not user:
            db.add(
                User(
                    email="admin@example.com",
                    display_name="E2E Administrator",
                    hashed_password=hash_password("change-this-password"),
                    is_active=True,
                    is_superuser=True,
                )
            )
        season_result = await db.execute(select(Season).where(Season.year == 2026))
        season = season_result.scalar_one_or_none()
        if not season:
            season = Season(name="E2E Season", year=2026, is_active=True)
            db.add(season)
            await db.flush()
        event_result = await db.execute(select(Event).where(Event.slug == "e2e-event"))
        event = event_result.scalar_one_or_none()
        if not event:
            event = Event(
                season_id=season.id,
                name="E2E Regional",
                slug="e2e-event",
                status="published",
                timezone="Europe/Vienna",
                venue="Test Arena",
                public_scoreboard=True,
                public_schedule=True,
                public_results=True,
                public_announcements=True,
            )
            db.add(event)
            await db.flush()
        team_result = await db.execute(select(Team).where(Team.team_number == "E2E-1"))
        team = team_result.scalar_one_or_none()
        if not team:
            team = Team(name="E2E Team", team_number="E2E-1", country="AT")
            db.add(team)
            await db.flush()
        registration = await db.execute(
            select(EventRegistration).where(
                EventRegistration.event_id == event.id,
                EventRegistration.team_id == team.id,
            )
        )
        if not registration.scalar_one_or_none():
            db.add(EventRegistration(event_id=event.id, team_id=team.id, seed_number=1))
        phase = await db.execute(select(EventPhase).where(EventPhase.event_id == event.id))
        if not phase.scalars().first():
            db.add(
                EventPhase(
                    event_id=event.id,
                    name="Seeding",
                    phase_type="seeding",
                    rounds=2,
                )
            )
        schema = await db.execute(
            select(ScoringSchema).where(
                ScoringSchema.event_id == event.id,
                ScoringSchema.is_active.is_(True),
            )
        )
        if not schema.scalars().first():
            db.add(
                ScoringSchema(
                    season_id=season.id,
                    event_id=event.id,
                    version=1,
                    is_active=True,
                    fields=[
                        {
                            "key": "objects",
                            "label": "Objects",
                            "type": "count",
                            "multiplier": 10,
                            "min_value": 0,
                            "max_value": 20,
                            "required": True,
                        }
                    ],
                )
            )
        await db.commit()
        print(f"E2E_EVENT_ID={event.id}")


if __name__ == "__main__":
    asyncio.run(main())

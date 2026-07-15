"""Unit tests for core.auth.assert_team_access — the own-team scoping used for
mentor self-service (papers, scores, print jobs, team management)."""
import pytest

from core.auth import assert_team_access
from core.exceptions import ForbiddenError
from modules.auth.models import User
from modules.auth.service import hash_password
from modules.teams.models import Team, TeamMember


async def _user(db, email, superuser=False):
    u = User(email=email, display_name="U", hashed_password=hash_password("password123"),
             is_active=True, is_superuser=superuser)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _team(db, name):
    t = Team(name=name, country="DE")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


class TestAssertTeamAccess:
    @pytest.mark.asyncio
    async def test_non_member_forbidden(self, db):
        user = await _user(db, "m1@test.com")
        team = await _team(db, "T1")
        with pytest.raises(ForbiddenError):
            await assert_team_access(db, user, team.id, "teams:admin")

    @pytest.mark.asyncio
    async def test_member_allowed(self, db):
        user = await _user(db, "m2@test.com")
        team = await _team(db, "T2")
        db.add(TeamMember(team_id=team.id, user_id=user.id, name="Mentor", role="mentor"))
        await db.commit()
        # Member of the team → no exception.
        await assert_team_access(db, user, team.id, "teams:admin")

    @pytest.mark.asyncio
    async def test_superuser_bypasses(self, db):
        user = await _user(db, "su@test.com", superuser=True)
        # Not a member of any team, but superuser → allowed.
        await assert_team_access(db, user, "any-team-id", "teams:admin")

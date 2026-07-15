"""Unit tests for the teams service layer.

Covers every public function in modules/teams/service.py:
list_teams, get_team, create_team, update_team, delete_team, add_member,
remove_member, register_for_season (duplicate guard), confirm_registration,
list_registrations.
"""
import pytest
from sqlalchemy import select

from core.exceptions import ConflictError, NotFoundError
from modules.seasons import service as seasons_service
from modules.teams import service
from modules.teams.models import Team, TeamMember, TeamSeasonRegistration


async def _members_for(db, team_id):
    """Read member rows directly.

    The shared test session uses autoflush=False and create_team never
    commits, so the returned team object exposes a stale (empty) `members`
    collection. The rows are persisted on flush, so query them directly.
    """
    result = await db.execute(
        select(TeamMember).where(TeamMember.team_id == team_id)
    )
    return list(result.scalars().all())


# ── create_team ───────────────────────────────────────────────────────────────

class TestCreateTeam:
    @pytest.mark.asyncio
    async def test_create_minimal(self, db):
        t = await service.create_team(db, {"name": "Solo"}, [])
        assert t.id is not None
        assert t.name == "Solo"
        assert t.country == "DE"  # model default
        assert t.is_active is True  # model default
        assert t.members == []

    @pytest.mark.asyncio
    async def test_create_with_members(self, db):
        members = [
            {"name": "Alice", "role": "mentor", "email": "a@x.com", "user_id": None},
            {"name": "Bob", "role": "member", "email": None, "user_id": None},
        ]
        t = await service.create_team(db, {"name": "Duo", "country": "AT"}, members)
        await db.flush()
        rows = await _members_for(db, t.id)
        assert len(rows) == 2
        assert {m.name for m in rows} == {"Alice", "Bob"}

    @pytest.mark.asyncio
    async def test_create_with_optional_fields(self, db):
        data = {"name": "Full", "team_number": "FT-1", "school": "HTL",
                "city": "Graz", "country": "AT", "notes": "hi"}
        t = await service.create_team(db, data, [])
        assert t.team_number == "FT-1"
        assert t.school == "HTL"
        assert t.city == "Graz"
        assert t.notes == "hi"


# ── list_teams ────────────────────────────────────────────────────────────────

class TestListTeams:
    @pytest.mark.asyncio
    async def test_empty(self, db):
        assert await service.list_teams(db) == []

    @pytest.mark.asyncio
    async def test_ordered_by_name(self, db):
        await service.create_team(db, {"name": "Zeta"}, [])
        await service.create_team(db, {"name": "Alpha"}, [])
        await service.create_team(db, {"name": "Mike"}, [])
        await db.flush()
        teams = await service.list_teams(db)
        assert [t.name for t in teams] == ["Alpha", "Mike", "Zeta"]

    @pytest.mark.asyncio
    async def test_filter_by_season(self, db, season):
        registered = await service.create_team(db, {"name": "Registered"}, [])
        await service.create_team(db, {"name": "Unregistered"}, [])
        await db.flush()
        await service.register_for_season(db, registered.id, season.id)
        await db.flush()

        teams = await service.list_teams(db, season_id=season.id)
        assert [t.name for t in teams] == ["Registered"]

    @pytest.mark.asyncio
    async def test_filter_by_competition_level(self, db):
        from modules.seasons.models import CompetitionLevel
        level = CompetitionLevel(name="ECER", code="ecer")
        db.add(level)
        await db.flush()

        await service.create_team(db, {"name": "Leveled", "competition_level_id": level.id}, [])
        await service.create_team(db, {"name": "NoLevel"}, [])
        await db.flush()

        teams = await service.list_teams(db, competition_level_id=level.id)
        assert [t.name for t in teams] == ["Leveled"]


# ── get_team ──────────────────────────────────────────────────────────────────

class TestGetTeam:
    @pytest.mark.asyncio
    async def test_found(self, db, team):
        fetched = await service.get_team(db, team.id)
        assert fetched.id == team.id

    @pytest.mark.asyncio
    async def test_not_found_raises(self, db):
        with pytest.raises(NotFoundError):
            await service.get_team(db, "missing")


# ── update_team ───────────────────────────────────────────────────────────────

class TestUpdateTeam:
    @pytest.mark.asyncio
    async def test_update_name(self, db, team):
        updated = await service.update_team(db, team.id, name="New Name")
        assert updated.name == "New Name"

    @pytest.mark.asyncio
    async def test_none_values_ignored(self, db, team):
        original = team.name
        updated = await service.update_team(db, team.id, name=None, city="Vienna")
        assert updated.name == original
        assert updated.city == "Vienna"

    @pytest.mark.asyncio
    async def test_update_is_active_false(self, db, team):
        # is_active=False is a real value, not None → must apply
        updated = await service.update_team(db, team.id, is_active=False)
        assert updated.is_active is False

    @pytest.mark.asyncio
    async def test_update_not_found(self, db):
        with pytest.raises(NotFoundError):
            await service.update_team(db, "missing", name="X")


# ── delete_team ───────────────────────────────────────────────────────────────

class TestDeleteTeam:
    @pytest.mark.asyncio
    async def test_delete(self, db):
        t = await service.create_team(db, {"name": "Del"}, [])
        await db.flush()
        tid = t.id
        await service.delete_team(db, tid)
        await db.flush()
        with pytest.raises(NotFoundError):
            await service.get_team(db, tid)

    @pytest.mark.asyncio
    async def test_delete_not_found(self, db):
        with pytest.raises(NotFoundError):
            await service.delete_team(db, "missing")

    @pytest.mark.asyncio
    async def test_delete_cascades_members(self, db):
        t = await service.create_team(db, {"name": "WithMembers"},
                                      [{"name": "M1", "role": "member"}])
        # Commit + expire so get_team (inside delete_team) loads the members
        # relationship fresh, letting the ORM "all, delete-orphan" cascade fire.
        await db.commit()
        tid = t.id
        db.expire_all()
        assert len(await _members_for(db, tid)) == 1

        await service.delete_team(db, tid)
        await db.flush()
        # Cascade removes the member rows along with the team
        assert await _members_for(db, tid) == []


# ── add_member ────────────────────────────────────────────────────────────────

class TestAddMember:
    @pytest.mark.asyncio
    async def test_add(self, db, team):
        member = await service.add_member(
            db, team.id, {"name": "Charlie", "role": "mentor", "email": None, "user_id": None}
        )
        assert member.id is not None
        assert member.name == "Charlie"
        assert member.team_id == team.id

    @pytest.mark.asyncio
    async def test_add_to_missing_team_raises(self, db):
        with pytest.raises(NotFoundError):
            await service.add_member(db, "missing", {"name": "X", "role": "member"})


# ── remove_member ─────────────────────────────────────────────────────────────

class TestRemoveMember:
    @pytest.mark.asyncio
    async def test_remove(self, db, team):
        member = await service.add_member(
            db, team.id, {"name": "Temp", "role": "member"}
        )
        await db.flush()
        mid = member.id
        await service.remove_member(db, team.id, mid)
        await db.flush()
        from sqlalchemy import select
        result = await db.execute(select(TeamMember).where(TeamMember.id == mid))
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_remove_missing_member_raises(self, db, team):
        with pytest.raises(NotFoundError):
            await service.remove_member(db, team.id, "missing")

    @pytest.mark.asyncio
    async def test_remove_member_wrong_team_raises(self, db, team):
        # member belongs to `team`, but we ask to remove it from another team
        member = await service.add_member(db, team.id, {"name": "X", "role": "member"})
        await db.flush()
        other = await service.create_team(db, {"name": "Other"}, [])
        await db.flush()
        with pytest.raises(NotFoundError):
            await service.remove_member(db, other.id, member.id)


# ── register_for_season (duplicate guard) ─────────────────────────────────────

class TestRegisterForSeason:
    @pytest.mark.asyncio
    async def test_register(self, db, team, season):
        reg = await service.register_for_season(db, team.id, season.id)
        assert reg.id is not None
        assert reg.team_id == team.id
        assert reg.season_id == season.id
        assert reg.confirmed is False

    @pytest.mark.asyncio
    async def test_register_with_kwargs(self, db, team, season):
        reg = await service.register_for_season(
            db, team.id, season.id, competition_level_id=None, notes="please"
        )
        assert reg.notes == "please"

    @pytest.mark.asyncio
    async def test_duplicate_raises_conflict(self, db, team, season):
        await service.register_for_season(db, team.id, season.id)
        await db.flush()
        with pytest.raises(ConflictError):
            await service.register_for_season(db, team.id, season.id)

    @pytest.mark.asyncio
    async def test_same_team_different_seasons_ok(self, db, team, season):
        other_season = await seasons_service.create_season(
            db, {"name": "Other", "year": 2099}, []
        )
        await db.flush()
        await service.register_for_season(db, team.id, season.id)
        await db.flush()
        # No conflict for a different season
        reg2 = await service.register_for_season(db, team.id, other_season.id)
        assert reg2.season_id == other_season.id


# ── confirm_registration ──────────────────────────────────────────────────────

class TestConfirmRegistration:
    @pytest.mark.asyncio
    async def test_confirm(self, db, team, season):
        reg = await service.register_for_season(db, team.id, season.id)
        await db.flush()
        confirmed = await service.confirm_registration(db, reg.id)
        assert confirmed.confirmed is True

    @pytest.mark.asyncio
    async def test_confirm_not_found_raises(self, db):
        with pytest.raises(NotFoundError):
            await service.confirm_registration(db, "missing")


# ── list_registrations ────────────────────────────────────────────────────────

class TestListRegistrations:
    @pytest.mark.asyncio
    async def test_empty(self, db):
        assert await service.list_registrations(db) == []

    @pytest.mark.asyncio
    async def test_list_all(self, db, team, season):
        await service.register_for_season(db, team.id, season.id)
        await db.flush()
        regs = await service.list_registrations(db)
        assert len(regs) == 1

    @pytest.mark.asyncio
    async def test_filter_by_season(self, db, team, season):
        other_season = await seasons_service.create_season(
            db, {"name": "Other", "year": 2099}, []
        )
        await db.flush()
        await service.register_for_season(db, team.id, season.id)
        await service.register_for_season(db, team.id, other_season.id)
        await db.flush()

        regs = await service.list_registrations(db, season_id=season.id)
        assert len(regs) == 1
        assert regs[0].season_id == season.id

    @pytest.mark.asyncio
    async def test_filter_by_team(self, db, team, season):
        other_team = await service.create_team(db, {"name": "Other"}, [])
        await db.flush()
        await service.register_for_season(db, team.id, season.id)
        await service.register_for_season(db, other_team.id, season.id)
        await db.flush()

        regs = await service.list_registrations(db, team_id=team.id)
        assert len(regs) == 1
        assert regs[0].team_id == team.id

    @pytest.mark.asyncio
    async def test_filter_by_team_and_season(self, db, team, season):
        await service.register_for_season(db, team.id, season.id)
        await db.flush()
        regs = await service.list_registrations(db, season_id=season.id, team_id=team.id)
        assert len(regs) == 1

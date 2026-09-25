"""The test database fixture: commits inside a test never reach the next test.

conftest.db wraps each test in an outer transaction and lets the session work
on SAVEPOINTs. The two tests below run in file order: the first commits, the
second must not see it.
"""

from sqlalchemy import func, select

from modules.teams.models import Team


async def _team_names(db) -> list[str]:
    return list((await db.execute(select(Team.name).order_by(Team.name))).scalars())


async def test_commit_and_rollback_behave_like_a_real_session(db):
    db.add(Team(name="Committed", country="DE"))
    await db.commit()
    db.add(Team(name="Rolled back", country="DE"))
    await db.flush()
    await db.rollback()
    # A rollback only undoes the work since the last commit.
    assert await _team_names(db) == ["Committed"]


async def test_the_previous_tests_commit_is_gone(db):
    assert (await db.execute(select(func.count()).select_from(Team))).scalar_one() == 0


async def test_routes_that_commit_are_isolated_too(client, auth_headers, db):
    response = await client.post(
        "/api/teams", headers=auth_headers, json={"name": "Via API", "country": "DE"}
    )
    assert response.status_code == 201, response.text
    assert await _team_names(db) == ["Via API"]


async def test_nothing_from_the_route_test_is_left(db):
    assert await _team_names(db) == []

"""Refresh-token rotation: row lock and reuse detection.

A refresh token is single-use. Presenting one that was already rotated means
two parties hold it (the legitimate client and a thief); since the server
cannot tell which is which, every session of the account ends, including the
access tokens already issued. The stored row is read with ``FOR UPDATE`` so
two concurrent refreshes with the same token cannot both succeed on
PostgreSQL.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import Select

from core.auth import create_refresh_token
from modules.auth import service
from modules.auth.models import RefreshToken, User
from modules.auth.service import hash_password

PASSWORD = "password123"


@pytest.fixture
async def user(db) -> User:
    u = User(
        email="rotate@example.com",
        display_name="Rotate",
        hashed_password=hash_password(PASSWORD),
        is_active=True,
    )
    db.add(u)
    await db.commit()
    return u


async def _seed(db, user: User, days: int) -> str:
    token = create_refresh_token(user.id)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=service._hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(days=days),
        )
    )
    await db.commit()
    return token


@pytest.mark.asyncio
async def test_reusing_a_rotated_token_ends_every_session(client, db, user):
    stolen = await _seed(db, user, 300)
    other_device = await _seed(db, user, 200)

    # The thief rotates first ...
    first = await client.post("/api/auth/refresh", json={"refresh_token": stolen})
    assert first.status_code == 200, first.text
    thief_refresh = first.cookies.get("refresh_token")
    thief_access = first.json()["access_token"]
    await db.commit()
    client.cookies.clear()

    # ... then the legitimate client presents the same (now rotated) token.
    reuse = await client.post("/api/auth/refresh", json={"refresh_token": stolen})
    assert reuse.status_code == 401
    await db.commit()

    # The whole account is signed out: the thief's new pair and other devices.
    for token in (thief_refresh, other_device):
        resp = await client.post("/api/auth/refresh", json={"refresh_token": token})
        assert resp.status_code == 401, resp.text
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {thief_access}"})
    assert me.status_code == 401
    assert (await db.execute(select(RefreshToken))).scalars().all() == []


@pytest.mark.asyncio
async def test_unknown_or_logged_out_token_ends_no_sessions(client, db, user):
    other_device = await _seed(db, user, 200)
    token_version = user.token_version
    unknown = create_refresh_token(user.id)
    resp = await client.post("/api/auth/refresh", json={"refresh_token": unknown})
    assert resp.status_code == 401
    await db.commit()
    await db.refresh(user)
    assert user.token_version == token_version
    ok = await client.post("/api/auth/refresh", json={"refresh_token": other_device})
    assert ok.status_code == 200, ok.text


@pytest.mark.asyncio
async def test_expired_token_is_refused_without_ending_sessions(client, db, user):
    token = await _seed(db, user, 50)
    row = (await db.execute(select(RefreshToken))).scalar_one()
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db.commit()
    token_version = user.token_version
    resp = await client.post("/api/auth/refresh", json={"refresh_token": token})
    assert resp.status_code == 401
    await db.refresh(user)
    assert user.token_version == token_version


@pytest.mark.asyncio
async def test_stored_token_is_read_with_a_row_lock(db, user, monkeypatch):
    token = await _seed(db, user, 30)
    statements: list = []
    execute = db.execute

    async def spy(statement, *args, **kwargs):
        statements.append(statement)
        return await execute(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", spy)
    await service.refresh_tokens(db, token)
    lookups = [
        s
        for s in statements
        if isinstance(s, Select) and RefreshToken.__table__ in s.get_final_froms()
    ]
    assert lookups, "the refresh token row must be read"
    sql = str(lookups[0].compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql, sql

"""Regression test: rapid successive logins for the same user.

Refresh tokens are stored by a UNIQUE hash. The refresh JWT used to carry only
{sub, exp, type}; because `exp` has second granularity, two logins for the same
user within the same second produced an identical token whose hash collided,
failing the second login with 409. A `jti` claim keeps each token unique.
"""
import asyncio

import pytest

from modules.auth.models import User
from modules.auth.service import hash_password

PASSWORD = "password123"


@pytest.fixture
async def plain_user(db):
    user = User(
        email="login-race@test.com",
        display_name="Race",
        hashed_password=hash_password(PASSWORD),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


class TestRepeatedLogin:
    @pytest.mark.asyncio
    async def test_two_logins_in_a_row_both_succeed(self, client, plain_user, db):
        creds = {"email": plain_user.email, "password": PASSWORD}
        first = await client.post("/api/auth/login", json=creds)
        second = await client.post("/api/auth/login", json=creds)

        assert first.status_code == 200
        assert second.status_code == 200, f"second login failed: {second.text}"
        # Distinct refresh tokens → distinct hashes → no unique-constraint clash.
        assert first.cookies.get("refresh_token") != second.cookies.get("refresh_token")

    @pytest.mark.asyncio
    async def test_concurrent_logins_all_succeed(self, client, plain_user):
        creds = {"email": plain_user.email, "password": PASSWORD}
        results = await asyncio.gather(
            *[client.post("/api/auth/login", json=creds) for _ in range(3)]
        )
        assert [r.status_code for r in results] == [200, 200, 200]

    @pytest.mark.asyncio
    async def test_refresh_tokens_are_unique(self):
        from core.auth import create_refresh_token

        tokens = {create_refresh_token("same-user-id") for _ in range(5)}
        assert len(tokens) == 5

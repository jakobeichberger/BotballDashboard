"""PyJWT tokens and the logout deny-list for access tokens."""

import time
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from core import token_denylist
from core.auth import ALGORITHM, create_access_token, decode_token
from core.config import get_settings
from core.exceptions import UnauthorizedError
from modules.auth.service import create_user


@pytest.fixture(autouse=True)
def clean_denylist():
    token_denylist.clear_memory()
    yield
    token_denylist.clear_memory()


async def _login(client, email="user@test.com", password="password123"):
    resp = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


class TestTokenFormat:
    def test_access_token_claims(self):
        payload = decode_token(create_access_token("u1", {"tv": 3}))
        assert payload["sub"] == "u1"
        assert payload["type"] == "access"
        assert payload["tv"] == 3
        assert payload["jti"]
        assert jwt.get_unverified_header(create_access_token("u1"))["alg"] == "HS256"

    def test_every_token_has_its_own_jti(self):
        assert (
            decode_token(create_access_token("u1"))["jti"]
            != (decode_token(create_access_token("u1"))["jti"])
        )

    def test_legacy_token_without_jti_still_valid(self):
        """Tokens issued before the switch (python-jose, no jti) keep working."""
        legacy = jwt.encode(
            {"sub": "u1", "exp": datetime.now(UTC) + timedelta(minutes=5), "type": "access"},
            get_settings().jwt_secret_key,
            algorithm=ALGORITHM,
        )
        assert decode_token(legacy)["sub"] == "u1"

    def test_rejects_unsigned_expired_and_foreign_tokens(self):
        secret = get_settings().jwt_secret_key
        claims = {"sub": "u1", "type": "access"}
        unsigned = jwt.encode(
            {**claims, "exp": datetime.now(UTC) + timedelta(minutes=5)}, None, algorithm="none"
        )
        expired = jwt.encode(
            {**claims, "exp": datetime.now(UTC) - timedelta(seconds=1)}, secret, algorithm=ALGORITHM
        )
        no_exp = jwt.encode(claims, secret, algorithm=ALGORITHM)
        foreign = jwt.encode(
            {**claims, "exp": datetime.now(UTC) + timedelta(minutes=5)},
            "another-secret-that-is-long-enough",
            algorithm=ALGORITHM,
        )
        for token in (unsigned, expired, no_exp, foreign):
            with pytest.raises(UnauthorizedError):
                decode_token(token)


class TestLogoutDenylist:
    @pytest.mark.asyncio
    async def test_logout_revokes_only_this_access_token(self, client, db):
        await create_user(db, "user@test.com", "User", "password123", [])
        await db.commit()
        first = await _login(client)
        second = await _login(client)
        assert (await client.get("/api/auth/me", headers=first)).status_code == 200

        resp = await client.post("/api/auth/logout", headers=first)
        assert resp.status_code == 204

        revoked = await client.get("/api/auth/me", headers=first)
        assert revoked.status_code == 401
        # Another session (device) of the same user stays signed in.
        assert (await client.get("/api/auth/me", headers=second)).status_code == 200

    @pytest.mark.asyncio
    async def test_logout_with_invalid_token_is_harmless(self, client):
        resp = await client.post(
            "/api/auth/logout", headers={"Authorization": "Bearer not.a.token"}
        )
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_denied_entry_expires_with_the_token(self):
        await token_denylist.deny("abc", time.time() - 5)
        # Entries are kept at least one second, then dropped.
        assert await token_denylist.is_denied("abc") is True
        token_denylist._memory["abc"] = time.time() - 1
        assert await token_denylist.is_denied("abc") is False

    @pytest.mark.asyncio
    async def test_redis_outage_fails_open(self, monkeypatch):
        class Broken:
            async def set(self, *args, **kwargs):
                raise ConnectionError("down")

            async def exists(self, *args):
                raise ConnectionError("down")

        monkeypatch.setattr(get_settings(), "token_denylist_backend", "redis")
        monkeypatch.setattr(token_denylist, "_client", lambda: Broken())
        await token_denylist.deny("x", None)
        assert await token_denylist.is_denied("x") is False

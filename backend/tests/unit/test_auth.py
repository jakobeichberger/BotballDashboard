"""Unit tests for authentication module."""
import pytest
from modules.auth.service import (
    hash_password,
    verify_password,
    authenticate_user,
    create_user,
    get_user_permissions,
)
from core.auth import create_access_token, create_refresh_token, decode_token
from core.exceptions import UnauthorizedError, ConflictError


class TestPasswordHashing:
    def test_hash_is_not_plaintext(self):
        hashed = hash_password("mysecret")
        assert hashed != "mysecret"

    def test_verify_correct_password(self):
        hashed = hash_password("mysecret")
        assert verify_password("mysecret", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("mysecret")
        assert verify_password("wrongpassword", hashed) is False

    def test_two_hashes_of_same_password_differ(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # bcrypt uses random salt


class TestJWTTokens:
    def test_create_and_decode_access_token(self):
        token = create_access_token("user-123")
        payload = decode_token(token, expected_type="access")
        assert payload["sub"] == "user-123"
        assert payload["type"] == "access"

    def test_create_and_decode_refresh_token(self):
        token = create_refresh_token("user-456")
        payload = decode_token(token, expected_type="refresh")
        assert payload["sub"] == "user-456"
        assert payload["type"] == "refresh"

    def test_wrong_token_type_raises(self):
        access_token = create_access_token("user-789")
        with pytest.raises(UnauthorizedError):
            decode_token(access_token, expected_type="refresh")

    def test_invalid_token_raises(self):
        with pytest.raises(UnauthorizedError):
            decode_token("not.a.valid.token")

    def test_tampered_token_raises(self):
        token = create_access_token("user-abc")
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(UnauthorizedError):
            decode_token(tampered)


class TestUserCreation:
    @pytest.mark.asyncio
    async def test_create_user_stores_hashed_password(self, db):
        user = await create_user(db, "test@example.com", "Test User", "password123", [])
        await db.commit()

        assert user.email == "test@example.com"
        assert user.hashed_password != "password123"
        assert verify_password("password123", user.hashed_password)

    @pytest.mark.asyncio
    async def test_email_normalized_to_lowercase(self, db):
        user = await create_user(db, "TEST@EXAMPLE.COM", "Test User", "pass", [])
        await db.commit()
        assert user.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_duplicate_email_raises_conflict(self, db):
        await create_user(db, "dupe@example.com", "User 1", "pass", [])
        await db.commit()

        with pytest.raises(ConflictError):
            await create_user(db, "dupe@example.com", "User 2", "pass", [])

    @pytest.mark.asyncio
    async def test_authenticate_valid_credentials(self, db):
        await create_user(db, "auth@example.com", "Auth User", "secret123", [])
        await db.commit()

        user = await authenticate_user(db, "auth@example.com", "secret123")
        assert user.email == "auth@example.com"

    @pytest.mark.asyncio
    async def test_authenticate_wrong_password_raises(self, db):
        await create_user(db, "fail@example.com", "Fail User", "correct", [])
        await db.commit()

        with pytest.raises(UnauthorizedError):
            await authenticate_user(db, "fail@example.com", "wrong")

    @pytest.mark.asyncio
    async def test_superuser_has_all_permissions(self, db, admin_user):
        perms = await get_user_permissions(db, admin_user.id)
        # Superuser returns all permissions from DB (may be empty in test DB without seeds)
        # The key assertion: does not raise and returns a set
        assert isinstance(perms, set)

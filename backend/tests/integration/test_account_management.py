"""Password reset, password policy, access-token revocation, profile settings,
DSGVO export/deletion and editable role permissions."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from modules.auth import routes as auth_routes
from modules.auth.models import (
    PasswordResetToken,
    Permission,
    PushSubscription,
    RefreshToken,
    Role,
    RolePermission,
    User,
)
from modules.auth.password_policy import MIN_LENGTH, common_passwords, password_problem
from modules.auth.service import hash_password
from modules.teams.models import TeamMember

PASSWORD = "password123"


@pytest.fixture
async def user(db):
    u = User(
        email="user@example.com",
        display_name="User",
        hashed_password=hash_password(PASSWORD),
        is_active=True,
    )
    db.add(u)
    await db.commit()
    return u


async def _login(client, email="user@example.com", password=PASSWORD):
    resp = await client.post("/api/auth/login", json={"email": email, "password": password})
    return resp


async def _headers(client, **kwargs):
    resp = await _login(client, **kwargs)
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def sent_mails(monkeypatch):
    mails: list[tuple[str, str]] = []

    async def capture(email, display_name, token, language=None):
        mails.append((email, token))

    monkeypatch.setattr(auth_routes, "send_password_reset_email", capture)
    return mails


class TestPasswordPolicy:
    @pytest.mark.parametrize(
        ("password", "ok"),
        [
            ("short", False),
            ("aaaaaaaaaaaa", False),
            ("user@example.com", False),
            # Common/leaked passwords, compared case-insensitively.
            (PASSWORD, False),
            ("QwertyUiop", False),
            (" 1234567890 ", False),
            ("iloveyou123", False),
            ("a-new-secret-1", True),
            ("Kiwi-Tram-Lantern", True),
        ],
    )
    def test_rules(self, password, ok):
        assert (password_problem(password, "user@example.com") is None) is ok

    def test_common_password_list_is_bundled_and_meaningful(self):
        entries = common_passwords()
        assert len(entries) > 2000
        # Shorter entries could never pass the length rule anyway.
        assert all(len(entry) >= MIN_LENGTH and entry == entry.lower() for entry in entries)
        assert "password123" in entries

    @pytest.mark.parametrize("common", ["Password123", "QWERTYUIOP"])
    async def test_every_password_path_rejects_common_passwords(
        self, client, user, auth_headers, sent_mails, common
    ):
        headers = await _headers(client)
        created = await client.post(
            "/api/auth/users",
            json={"email": "new@example.com", "display_name": "N", "password": common},
            headers=auth_headers,
        )
        changed = await client.post(
            "/api/auth/me/password",
            json={"current_password": PASSWORD, "new_password": common},
            headers=headers,
        )
        admin_set = await client.post(
            f"/api/auth/users/{user.id}/password",
            json={"new_password": common},
            headers=auth_headers,
        )
        await client.post("/api/auth/password-reset/request", json={"email": "user@example.com"})
        reset = await client.post(
            "/api/auth/password-reset/confirm",
            json={"token": sent_mails[0][1], "new_password": common},
        )
        for resp in (created, changed, admin_set, reset):
            assert resp.status_code == 422, resp.text
            assert "common or leaked" in resp.text

    async def test_every_password_path_rejects_passwords_over_72_bytes(
        self, client, user, auth_headers, sent_mails
    ):
        # 50 characters, but 75 bytes: more than bcrypt 5 accepts.
        too_long = "Grüße-äöü-" * 5
        headers = await _headers(client)
        created = await client.post(
            "/api/auth/users",
            json={"email": "new@example.com", "display_name": "N", "password": too_long},
            headers=auth_headers,
        )
        changed = await client.post(
            "/api/auth/me/password",
            json={"current_password": PASSWORD, "new_password": too_long},
            headers=headers,
        )
        admin_set = await client.post(
            f"/api/auth/users/{user.id}/password",
            json={"new_password": too_long},
            headers=auth_headers,
        )
        await client.post("/api/auth/password-reset/request", json={"email": "user@example.com"})
        reset = await client.post(
            "/api/auth/password-reset/confirm",
            json={"token": sent_mails[0][1], "new_password": too_long},
        )
        for resp in (created, changed, admin_set, reset):
            assert resp.status_code == 422, resp.text
            assert "at most 72 bytes" in resp.text

    async def test_long_password_from_bcrypt_4_still_logs_in(self, client, db):
        # bcrypt 4.3.0 hashed only the first 72 of these 86 bytes.
        legacy = (
            "correct horse battery staple – Grüße aus dem Turniersaal, 2025 edition!!" + "x" * 10
        )
        db.add(
            User(
                email="legacy@example.com",
                display_name="Legacy",
                hashed_password="$2b$04$Tl3WvJeUPyput3IUyJnzR.oezRFSZHTFQokzClfYof.FNa351Pise",
                is_active=True,
            )
        )
        await db.commit()
        headers = await _headers(client, email="legacy@example.com", password=legacy)
        # Changing it works with the old password; the new one must fit.
        resp = await client.post(
            "/api/auth/me/password",
            json={"current_password": legacy, "new_password": "a-new-secret-1"},
            headers=headers,
        )
        assert resp.status_code == 204, resp.text
        assert (await _login(client, "legacy@example.com", "a-new-secret-1")).status_code == 200

    async def test_create_user_rejects_email_as_password(self, client, auth_headers):
        resp = await client.post(
            "/api/auth/users",
            json={"email": "same@example.com", "display_name": "S", "password": "same@example.com"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_change_password_policy(self, client, user):
        headers = await _headers(client)
        for bad in ("123456789", "bbbbbbbbbbbb", "USER@example.com"):
            resp = await client.post(
                "/api/auth/me/password",
                json={"current_password": PASSWORD, "new_password": bad},
                headers=headers,
            )
            assert resp.status_code == 422, bad


class TestPasswordReset:
    async def test_full_flow(self, client, db, user, sent_mails):
        old_headers = await _headers(client)
        resp = await client.post(
            "/api/auth/password-reset/request", json={"email": "USER@example.com"}
        )
        assert resp.status_code == 204
        assert len(sent_mails) == 1
        email, token = sent_mails[0]
        assert email == "user@example.com"
        stored = (await db.execute(select(PasswordResetToken))).scalar_one()
        assert stored.token_hash != token  # only the hash is stored

        resp = await client.post(
            "/api/auth/password-reset/confirm",
            json={"token": token, "new_password": "a-new-secret-1"},
        )
        assert resp.status_code == 204, resp.text
        assert (await _login(client, password="a-new-secret-1")).status_code == 200
        assert (await _login(client)).status_code == 401
        # Sessions opened before the reset are gone, access tokens included.
        assert (await client.get("/api/auth/me", headers=old_headers)).status_code == 401
        # Single use.
        again = await client.post(
            "/api/auth/password-reset/confirm",
            json={"token": token, "new_password": "another-secret-2"},
        )
        assert again.status_code == 400

    async def test_unknown_email_is_indistinguishable(self, client, sent_mails):
        resp = await client.post(
            "/api/auth/password-reset/request", json={"email": "nobody@example.com"}
        )
        assert resp.status_code == 204
        assert sent_mails == []

    async def test_resend_is_throttled(self, client, user, sent_mails):
        for _ in range(3):
            resp = await client.post(
                "/api/auth/password-reset/request", json={"email": "user@example.com"}
            )
            assert resp.status_code == 204
        assert len(sent_mails) == 1

    async def test_expired_token_rejected(self, client, db, user, sent_mails):
        await client.post("/api/auth/password-reset/request", json={"email": "user@example.com"})
        stored = (await db.execute(select(PasswordResetToken))).scalar_one()
        stored.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await db.commit()
        resp = await client.post(
            "/api/auth/password-reset/confirm",
            json={"token": sent_mails[0][1], "new_password": "a-new-secret-1"},
        )
        assert resp.status_code == 400

    async def test_reset_enforces_policy(self, client, user, sent_mails):
        await client.post("/api/auth/password-reset/request", json={"email": "user@example.com"})
        resp = await client.post(
            "/api/auth/password-reset/confirm",
            json={"token": sent_mails[0][1], "new_password": "user@example.com"},
        )
        assert resp.status_code == 422


class TestTokenRevocation:
    async def test_password_change_revokes_other_access_tokens(self, client, user):
        headers = await _headers(client)
        resp = await client.post(
            "/api/auth/me/password",
            json={"current_password": PASSWORD, "new_password": "brand-new-pass"},
            headers=headers,
        )
        assert resp.status_code == 204
        assert (await client.get("/api/auth/me", headers=headers)).status_code == 401
        new_headers = await _headers(client, password="brand-new-pass")
        assert (await client.get("/api/auth/me", headers=new_headers)).status_code == 200

    async def test_deactivation_revokes_tokens(self, client, db, user, auth_headers):
        headers = await _headers(client)
        resp = await client.patch(
            f"/api/auth/users/{user.id}", json={"is_active": False}, headers=auth_headers
        )
        assert resp.status_code == 200
        await db.refresh(user)
        assert user.token_version == 1
        assert (await client.get("/api/auth/me", headers=headers)).status_code == 401

    async def test_admin_sets_password(self, client, db, user, auth_headers):
        headers = await _headers(client)
        await db.flush()
        resp = await client.post(
            f"/api/auth/users/{user.id}/password",
            json={"new_password": "set-by-admin-1"},
            headers=auth_headers,
        )
        assert resp.status_code == 204, resp.text
        assert (await client.get("/api/auth/me", headers=headers)).status_code == 401
        assert (await _login(client, password="set-by-admin-1")).status_code == 200
        await db.flush()
        tokens = await db.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))
        assert len(tokens.scalars().all()) == 1  # only the login just now

    async def test_admin_set_password_needs_users_write(self, client, user):
        headers = await _headers(client)
        resp = await client.post(
            f"/api/auth/users/{user.id}/password",
            json={"new_password": "set-by-self-1"},
            headers=headers,
        )
        assert resp.status_code == 403


class TestProfile:
    async def test_theme_and_language_persist(self, client, user):
        headers = await _headers(client)
        resp = await client.patch(
            "/api/auth/me", json={"theme": "dark", "preferred_language": "en"}, headers=headers
        )
        assert resp.status_code == 200
        me = (await client.get("/api/auth/me", headers=headers)).json()
        assert me["theme"] == "dark" and me["preferred_language"] == "en"
        bad = await client.patch("/api/auth/me", json={"theme": "pink"}, headers=headers)
        assert bad.status_code == 422

    async def test_email_change_requires_password(self, client, db, user, auth_headers):
        headers = await _headers(client)
        resp = await client.post(
            "/api/auth/me/email",
            json={"new_email": "new@example.com", "current_password": "wrong-password"},
            headers=headers,
        )
        assert resp.status_code == 400
        resp = await client.post(
            "/api/auth/me/email",
            json={"new_email": "admin@test.com", "current_password": PASSWORD},
            headers=headers,
        )
        assert resp.status_code == 409  # taken by the admin fixture
        resp = await client.post(
            "/api/auth/me/email",
            json={"new_email": "New@Example.com", "current_password": PASSWORD},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == "new@example.com"
        assert (await _login(client, email="new@example.com")).status_code == 200


class TestDsgvo:
    async def test_export_own_data(self, client, db, user, team):
        db.add(TeamMember(team_id=team.id, user_id=user.id, name="User", role="mentor"))
        await db.commit()
        headers = await _headers(client)
        await db.flush()  # the test session is never committed between requests
        resp = await client.get("/api/auth/me/export", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["profile"]["email"] == "user@example.com"
        assert "hashed_password" not in data["profile"]
        assert data["team_memberships"][0]["team_name"] == team.name
        assert data["sessions"] and "token_hash" not in data["sessions"][0]

    async def test_delete_own_account_anonymises(self, client, db, user, team):
        db.add(
            TeamMember(
                team_id=team.id,
                user_id=user.id,
                name="User",
                email="user@example.com",
                role="mentor",
            )
        )
        db.add(PushSubscription(user_id=user.id, endpoint="https://push", p256dh="p", auth="a"))
        await db.commit()
        headers = await _headers(client)
        wrong = await client.request(
            "DELETE", "/api/auth/me", json={"current_password": "nope-nope"}, headers=headers
        )
        assert wrong.status_code == 400
        resp = await client.request(
            "DELETE", "/api/auth/me", json={"current_password": PASSWORD}, headers=headers
        )
        assert resp.status_code == 204
        await db.refresh(user)
        assert user.anonymized_at is not None
        assert user.email.endswith("@deleted.invalid")
        assert user.display_name != "User" and not user.is_active
        assert (await db.execute(select(PushSubscription))).first() is None
        member = (await db.execute(select(TeamMember))).scalar_one()
        assert member.user_id is None and member.email is None
        assert (await client.get("/api/auth/me", headers=headers)).status_code == 401
        assert (await _login(client)).status_code == 401

    async def test_admin_deletes_user(self, client, db, user, admin_user, auth_headers):
        resp = await client.delete(f"/api/auth/users/{user.id}", headers=auth_headers)
        assert resp.status_code == 204
        await db.refresh(user)
        assert user.anonymized_at is not None
        own = await client.delete(f"/api/auth/users/{admin_user.id}", headers=auth_headers)
        assert own.status_code == 409


class TestRolePermissions:
    async def _perms(self, db, *names):
        perms = [Permission(name=n, description=n) for n in names]
        db.add_all(perms)
        await db.flush()
        return perms

    async def test_edit_role_permissions(self, client, db, auth_headers):
        await self._perms(db, "teams:read", "teams:write")
        role = Role(name="helper")
        db.add(role)
        await db.commit()
        resp = await client.put(
            f"/api/auth/roles/{role.id}",
            json={"permission_names": ["teams:read", "teams:write"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert sorted(p["name"] for p in resp.json()["permissions"]) == [
            "teams:read",
            "teams:write",
        ]
        resp = await client.put(
            f"/api/auth/roles/{role.id}",
            json={"permission_names": ["teams:read"]},
            headers=auth_headers,
        )
        assert [p["name"] for p in resp.json()["permissions"]] == ["teams:read"]
        unknown = await client.put(
            f"/api/auth/roles/{role.id}",
            json={"permission_names": ["nope:nope"]},
            headers=auth_headers,
        )
        assert unknown.status_code == 422

    async def test_admin_role_keeps_critical_permissions(self, client, db, auth_headers):
        perms = await self._perms(db, "users:read", "users:write", "roles:read", "roles:write")
        admin = Role(name="admin", is_system=True)
        db.add(admin)
        await db.flush()
        for perm in perms:
            db.add(RolePermission(role_id=admin.id, permission_id=perm.id))
        await db.commit()
        resp = await client.put(
            f"/api/auth/roles/{admin.id}",
            json={"permission_names": ["users:read", "roles:read"]},
            headers=auth_headers,
        )
        assert resp.status_code == 403
        resp = await client.put(
            f"/api/auth/roles/{admin.id}",
            json={"permission_names": [p.name for p in perms]},
            headers=auth_headers,
        )
        assert resp.status_code == 200

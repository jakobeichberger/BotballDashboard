"""Per-user push preferences (spec 09) and the in-app notification center."""

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from core.auth import create_access_token
from core.domain_events import emit_event
from modules.auth.models import PushSubscription, User
from modules.auth.service import hash_password
from modules.dashboard import tasks
from modules.dashboard.models import NotificationEvent
from modules.dashboard.notifications import category_of, normalize_preferences
from modules.dashboard.tasks import push_targets


def _sub(user_id: str):
    return SimpleNamespace(user_id=user_id, endpoint=f"https://push/{user_id}")


async def _user(db, email: str) -> tuple[User, dict]:
    user = User(
        email=email,
        display_name=email,
        hashed_password=hash_password("password123"),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    return user, {"Authorization": f"Bearer {create_access_token(user.id)}"}


class TestCategories:
    def test_event_types_map_to_user_facing_categories(self):
        assert category_of("paper_status_changed") == "paper_status"
        assert category_of("print_status_changed") == "print_status"
        assert category_of("announcement_published") == "announcements"
        assert category_of("review_reminder") == "deadlines"
        assert category_of("schedule_updated") == "match_soon"
        assert category_of("match_starting_soon") == "match_soon"
        assert category_of("paper_deadline_reminder") == "deadlines"
        assert category_of("something_internal") is None
        assert category_of("custom", {"category": "score_corrected"}) == "score_corrected"

    def test_missing_preferences_default_to_on(self):
        prefs = normalize_preferences({"print_status": False})
        assert prefs["print_status"] is False
        assert all(value for key, value in prefs.items() if key != "print_status")


class TestPushTargetsHonourPreferences:
    def test_muted_category_skips_the_user(self):
        subs = [_sub("a"), _sub("b")]
        payload = {"userIds": ["a", "b"]}
        prefs = {"a": {"paper_status": False}}
        targets = push_targets(payload, subs, event_type="paper_status_changed", preferences=prefs)
        assert [s.user_id for s in targets] == ["b"]

    def test_broadcast_respects_opt_outs(self):
        subs = [_sub("a"), _sub("b")]
        prefs = {"b": {"announcements": False}}
        targets = push_targets(
            {"broadcast": True}, subs, event_type="announcement_published", preferences=prefs
        )
        assert [s.user_id for s in targets] == ["a"]

    def test_other_categories_are_unaffected(self):
        subs = [_sub("a")]
        prefs = {"a": {"paper_status": False}}
        targets = push_targets(
            {"userId": "a"}, subs, event_type="print_status_changed", preferences=prefs
        )
        assert [s.user_id for s in targets] == ["a"]

    def test_legacy_call_without_preferences(self):
        assert [s.user_id for s in push_targets({"userId": "a"}, [_sub("a"), _sub("b")])] == ["a"]


class TestOutboxDeliveryHonoursPreferences:
    """Preferences apply inside the outbox worker (deliver_pending/_deliver)."""

    @pytest.mark.asyncio
    async def test_deliver_pending_skips_muted_recipients(self, db, monkeypatch):
        calls: list[str] = []

        async def fake_send(endpoint, p256dh, auth, title, body, url=None):
            calls.append(endpoint)
            return "sent"

        monkeypatch.setattr(tasks, "send_push_notification", fake_send)
        muted, _ = await _user(db, "muted@test.com")
        listening, _ = await _user(db, "listening@test.com")
        muted.notification_preferences = {"match_soon": False}
        for user in (muted, listening):
            db.add(
                PushSubscription(
                    user_id=user.id, endpoint=f"https://push/{user.email}", p256dh="k", auth="a"
                )
            )
        await emit_event(
            db,
            "match_starting_soon",
            payload={"message": "Table 2 in 10 min", "userIds": [muted.id, listening.id]},
        )
        await db.commit()

        assert await tasks.deliver_pending(db) == 1
        assert calls == ["https://push/listening@test.com"]
        item = (await db.execute(select(NotificationEvent))).scalar_one()
        assert item.status == "delivered"

    @pytest.mark.asyncio
    async def test_fully_muted_item_counts_as_delivered(self, db, monkeypatch):
        async def fake_send(*_args, **_kwargs):
            raise AssertionError("muted users must not be pushed")

        monkeypatch.setattr(tasks, "send_push_notification", fake_send)
        user, _ = await _user(db, "quiet@test.com")
        user.notification_preferences = {"deadlines": False}
        db.add(PushSubscription(user_id=user.id, endpoint="https://push/q", p256dh="k", auth="a"))
        await emit_event(
            db, "paper_deadline_reminder", payload={"message": "3 days", "userId": user.id}
        )
        await db.commit()
        # No recipient left is not a failure: nothing to retry.
        assert await tasks.deliver_pending(db) == 1


class TestPreferencesApi:
    @pytest.mark.asyncio
    async def test_defaults_and_partial_update(self, client, db):
        user, headers = await _user(db, "prefs@test.com")
        resp = await client.get("/api/auth/me/notification-preferences", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == {
            "match_soon": True,
            "score_corrected": True,
            "deadlines": True,
            "paper_status": True,
            "print_status": True,
            "announcements": True,
        }

        resp = await client.put(
            "/api/auth/me/notification-preferences",
            headers=headers,
            json={"print_status": False, "deadlines": False},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["print_status"] is False
        assert resp.json()["match_soon"] is True

        await db.refresh(user)
        assert user.notification_preferences["print_status"] is False
        resp = await client.get("/api/auth/me/notification-preferences", headers=headers)
        assert resp.json()["deadlines"] is False

    @pytest.mark.asyncio
    async def test_requires_login(self, client):
        assert (await client.get("/api/auth/me/notification-preferences")).status_code == 401


class TestNotificationCenter:
    @pytest.mark.asyncio
    async def test_lists_only_own_and_broadcast_notifications(self, client, db):
        me, headers = await _user(db, "me@test.com")
        other, _ = await _user(db, "other@test.com")
        await emit_event(db, "print_status_changed", payload={"userId": me.id, "message": "Mine"})
        await emit_event(
            db, "paper_status_changed", payload={"userIds": [other.id], "message": "X"}
        )
        await emit_event(
            db,
            "announcement_published",
            payload={"broadcast": True, "title": "Hello", "body": "All"},
        )
        await db.commit()

        resp = await client.get("/api/dashboard/notifications", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["unread"] == 2
        assert sorted(item["body"] for item in body["items"]) == ["All", "Mine"]
        assert {item["category"] for item in body["items"]} == {"print_status", "announcements"}
        assert not any(item["read"] for item in body["items"])

    @pytest.mark.asyncio
    async def test_mark_read_and_read_all(self, client, db):
        me, headers = await _user(db, "reader@test.com")
        other, _ = await _user(db, "stranger@test.com")
        first = await emit_event(
            db, "print_status_changed", payload={"userId": me.id, "message": "1"}
        )
        await emit_event(db, "print_status_changed", payload={"userId": me.id, "message": "2"})
        foreign = await emit_event(
            db, "print_status_changed", payload={"userId": other.id, "message": "x"}
        )
        await db.commit()

        resp = await client.post(
            "/api/dashboard/notifications/read",
            headers=headers,
            json={"ids": [first.id, foreign.id]},
        )
        # Someone else's notification cannot be marked.
        assert resp.json() == {"marked": 1}
        body = (await client.get("/api/dashboard/notifications", headers=headers)).json()
        assert body["unread"] == 1
        assert {item["body"]: item["read"] for item in body["items"]} == {"1": True, "2": False}

        unread_only = await client.get(
            "/api/dashboard/notifications?unread_only=true", headers=headers
        )
        assert [item["body"] for item in unread_only.json()["items"]] == ["2"]

        assert (
            await client.post("/api/dashboard/notifications/read-all", headers=headers)
        ).json() == {"marked": 1}
        assert (await client.get("/api/dashboard/notifications", headers=headers)).json()[
            "unread"
        ] == 0

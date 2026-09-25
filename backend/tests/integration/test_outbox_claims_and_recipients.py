"""Outbox delivery without locks held during sends; the notification center index."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

import modules.dashboard.tasks as tasks
from core.domain_events import emit_event
from modules.auth.models import PushSubscription, User
from modules.dashboard import notifications as notification_center
from modules.dashboard.models import NotificationEvent, NotificationRead, NotificationRecipient


async def _user(db, email: str) -> User:
    user = User(email=email, display_name=email, hashed_password="x", is_active=True)
    db.add(user)
    await db.flush()
    return user


async def _subscribe(db, user: User, endpoint: str) -> PushSubscription:
    subscription = PushSubscription(user_id=user.id, endpoint=endpoint, p256dh="k", auth="a")
    db.add(subscription)
    await db.flush()
    return subscription


@pytest.fixture
def sent(monkeypatch):
    calls: list[str] = []

    async def fake_send(endpoint, p256dh, auth, title, body, url=None):
        calls.append(endpoint)
        return "sent"

    monkeypatch.setattr(tasks, "send_push_notification", fake_send)
    return calls


# ── Claim, lease, sends outside the transaction ───────────────────────────────


@pytest.mark.asyncio
async def test_sends_happen_outside_any_transaction(db, monkeypatch):
    user = await _user(db, "tx@example.com")
    await _subscribe(db, user, "https://push/tx")
    await emit_event(db, "test", payload={"message": "hi", "userId": user.id})
    await db.commit()
    seen: list[tuple[str, bool]] = []

    async def fake_send(endpoint, p256dh, auth, title, body, url=None):
        seen.append((endpoint, db.in_transaction()))
        # Claimed rows are committed as "sending" before any send.
        async with tasks_session(db) as other:
            status = (await other.execute(select(NotificationEvent.status))).scalar_one()
            assert status == "sending"
        return "sent"

    monkeypatch.setattr(tasks, "send_push_notification", fake_send)
    assert await tasks.deliver_pending(db) == 1
    assert seen == [("https://push/tx", False)]
    item = (await db.execute(select(NotificationEvent))).scalar_one()
    assert item.status == "delivered" and item.next_attempt_at is None


def tasks_session(db):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    return async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)()


@pytest.mark.asyncio
async def test_claimed_rows_are_skipped_until_the_lease_ends(db, sent):
    user = await _user(db, "lease@example.com")
    await _subscribe(db, user, "https://push/lease")
    await emit_event(db, "test", payload={"message": "hi", "userId": user.id})
    await db.commit()

    now = datetime.now(UTC)
    claimed = await tasks.claim_batch(db, now)
    assert [item.status for item in claimed] == ["sending"]
    assert claimed[0].attempts == 1

    # Another worker right now finds nothing to do …
    assert await tasks.deliver_pending(db, now + timedelta(seconds=1)) == 0
    assert sent == []
    # … but a claim whose worker died is delivered once the lease is over.
    later = now + tasks.CLAIM_LEASE + timedelta(seconds=1)
    assert await tasks.deliver_pending(db, later) == 1
    assert sent == ["https://push/lease"]
    item = (await db.execute(select(NotificationEvent))).scalar_one()
    assert item.status == "delivered" and item.attempts == 2


@pytest.mark.asyncio
async def test_only_the_recipients_subscriptions_are_loaded(db, sent):
    alice = await _user(db, "alice@example.com")
    bob = await _user(db, "bob@example.com")
    await _subscribe(db, alice, "https://push/alice")
    await _subscribe(db, bob, "https://push/bob")
    await emit_event(db, "test", payload={"message": "hi", "userId": alice.id})
    await db.commit()
    items = list((await db.execute(select(NotificationEvent))).scalars())
    loaded = await tasks._load_subscriptions(db, items)
    assert [s.endpoint for s in loaded] == ["https://push/alice"]

    await emit_event(db, "test", payload={"message": "all", "broadcast": True})
    await db.commit()
    items = list((await db.execute(select(NotificationEvent))).scalars())
    assert len(await tasks._load_subscriptions(db, items)) == 2

    assert await tasks.deliver_pending(db) == 2
    assert sorted(sent) == ["https://push/alice", "https://push/alice", "https://push/bob"]


@pytest.mark.asyncio
async def test_localized_mail_languages_are_loaded_before_sending(db, monkeypatch):
    english = await _user(db, "en@example.com")
    english.preferred_language = "en"
    mails: list[tuple[list[str], str]] = []

    async def fake_email(to, subject, html_body, text_body=None):
        mails.append((list(to), subject))
        return True

    monkeypatch.setattr(tasks, "send_email", fake_email)
    monkeypatch.setattr(tasks, "email_enabled", lambda: True)
    payload = {
        "i18n": {
            "template": "deadline_reminder",
            "params": {"title": "Paper", "due": "2026-10-01", "days": 3},
        },
        "emails": ["de@example.com", "en@example.com"],
    }
    await emit_event(db, "deadline_reminder", payload=payload)
    await db.commit()
    assert await tasks.deliver_pending(db) == 1
    # One mail per language: the account's language, else the default (German).
    assert sorted(mails) == [
        (["de@example.com"], "Deadline in 3 Tagen: Paper"),
        (["en@example.com"], "Deadline in 3 days: Paper"),
    ]


# ── Outbox cleanup ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cleanup_removes_old_finished_rows_with_their_recipients(db):
    user = await _user(db, "old@example.com")
    now = datetime.now(UTC)
    old = await emit_event(db, "test", payload={"message": "old", "userId": user.id})
    old_failed = await emit_event(db, "test", payload={"message": "fail", "userId": user.id})
    pending = await emit_event(db, "test", payload={"message": "wait", "userId": user.id})
    recent = await emit_event(db, "test", payload={"message": "new", "userId": user.id})
    assert old and old_failed and pending and recent
    long_ago = now - tasks.OUTBOX_RETENTION - timedelta(days=1)
    old.status, old.created_at = "delivered", long_ago
    old_failed.status, old_failed.created_at = "failed", long_ago
    pending.created_at = long_ago  # never delivered: kept
    recent.status = "delivered"
    db.add(NotificationRead(user_id=user.id, notification_id=old.id, read_at=now))
    await db.commit()

    assert await tasks.cleanup_outbox(db, now) == 2
    remaining = set((await db.execute(select(NotificationEvent.id))).scalars())
    assert remaining == {pending.id, recent.id}
    recipient_rows = set(
        (await db.execute(select(NotificationRecipient.notification_id))).scalars()
    )
    assert recipient_rows == {pending.id, recent.id}
    assert (await db.execute(select(NotificationRead))).scalars().all() == []


# ── Recipient index / notification center ─────────────────────────────────────


@pytest.mark.asyncio
async def test_emit_event_records_recipients(db):
    alice = await _user(db, "r-alice@example.com")
    bob = await _user(db, "r-bob@example.com")
    direct = await emit_event(
        db,
        "test",
        payload={"message": "x", "userIds": [alice.id, "no-such-user"], "userId": bob.id},
    )
    everyone = await emit_event(db, "test", payload={"message": "y", "broadcast": True})
    nobody = await emit_event(db, "test", payload={"message": "z"})
    assert direct and everyone and nobody
    rows = (await db.execute(select(NotificationRecipient))).scalars().all()
    by_notification: dict[str, set] = {}
    for row in rows:
        by_notification.setdefault(row.notification_id, set()).add(row.user_id)
    # Unknown ids are skipped instead of failing the write.
    assert by_notification[direct.id] == {alice.id, bob.id}
    assert by_notification[everyone.id] == {None}
    assert nobody.id not in by_notification


@pytest.mark.asyncio
async def test_center_finds_a_users_notifications_behind_many_newer_ones(db):
    """The center scanned only the newest 500 outbox rows; older own ones vanished."""
    me = await _user(db, "me@example.com")
    other = await _user(db, "other@example.com")
    mine = await emit_event(db, "test", payload={"title": "Mine", "userId": me.id})
    assert mine is not None
    mine.created_at = datetime.now(UTC) - timedelta(hours=1)
    for i in range(520):
        await emit_event(db, "test", payload={"title": f"n{i}", "userId": other.id})
    announcement = await emit_event(db, "test", payload={"title": "All", "broadcast": True})
    await db.commit()

    items, unread = await notification_center.list_for_user(db, me.id)
    assert [item["title"] for item in items] == ["All", "Mine"]
    assert unread == 2
    assert await notification_center.mark_read(db, me.id, [mine.id]) == 1
    # Not addressed to me: ignored.
    stranger = (
        (
            await db.execute(
                select(NotificationRecipient).where(NotificationRecipient.user_id == other.id)
            )
        )
        .scalars()
        .first()
    )
    assert stranger is not None
    assert await notification_center.mark_read(db, me.id, [stranger.notification_id]) == 0
    items, unread = await notification_center.list_for_user(db, me.id, unread_only=True)
    assert [item["id"] for item in items] == [announcement.id] and unread == 1
    assert await notification_center.mark_all_read(db, me.id) == 1
    assert (await notification_center.list_for_user(db, me.id))[1] == 0

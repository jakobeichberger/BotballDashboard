"""After-commit live events, outbox delivery and schedule/deadline notifications."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

import core.live as live
import modules.dashboard.tasks as tasks
from core.domain_events import emit_event
from modules.auth.models import PushSubscription, User
from modules.dashboard.models import NotificationEvent
from modules.events.models import EventPhase, EventRegistration, MatchParticipant, ScheduledMatch
from modules.events.notifications import queue_deadline_reminders, queue_match_reminders
from modules.seasons.models import SeasonEvent
from modules.teams.models import Team, TeamMember, TeamSeasonRegistration


@pytest.fixture
def published(monkeypatch):
    sent: list[tuple[str, str, dict]] = []

    async def fake_publish(event_id, event, payload=None):
        sent.append((event_id, event, payload or {}))
        return True

    monkeypatch.setattr(live, "publish_live_event", fake_publish)
    return sent


async def _member(db, team: Team, email: str) -> User:
    user = User(email=email, display_name=email, hashed_password="x", is_active=True)
    db.add(user)
    await db.flush()
    db.add(TeamMember(team_id=team.id, user_id=user.id, name=email, email=email))
    await db.flush()
    return user


# ── Live events after commit ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_live_events_are_published_only_after_commit(db, event, published):
    live.publish_after_commit(db, event.id, "ranking_updated")
    live.publish_after_commit(db, event.id, "ranking_updated")  # deduplicated
    await db.flush()
    await live.drain_pending_publishes()
    assert published == []
    await db.commit()
    await live.drain_pending_publishes()
    assert published == [(event.id, "ranking_updated", {})]


@pytest.mark.asyncio
async def test_live_events_are_dropped_on_rollback(db, event, published):
    live.publish_after_commit(db, event.id, "schedule_updated")
    await db.rollback()
    await db.commit()
    await live.drain_pending_publishes()
    assert published == []


@pytest.mark.asyncio
async def test_score_entry_publishes_ranking_after_commit(
    client, auth_headers, event, team, db, published
):
    db.add(EventRegistration(event_id=event.id, team_id=team.id))
    await db.commit()
    await live.drain_pending_publishes()
    published.clear()
    response = await client.post(
        f"/api/v1/events/{event.id}/matches",
        headers=auth_headers,
        json={"team_id": team.id, "idempotency_key": "live-after-commit-1"},
    )
    assert response.status_code == 201
    await live.drain_pending_publishes()
    assert published == []  # the request's transaction is still open
    await db.commit()
    await live.drain_pending_publishes()
    assert [item[1] for item in published] == ["ranking_updated"]


@pytest.mark.asyncio
async def test_announcements_update_the_public_stream(client, auth_headers, event, db, published):
    created = await client.post(
        "/api/dashboard/announcements",
        headers=auth_headers,
        json={"event_id": event.id, "title": "Lunch", "body": "Lunch at noon"},
    )
    ann_id = created.json()["id"]
    await client.put(f"/api/dashboard/announcements/{ann_id}/publish", headers=auth_headers)
    await db.commit()
    await live.drain_pending_publishes()
    assert [item[1] for item in published] == ["announcement_published"]
    outbox = (await db.execute(select(NotificationEvent))).scalars().all()
    # The outbox row carries the push; the live update is not sent twice.
    assert [row.payload.get("publicLive") for row in outbox] == [None]

    published.clear()
    response = await client.put(
        f"/api/dashboard/announcements/{ann_id}/unpublish", headers=auth_headers
    )
    assert response.status_code == 200 and response.json()["is_published"] is False
    await db.commit()
    await live.drain_pending_publishes()
    assert [item[1] for item in published] == ["announcement_removed"]
    response = await client.delete(f"/api/dashboard/announcements/{ann_id}", headers=auth_headers)
    assert response.status_code == 204


# ── Outbox delivery ───────────────────────────────────────────────────────────


@pytest.fixture
def push_results(monkeypatch):
    """Map endpoint → push status for the fake push sender."""
    results: dict[str, str] = {}
    calls: list[str] = []

    async def fake_send(endpoint, p256dh, auth, title, body, url=None):
        calls.append(endpoint)
        return results.get(endpoint, "sent")

    monkeypatch.setattr(tasks, "send_push_notification", fake_send)
    return results, calls


async def _subscribe(db, user: User, endpoint: str) -> PushSubscription:
    subscription = PushSubscription(user_id=user.id, endpoint=endpoint, p256dh="k", auth="a")
    db.add(subscription)
    await db.flush()
    return subscription


@pytest.mark.asyncio
async def test_outbox_marks_delivered_when_one_push_succeeds_and_prunes_gone(
    db, team, push_results
):
    results, _ = push_results
    user = await _member(db, team, "a@example.com")
    await _subscribe(db, user, "https://push/ok")
    await _subscribe(db, user, "https://push/gone")
    results["https://push/gone"] = "gone"
    await emit_event(db, "test", payload={"message": "hi", "userIds": [user.id]})
    await db.commit()

    assert await tasks.deliver_pending(db) == 1
    item = (await db.execute(select(NotificationEvent))).scalar_one()
    assert item.status == "delivered" and item.attempts == 1
    endpoints = (await db.execute(select(PushSubscription.endpoint))).scalars().all()
    assert endpoints == ["https://push/ok"]


@pytest.mark.asyncio
async def test_outbox_retries_failed_pushes_with_backoff(db, team, push_results):
    results, calls = push_results
    user = await _member(db, team, "b@example.com")
    await _subscribe(db, user, "https://push/down")
    results["https://push/down"] = "failed"
    await emit_event(db, "test", payload={"message": "hi", "userId": user.id})
    await db.commit()

    now = datetime.now(UTC)
    assert await tasks.deliver_pending(db, now) == 0
    item = (await db.execute(select(NotificationEvent))).scalar_one()
    assert item.status == "pending" and item.attempts == 1 and item.last_error
    assert item.next_attempt_at is not None

    # Not due yet: nothing is sent.
    await tasks.deliver_pending(db, now + timedelta(seconds=1))
    assert len(calls) == 1
    for attempt in range(2, tasks.MAX_ATTEMPTS + 1):
        now += timedelta(hours=1)
        await tasks.deliver_pending(db, now)
        await db.refresh(item)
        assert item.attempts == attempt
    assert item.status == "failed"


@pytest.mark.asyncio
async def test_outbox_without_recipients_or_push_is_delivered(db, team, push_results):
    results, _ = push_results
    user = await _member(db, team, "c@example.com")
    await _subscribe(db, user, "https://push/novapid")
    results["https://push/novapid"] = "disabled"
    await emit_event(db, "nobody", payload={"message": "internal"})
    await emit_event(db, "novapid", payload={"message": "hi", "userId": user.id})
    await db.commit()
    assert await tasks.deliver_pending(db) == 2


@pytest.mark.asyncio
async def test_outbox_query_locks_rows_on_postgres():
    from sqlalchemy.dialects import postgresql, sqlite

    statement = (
        select(NotificationEvent)
        .where(NotificationEvent.status == "pending")
        .with_for_update(skip_locked=True)
    )
    assert "FOR UPDATE SKIP LOCKED" in str(statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" not in str(statement.compile(dialect=sqlite.dialect()))


@pytest.mark.asyncio
async def test_emit_event_dedupe_key(db):
    assert await emit_event(db, "x", dedupe_key="once") is not None
    assert await emit_event(db, "x", dedupe_key="once") is None
    assert len((await db.execute(select(NotificationEvent))).scalars().all()) == 1


ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc"


@pytest.mark.asyncio
async def test_send_push_notification_reports_expired_subscriptions(monkeypatch):
    import pywebpush

    import core.notifications as notifications

    class Response:
        status_code = 410

    def gone(**_kwargs):
        raise pywebpush.WebPushException("gone", response=Response())

    monkeypatch.setattr(notifications.settings, "vapid_private_key", "key")
    monkeypatch.setattr(pywebpush, "webpush", gone)
    assert await notifications.send_push_notification(ENDPOINT, "p", "a", "t", "b") == "gone"

    def broken(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(pywebpush, "webpush", broken)
    assert await notifications.send_push_notification(ENDPOINT, "p", "a", "t", "b") == "failed"
    monkeypatch.setattr(pywebpush, "webpush", lambda **_kwargs: None)
    assert await notifications.send_push_notification(ENDPOINT, "p", "a", "t", "b") == "sent"
    monkeypatch.setattr(notifications.settings, "vapid_private_key", "")
    assert await notifications.send_push_notification(ENDPOINT, "p", "a", "t", "b") == "disabled"


@pytest.mark.asyncio
async def test_outbox_sends_emails_when_configured(db, monkeypatch):
    sent: list[list[str]] = []

    async def fake_email(to, subject, html_body, text_body=None):
        sent.append(list(to))
        return True

    monkeypatch.setattr(tasks, "send_email", fake_email)
    monkeypatch.setattr(tasks, "email_enabled", lambda: True)
    await emit_event(db, "deadline_reminder", payload={"message": "due", "emails": ["m@x.org"]})
    await db.commit()
    assert await tasks.deliver_pending(db) == 1
    assert sent == [["m@x.org"]]


# ── Reminders and corrections ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_match_reminder_is_queued_once_for_the_teams(db, event, team):
    user = await _member(db, team, "player@example.com")
    other = Team(name="Other", team_number="OT")
    db.add(other)
    await db.flush()
    stranger = await _member(db, other, "stranger@example.com")
    phase = EventPhase(event_id=event.id, name="Seeding", phase_type="seeding", sort_order=0)
    db.add(phase)
    await db.flush()
    now = datetime.now(UTC)
    soon = ScheduledMatch(
        event_id=event.id,
        phase_id=phase.id,
        code="1-S1",
        sequence_number=1,
        table_number=2,
        scheduled_at=now + timedelta(minutes=8),
    )
    later = ScheduledMatch(
        event_id=event.id,
        phase_id=phase.id,
        code="1-S2",
        sequence_number=2,
        scheduled_at=now + timedelta(minutes=40),
    )
    db.add_all([soon, later])
    await db.flush()
    db.add(MatchParticipant(scheduled_match_id=soon.id, team_id=team.id, position=1))
    db.add(MatchParticipant(scheduled_match_id=later.id, team_id=other.id, position=1))
    await db.commit()

    assert await queue_match_reminders(db, now) == 1
    assert await queue_match_reminders(db, now + timedelta(minutes=1)) == 0
    [item] = (await db.execute(select(NotificationEvent))).scalars().all()
    assert item.event_type == "match_starting_soon"
    assert item.payload["userIds"] == [user.id]
    assert stranger.id not in item.payload["userIds"]
    assert "table 2" in item.payload["message"]


@pytest.mark.asyncio
async def test_deadline_reminders_7_3_1_days(db, season, team):
    user = await _member(db, team, "mentor@example.com")
    db.add(TeamSeasonRegistration(team_id=team.id, season_id=season.id))
    today = date(2026, 9, 24)
    for days in (7, 3, 1, 5):
        db.add(
            SeasonEvent(
                season_id=season.id,
                title=f"Paper in {days}",
                event_type="deadline",
                event_date=today + timedelta(days=days),
            )
        )
    db.add(
        SeasonEvent(
            season_id=season.id,
            title="Kickoff",
            event_type="event",
            event_date=today + timedelta(days=7),
        )
    )
    await db.commit()

    assert await queue_deadline_reminders(db, today) == 3
    assert await queue_deadline_reminders(db, today) == 0  # same day again: nothing
    items = (await db.execute(select(NotificationEvent))).scalars().all()
    titles = sorted(item.payload["title"] for item in items)
    assert titles == [
        "Deadline in 3 days: Paper in 3",
        "Deadline in 7 days: Paper in 7",
        "Deadline tomorrow: Paper in 1",
    ]
    assert all(item.payload["userIds"] == [user.id] for item in items)
    assert all(item.payload["emails"] == ["mentor@example.com"] for item in items)


@pytest.mark.asyncio
async def test_score_correction_notifies_the_team(client, auth_headers, event, team, db):
    user = await _member(db, team, "corrected@example.com")
    db.add(EventRegistration(event_id=event.id, team_id=team.id))
    await db.commit()
    created = await client.post(
        f"/api/v1/events/{event.id}/matches",
        headers=auth_headers,
        json={"team_id": team.id, "idempotency_key": "correction-1"},
    )
    match_id = created.json()["id"]
    unchanged = await client.patch(
        f"/api/scoring/matches/{match_id}", headers=auth_headers, json={"is_disqualified": False}
    )
    assert unchanged.status_code == 200
    assert (await db.execute(select(NotificationEvent))).scalars().all() == []
    response = await client.patch(
        f"/api/scoring/matches/{match_id}",
        headers=auth_headers,
        json={"is_disqualified": True, "correction_reason": "robot left the table"},
    )
    assert response.status_code == 200, response.text
    [item] = (await db.execute(select(NotificationEvent))).scalars().all()
    assert item.event_type == "score_corrected"
    assert item.payload["userIds"] == [user.id]

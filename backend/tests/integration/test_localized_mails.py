"""E-mails (and templated notifications) go out in the recipient's language."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

import core.notifications as notifications
import modules.auth.routes as auth_routes
import modules.dashboard.tasks as tasks
from modules.auth.models import PushSubscription, User
from modules.dashboard import notifications as notification_center
from modules.dashboard.models import NotificationEvent
from modules.events.notifications import queue_deadline_reminders
from modules.seasons.models import SeasonEvent
from modules.teams.models import TeamMember, TeamSeasonRegistration


@pytest.fixture
def mails(monkeypatch):
    """Capture every e-mail (core.notifications.send_email and the worker's copy)."""
    sent: list[dict] = []

    async def fake_send(to, subject, html_body, text_body=None):
        sent.append(
            {
                "to": [to] if isinstance(to, str) else list(to),
                "subject": subject,
                "html": html_body,
                "text": text_body,
            }
        )
        return True

    monkeypatch.setattr(notifications, "send_email", fake_send)
    monkeypatch.setattr(tasks, "send_email", fake_send)
    return sent


async def _user(db, email: str, language: str) -> User:
    user = User(
        email=email,
        display_name=email.split("@")[0],
        hashed_password="x",
        is_active=True,
        preferred_language=language,
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "subject", "greeting"),
    [
        ("de", "BotballDashboard: Passwort zurücksetzen", "Hallo Ada,"),
        ("en", "BotballDashboard: reset your password", "Hello Ada,"),
    ],
)
async def test_password_reset_mail_uses_the_user_language(
    monkeypatch, mails, language, subject, greeting
):
    monkeypatch.setattr(auth_routes, "_mail_enabled", lambda: True)
    await auth_routes.send_password_reset_email("ada@example.org", "Ada", "tok en", language)
    [mail] = mails
    assert mail["to"] == ["ada@example.org"]
    assert mail["subject"] == subject
    assert greeting in mail["text"]
    assert "reset-password?token=tok%20en" in mail["text"]


@pytest.mark.asyncio
async def test_password_reset_request_passes_the_profile_language(client, db, monkeypatch):
    user = await _user(db, "reset@example.org", "en")
    await db.commit()
    calls = []

    async def capture(email, display_name, token, language=None):
        calls.append((email, language))

    monkeypatch.setattr(auth_routes, "send_password_reset_email", capture)
    response = await client.post("/api/auth/password-reset/request", json={"email": user.email})
    assert response.status_code == 204
    assert calls == [("reset@example.org", "en")]


@pytest.mark.asyncio
async def test_account_creation_mail_is_localized(client, auth_headers, monkeypatch, mails):
    monkeypatch.setattr(auth_routes, "_mail_enabled", lambda: True)
    response = await client.post(
        "/api/auth/users",
        json={"email": "new@example.org", "display_name": "Neu", "password": "correct-horse-1"},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    [mail] = mails
    # New accounts start in German (User.preferred_language default).
    assert mail["subject"] == "Dein BotballDashboard-Konto wurde angelegt"
    assert "new@example.org" in mail["text"] and "/login" in mail["text"]

    mails.clear()
    await auth_routes.send_account_created_email("en@example.org", "En", "en")
    assert mails[0]["subject"] == "Your BotballDashboard account was created"


@pytest.mark.asyncio
async def test_deadline_reminder_is_mailed_and_pushed_per_language(
    db, season, team, monkeypatch, mails
):
    german = await _user(db, "de@example.org", "de")
    english = await _user(db, "en@example.org", "en")
    db.add_all(
        [
            TeamMember(team_id=team.id, user_id=german.id, name="De", email="de@example.org"),
            # The member entry has its own address; the language comes from the account.
            TeamMember(
                team_id=team.id, user_id=english.id, name="En", email="en.member@example.org"
            ),
            TeamMember(team_id=team.id, name="Guest", email="guest@example.org"),
            TeamSeasonRegistration(team_id=team.id, season_id=season.id),
            PushSubscription(user_id=english.id, endpoint="https://push/en", p256dh="k", auth="a"),
        ]
    )
    today = date(2026, 9, 24)
    db.add(
        SeasonEvent(
            season_id=season.id,
            title="Paper",
            event_type="deadline",
            event_date=today + timedelta(days=1),
            description="Upload the PDF",
        )
    )
    await db.commit()
    pushes: list[tuple[str, str]] = []

    async def fake_push(endpoint, p256dh, auth, title, body, url=None):
        pushes.append((title, body))
        return "sent"

    monkeypatch.setattr(tasks, "send_push_notification", fake_push)
    monkeypatch.setattr(tasks, "email_enabled", lambda: True)

    assert await queue_deadline_reminders(db, today) == 1
    assert await tasks.deliver_pending(db) == 1

    by_subject = {mail["subject"]: sorted(mail["to"]) for mail in mails}
    assert by_subject == {
        # Addresses without an account get the default language (German).
        "Deadline morgen: Paper": ["de@example.org", "guest@example.org"],
        "Deadline tomorrow: Paper": ["en.member@example.org"],
    }
    german_mail = next(mail for mail in mails if mail["subject"] == "Deadline morgen: Paper")
    assert "Paper ist morgen fällig (25. September 2026)." in german_mail["text"]
    assert "Upload the PDF" in german_mail["text"]
    assert pushes == [
        ("Deadline tomorrow: Paper", "Paper is due tomorrow (25 September 2026).\n\nUpload the PDF")
    ]

    # The in-app notification center renders the same item per reader.
    item = (await db.execute(select(NotificationEvent))).scalar_one()
    assert item.payload["title"] == "Deadline tomorrow: Paper"  # untranslated fallback
    items, _ = await notification_center.list_for_user(db, german.id, language="de")
    assert items[0]["title"] == "Deadline morgen: Paper"
    items, _ = await notification_center.list_for_user(db, english.id, language="en")
    assert items[0]["title"] == "Deadline tomorrow: Paper"


@pytest.mark.asyncio
async def test_plain_notifications_keep_their_text(db, team, monkeypatch, mails):
    """Payloads without a template are mailed as before (one mail, stored text)."""
    from core.domain_events import emit_event

    monkeypatch.setattr(tasks, "email_enabled", lambda: True)
    await emit_event(
        db, "custom", payload={"title": "Hi", "message": "Body", "emails": ["x@example.org"]}
    )
    await db.commit()
    assert await tasks.deliver_pending(db) == 1
    assert [(mail["subject"], mail["to"]) for mail in mails] == [("Hi", ["x@example.org"])]

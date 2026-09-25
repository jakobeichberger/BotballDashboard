"""Localized e-mail/notification templates (core.mail_templates)."""

from datetime import date

import pytest

from core.mail_templates import (
    TEMPLATES,
    format_date,
    i18n_payload,
    normalize_language,
    render,
    render_notification,
)

PARAMS = {
    "account_created": {
        "display_name": "Ada",
        "email": "ada@example.org",
        "login_url": "https://botball.example/login",
    },
    "password_reset": {"display_name": "Ada", "link": "https://botball.example/reset?token=x"},
    "deadline_reminder": {"title": "Paper", "due": "2026-09-25", "days": 3, "description": None},
    "paper_deadline_reminder": {
        "kind": "submission",
        "deadline_type": "official_submission",
        "due": "2026-09-25",
        "days": 1,
    },
}


@pytest.mark.parametrize(
    ("value", "expected"),
    [("de", "de"), ("en", "en"), ("de-AT", "de"), ("EN_gb", "en"), ("fr", "de"), (None, "de")],
)
def test_normalize_language(value, expected):
    assert normalize_language(value) == expected


def test_format_date_per_language():
    assert format_date(date(2026, 3, 5), "de") == "5. März 2026"
    assert format_date("2026-03-05", "en") == "5 March 2026"


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_every_template_exists_in_both_languages(template):
    assert set(TEMPLATES[template]) == {"de", "en"}
    german = render(template, "de", **PARAMS[template])
    english = render(template, "en", **PARAMS[template])
    assert german.subject and english.subject and german.subject != english.subject
    assert german.text != english.text


def test_unknown_language_falls_back_to_english():
    assert render("password_reset", "fr", **PARAMS["password_reset"]).subject == (
        "BotballDashboard: reset your password"
    )


def test_password_reset_mail_contains_the_link_in_text_and_html():
    message = render("password_reset", "de", **PARAMS["password_reset"])
    assert message.subject == "BotballDashboard: Passwort zurücksetzen"
    assert "Hallo Ada," in message.text
    assert "https://botball.example/reset?token=x" in message.text
    assert 'href="https://botball.example/reset?token=x"' in message.html
    assert "Neues Passwort setzen" in message.html


def test_html_escapes_user_text():
    message = render(
        "deadline_reminder", "en", title="<b>x</b>", due="2026-09-25", days=1, description="a & b"
    )
    assert "<b>x</b>" not in message.html and "&lt;b&gt;x&lt;/b&gt;" in message.html
    assert "a &amp; b" in message.html
    assert message.summary == "<b>x</b> is due tomorrow (25 September 2026).\n\na & b"


def test_deadline_reminder_texts():
    german = render("deadline_reminder", "de", title="Paper", due="2026-09-25", days=3)
    assert german.subject == "Deadline in 3 Tagen: Paper"
    assert german.summary == "Paper ist in 3 Tagen fällig (25. September 2026)."
    tomorrow = render("deadline_reminder", "de", title="Paper", due="2026-09-25", days=1)
    assert tomorrow.subject == "Deadline morgen: Paper"


def test_paper_deadline_reminder_keeps_custom_labels_and_translates_types():
    base = {"deadline_type": "official_final", "due": "2026-09-25", "days": 7}
    assert render("paper_deadline_reminder", "de", kind="revision", **base).subject == (
        "Offizielle finale Abgabe in 7 Tagen"
    )
    assert render("paper_deadline_reminder", "en", kind="revision", **base).subject == (
        "Official final submission in 7 days"
    )
    custom = render("paper_deadline_reminder", "en", kind="revision", label="ECER final", **base)
    assert custom.subject == "ECER final in 7 days"
    review = render("paper_deadline_reminder", "de", kind="review", **base)
    assert review.summary.startswith("Deine offenen Paper-Reviews sind in 7 Tagen fällig")


def test_render_notification_uses_the_payload_template():
    payload = {"title": "plain", **i18n_payload("deadline_reminder", **PARAMS["deadline_reminder"])}
    assert render_notification(payload, "en").subject == "Deadline in 3 days: Paper"
    assert render_notification(payload, "de").subject == "Deadline in 3 Tagen: Paper"
    assert render_notification({"title": "plain"}, "de") is None
    assert render_notification({"i18n": {"template": "unknown"}}, "de") is None

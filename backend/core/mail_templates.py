"""Localized (DE/EN) texts for e-mails and notifications.

Mails are rendered in the recipient's language (``User.preferred_language``).
Recipients without an account (e.g. team members that only have an e-mail
address) get ``DEFAULT_LANGUAGE``. A language without a translation falls
back to English, like the frontend (i18next ``fallbackLng: "en"``).

Notifications queued into the outbox carry ``{"i18n": {"template": name,
"params": {...}}}`` in their payload; the worker and the in-app notification
center render them per recipient with :func:`render_notification`.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from html import escape
from typing import Any

SUPPORTED_LANGUAGES = ("de", "en")
DEFAULT_LANGUAGE = "de"
FALLBACK_LANGUAGE = "en"

GERMAN_MONTHS = (
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
)
ENGLISH_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def normalize_language(value: str | None, default: str = DEFAULT_LANGUAGE) -> str:
    """ "de-AT" → "de"; unknown or empty values → `default`."""
    language = (value or "").split("-")[0].split("_")[0].strip().lower()
    return language if language in SUPPORTED_LANGUAGES else default


def format_date(value: date | str, language: str) -> str:
    """A calendar day as people write it: "25. September 2026" / "25 September 2026"."""
    day = date.fromisoformat(value) if isinstance(value, str) else value
    if normalize_language(language) == "de":
        return f"{day.day}. {GERMAN_MONTHS[day.month - 1]} {day.year}"
    return f"{day.day} {ENGLISH_MONTHS[day.month - 1]} {day.year}"


@dataclass(frozen=True)
class Message:
    """One rendered message: subject/title, paragraphs and an optional link."""

    subject: str
    paragraphs: tuple[str, ...]
    link: str | None = None
    link_text: str | None = None

    @property
    def text(self) -> str:
        parts = list(self.paragraphs)
        if self.link:
            parts.append(f"{self.link_text}: {self.link}" if self.link_text else self.link)
        return "\n\n".join(parts)

    @property
    def html(self) -> str:
        parts = [f"<p>{escape(p)}</p>".replace("\n", "<br>") for p in self.paragraphs]
        if self.link:
            label = escape(self.link_text or self.link)
            parts.append(f'<p><a href="{escape(self.link)}">{label}</a></p>')
        return "".join(parts)

    @property
    def summary(self) -> str:
        """Body for push and the notification center: the paragraphs, no link."""
        return "\n\n".join(self.paragraphs)


# ── Templates ─────────────────────────────────────────────────────────────────
#
# Each template maps a language to a function building the Message from the
# template parameters. Keep the parameters language-neutral (ISO dates, keys).


def _account_created_de(display_name: str, email: str, login_url: str, **_: Any) -> Message:
    return Message(
        subject="Dein BotballDashboard-Konto wurde angelegt",
        paragraphs=(
            f"Hallo {display_name},",
            f"für dich wurde ein BotballDashboard-Konto mit der E-Mail-Adresse {email} angelegt. "
            "Das Passwort erhältst du von der Person, die das Konto angelegt hat; "
            "du kannst es nach der Anmeldung in deinem Profil ändern.",
        ),
        link=login_url,
        link_text="Zur Anmeldung",
    )


def _account_created_en(display_name: str, email: str, login_url: str, **_: Any) -> Message:
    return Message(
        subject="Your BotballDashboard account was created",
        paragraphs=(
            f"Hello {display_name},",
            f"a BotballDashboard account with the email address {email} was created for you. "
            "You get the password from the person who created the account; "
            "you can change it in your profile after signing in.",
        ),
        link=login_url,
        link_text="Sign in",
    )


def _password_reset_de(display_name: str, link: str, **_: Any) -> Message:
    return Message(
        subject="BotballDashboard: Passwort zurücksetzen",
        paragraphs=(
            f"Hallo {display_name},",
            "über den folgenden Link kannst du ein neues Passwort setzen. Der Link ist eine "
            "Stunde gültig und nur einmal verwendbar. Wenn du das nicht angefordert hast, "
            "ignoriere diese E-Mail.",
        ),
        link=link,
        link_text="Neues Passwort setzen",
    )


def _password_reset_en(display_name: str, link: str, **_: Any) -> Message:
    return Message(
        subject="BotballDashboard: reset your password",
        paragraphs=(
            f"Hello {display_name},",
            "use the following link to set a new password. It is valid for one hour and "
            "can be used once. If you did not request this, ignore this email.",
        ),
        link=link,
        link_text="Set a new password",
    )


def _when_de(days: int) -> str:
    return "morgen" if days == 1 else f"in {days} Tagen"


def _when_en(days: int) -> str:
    return "tomorrow" if days == 1 else f"in {days} days"


def _deadline_reminder_de(
    title: str, due: str, days: int, description: str | None = None, **_: Any
) -> Message:
    when = _when_de(days)
    paragraphs = [f"{title} ist {when} fällig ({format_date(due, 'de')})."]
    if description:
        paragraphs.append(description)
    return Message(subject=f"Deadline {when}: {title}", paragraphs=tuple(paragraphs))


def _deadline_reminder_en(
    title: str, due: str, days: int, description: str | None = None, **_: Any
) -> Message:
    when = _when_en(days)
    paragraphs = [f"{title} is due {when} ({format_date(due, 'en')})."]
    if description:
        paragraphs.append(description)
    return Message(subject=f"Deadline {when}: {title}", paragraphs=tuple(paragraphs))


PAPER_DEADLINE_TYPES = {
    "de": {
        "official_submission": "Offizielle Paper-Einreichung",
        "official_final": "Offizielle finale Abgabe",
        "internal_draft": "Interne Entwurfs-Frist",
        "internal_review": "Interne Review-Frist",
        "internal_revision": "Interne Überarbeitungs-Frist",
        "internal_final": "Interne finale Abgabe",
    },
    "en": {
        "official_submission": "Official paper submission",
        "official_final": "Official final submission",
        "internal_draft": "Internal draft deadline",
        "internal_review": "Internal review deadline",
        "internal_revision": "Internal revision deadline",
        "internal_final": "Internal final submission",
    },
}


def _paper_label(language: str, deadline_type: str, label: str | None) -> str:
    return label or PAPER_DEADLINE_TYPES[language].get(deadline_type, deadline_type)


def _paper_deadline_reminder_de(
    kind: str, deadline_type: str, due: str, days: int, label: str | None = None, **_: Any
) -> Message:
    name = _paper_label("de", deadline_type, label)
    when = _when_de(days)
    day = format_date(due, "de")
    if kind == "review":
        text = f"Deine offenen Paper-Reviews sind {when} fällig ({day})."
    elif kind == "revision":
        text = (
            "Ladet die überarbeitete Version eures Papers hoch und reicht sie ein. "
            f"{name}: {day} ({when})."
        )
    else:
        text = f"Euer Team hat sein Paper noch nicht eingereicht. {name}: {day} ({when})."
    return Message(subject=f"{name} {when}", paragraphs=(text,))


def _paper_deadline_reminder_en(
    kind: str, deadline_type: str, due: str, days: int, label: str | None = None, **_: Any
) -> Message:
    name = _paper_label("en", deadline_type, label)
    when = _when_en(days)
    day = format_date(due, "en")
    if kind == "review":
        text = f"Your open paper reviews are due {when} ({day})."
    elif kind == "revision":
        text = f"Upload and submit the revised version of your paper. {name}: {day} ({when})."
    else:
        text = f"Your team has not submitted its paper yet. {name}: {day} ({when})."
    return Message(subject=f"{name} {when}", paragraphs=(text,))


TEMPLATES: dict[str, dict[str, Callable[..., Message]]] = {
    "account_created": {"de": _account_created_de, "en": _account_created_en},
    "password_reset": {"de": _password_reset_de, "en": _password_reset_en},
    "deadline_reminder": {"de": _deadline_reminder_de, "en": _deadline_reminder_en},
    "paper_deadline_reminder": {
        "de": _paper_deadline_reminder_de,
        "en": _paper_deadline_reminder_en,
    },
}


def render(template: str, language: str | None, **params: Any) -> Message:
    """Render `template` in `language` (English when that language is missing)."""
    variants = TEMPLATES[template]
    builder = variants.get(normalize_language(language, FALLBACK_LANGUAGE))
    builder = builder or variants[FALLBACK_LANGUAGE]
    return builder(**params)


def i18n_payload(template: str, **params: Any) -> dict[str, Any]:
    """Outbox payload part that lets the worker render per recipient language."""
    return {"i18n": {"template": template, "params": params}}


def render_notification(payload: dict, language: str | None) -> Message | None:
    """The payload's localized message, or None for plain (untranslated) payloads."""
    spec = payload.get("i18n")
    if not isinstance(spec, dict) or spec.get("template") not in TEMPLATES:
        return None
    return render(spec["template"], language, **(spec.get("params") or {}))

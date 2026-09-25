"""Award line-ups an event can start from.

ECER: the awards of the ECER results and ceremony (Botball and ECER Open
overall 1–3, Seeding, Double Elimination, Documentation on the
AdaptedDocScore of the ECER amendments, Best Paper, Best Paper Presentation,
Spirit of ECER, Outstanding Mechanical Subsystem, Judges' Choice, Aerial
Junior / Senior and the Junior Botball Challenge).

GCER: the International Botball Tournament awards (overall and double
elimination 1–4 per course, seeding 1–4, and the judged awards).

Computed awards take their places from a ranking (``source``); judged
awards are decided by the jury from nominations.
"""

from __future__ import annotations

from typing import Any

COMPUTED_SOURCES = ("overall", "seeding", "de", "doc", "adapted_doc", "paper", "aerial", "jbc")
JUDGED_SOURCES = ("paper_on_stage",)


def _computed(
    key: str,
    label: str,
    source: str,
    category: str | None,
    places: int = 1,
    per_course: bool = False,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "kind": "computed",
        "source": source,
        "team_category": category,
        "places": places,
        "per_course": per_course,
    }


def _judged(key: str, label: str, source: str | None = None, places: int = 1) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "kind": "judged",
        "source": source,
        "team_category": None,
        "places": places,
        "per_course": False,
    }


TEMPLATES: dict[str, dict[str, Any]] = {
    "ecer": {
        "name": "ECER",
        "awards": [
            _computed("botball_overall", "Botball – Overall", "overall", "botball", 3),
            _computed("open_overall", "ECER Open – Overall", "overall", "open", 3),
            _computed("botball_seeding", "Botball – Seeding", "seeding", "botball"),
            _computed("botball_de", "Botball – Double Elimination", "de", "botball"),
            _computed("open_seeding", "ECER Open – Seeding", "seeding", "open"),
            _computed("open_de", "ECER Open – Double Elimination", "de", "open"),
            _computed("documentation", "Documentation", "adapted_doc", "botball"),
            _computed("best_paper", "Best Paper", "paper", None),
            _judged("best_paper_presentation", "Best Paper Presentation", "paper_on_stage"),
            _judged("spirit_of_ecer", "Spirit of ECER"),
            _judged("mechanical_subsystem", "Outstanding Mechanical Subsystem"),
            _judged("judges_choice", "Judges' Choice"),
            _computed("aerial_junior", "Aerial Junior", "aerial", "aerial_junior", 3),
            _computed("aerial_senior", "Aerial Senior", "aerial", "aerial", 3),
            _computed("jbc", "Junior Botball Challenge", "jbc", "jbc", 3),
        ],
    },
    "gcer": {
        "name": "GCER",
        "awards": [
            _computed("overall", "Overall", "overall", "botball", 4, per_course=True),
            _computed("de", "Double Elimination", "de", "botball", 4, per_course=True),
            _computed("seeding", "Seeding", "seeding", "botball", 4),
            _judged("programming", "Programming"),
            _judged("engineering", "Engineering"),
            _judged("subsystem", "Subsystem"),
            _judged("robot_collaboration", "Robot Collaboration"),
            _judged("use_of_sensors", "Use of Sensors"),
            _judged("outreach", "Outreach"),
            _judged("team_spirit", "Team Spirit"),
            _judged("outstanding_overall_design", "Outstanding Overall Design"),
            _judged("outstanding_middle_school", "Outstanding Middle School"),
            _judged("outstanding_rookie", "Outstanding Rookie"),
            _judged("outstanding_documentation", "Outstanding Documentation"),
            _judged("kiss_award", "KISS Award"),
            _judged("spirit_of_botball", "Spirit of Botball"),
            _judged("judges_choice", "Judges' Choice"),
            _judged("overall_judges_choice", "Overall Judges' Choice"),
        ],
    },
}

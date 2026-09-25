"""Scouting report PDF (opponent ranking, observed scores and notes)."""

from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table

from modules.exports.pdf_builder import BODY, H2, SMALL, _header, _table_style


def _p(text: Any, style=BODY) -> Paragraph:
    return Paragraph(escape(str(text if text is not None else "–")).replace("\n", "<br/>"), style)


def build_scouting_pdf(report: dict[str, Any]) -> bytes:
    event = report["event"]
    teams = {t.id: t for t in report["teams"]}
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )
    elements: list = []
    _header(elements, "Scouting-Bericht", event.name)

    elements.append(Paragraph("Gegner-Rangliste", H2))
    rows: list[list[Any]] = [["#", "Team", "Nr.", "Land", "Typ", "Seed", "Best", "Läufe"]]
    for entry in report["ranking"]:
        rows.append(
            [
                entry["rank"],
                _p(entry["team_name"]),
                entry["team_number"] or "–",
                entry["country"] or "–",
                "eigenes" if entry["kind"] == "internal" else "extern",
                f"{entry['seed_score']:.1f}",
                f"{entry['best_score']:.1f}",
                entry["runs"],
            ]
        )
    if len(rows) == 1:
        rows.append(["", _p("Noch keine Daten"), "", "", "", "", "", ""])
    table = Table(
        rows,
        repeatRows=1,
        colWidths=[1 * cm, 5.4 * cm, 1.8 * cm, 2 * cm, 1.6 * cm, 1.6 * cm, 1.6 * cm, 1.4 * cm],
    )
    table.setStyle(_table_style())
    elements.append(table)

    observations_by_team: dict[str, list] = {}
    for obs in report["observations"]:
        observations_by_team.setdefault(obs.external_team_id, []).append(obs)
    notes_by_team: dict[str, list] = {}
    for note in report["notes"]:
        notes_by_team.setdefault(note.external_team_id, []).append(note)

    for team_id in sorted(
        set(observations_by_team) | set(notes_by_team),
        key=lambda tid: teams[tid].name if tid in teams else tid,
    ):
        team = teams.get(team_id)
        if not team:
            continue
        elements.append(Spacer(1, 0.5 * cm))
        heading = team.name + (f" ({team.number})" if team.number else "")
        elements.append(Paragraph(escape(heading), H2))
        if team.country or team.school:
            elements.append(_p(" · ".join(x for x in (team.country, team.school) if x), SMALL))
        if team.notes:
            elements.append(_p(team.notes))
        observed = observations_by_team.get(team_id, [])
        if observed:
            obs_rows: list[list[Any]] = [["Phase", "Runde", "Punkte", "Notiz"]]
            for obs in observed:
                obs_rows.append(
                    [obs.phase, obs.round_number or "–", f"{obs.score:.0f}", _p(obs.notes)]
                )
            obs_table = Table(
                obs_rows, repeatRows=1, colWidths=[3.5 * cm, 1.6 * cm, 1.8 * cm, 9.5 * cm]
            )
            obs_table.setStyle(_table_style())
            elements.append(Spacer(1, 0.2 * cm))
            elements.append(obs_table)
        for note in notes_by_team.get(team_id, []):
            threat = f" – Einschätzung {note.threat_level}/5" if note.threat_level else ""
            elements.append(Spacer(1, 0.2 * cm))
            elements.append(_p(f"{note.created_at:%d.%m.%Y %H:%M}{threat}", SMALL))
            elements.append(_p(note.body))

    doc.build(elements)
    return buf.getvalue()

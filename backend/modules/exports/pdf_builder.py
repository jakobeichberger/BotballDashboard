"""
PDF builder using reportlab.
All exports return bytes that can be streamed as a Response.
"""

from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Shared style constants ────────────────────────────────────────────────────
PRIMARY = colors.HexColor("#1d4ed8")
LIGHT_GRAY = colors.HexColor("#f1f5f9")
DARK_GRAY = colors.HexColor("#334155")
ACCENT = colors.HexColor("#0ea5e9")
GREEN = colors.HexColor("#16a34a")
RED = colors.HexColor("#dc2626")
YELLOW = colors.HexColor("#ca8a04")

STYLES = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=STYLES["Heading1"], textColor=PRIMARY, fontSize=18, spaceAfter=6)
H2 = ParagraphStyle("h2", parent=STYLES["Heading2"], textColor=DARK_GRAY, fontSize=13, spaceAfter=4)
BODY = ParagraphStyle("body", parent=STYLES["Normal"], fontSize=9, leading=13)
SMALL = ParagraphStyle("small", parent=STYLES["Normal"], fontSize=8, textColor=colors.gray)

# reportlab parses Paragraph text as markup: an unescaped "<b>" breaks the
# export (500), and "<img src=…>" makes the server fetch a URL or read a local
# file into the PDF. Every piece of user text that becomes a Paragraph goes
# through escape() (xml.sax.saxutils). Plain strings in Table cells are not
# parsed and need no escaping.


def _text(value, limit: int | None = None) -> str:
    """User text for a Paragraph: shortened first, then escaped."""
    text = str(value if value is not None else "")
    if limit is not None and len(text) > limit:
        text = text[:limit] + "…"
    return escape(text)


def _header(elements: list, title: str, subtitle: str = "") -> None:
    """Title and subtitle are plain text (season, event and team names)."""
    elements.append(Paragraph("BotballDashboard", SMALL))
    elements.append(Paragraph(escape(title), H1))
    if subtitle:
        elements.append(Paragraph(escape(subtitle), SMALL))
    elements.append(
        Paragraph(
            f"Exportiert am {datetime.now().strftime('%d.%m.%Y %H:%M')} Uhr",
            SMALL,
        )
    )
    elements.append(HRFlowable(width="100%", thickness=1, color=PRIMARY, spaceAfter=12))


def _table_style(header_rows: int = 1) -> TableStyle:
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, header_rows - 1), PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, header_rows - 1), colors.white),
            ("FONTNAME", (0, 0), (-1, header_rows - 1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, header_rows - 1), 9),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, header_rows), (-1, -1), [colors.white, LIGHT_GRAY]),
            ("FONTSIZE", (0, header_rows), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]
    )


# ── Ranking PDF ───────────────────────────────────────────────────────────────


def build_ranking_pdf(
    season_name: str,
    competition_level: str,
    ranking_rows: list[dict],
    teams_by_id: dict[str, str],
) -> bytes:
    """
    ranking_rows: list of dicts with keys rank, team_id, seed_score,
        best_score, average_score, rounds_played
    teams_by_id: {team_id: team_name}
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    elements: list = []

    _header(
        elements,
        "Rangliste",
        f"{season_name}" + (f" – {competition_level}" if competition_level else ""),
    )

    if not ranking_rows:
        elements.append(Paragraph("Keine Einträge vorhanden.", BODY))
    else:
        data = [["#", "Team", "Seed-Score", "Best-Score", "⌀ Score", "Runden"]]
        for r in ranking_rows:
            medal = {1: "🥇 ", 2: "🥈 ", 3: "🥉 "}.get(r["rank"], "")
            data.append(
                [
                    str(r["rank"]),
                    medal + teams_by_id.get(r["team_id"], r["team_id"][:8]),
                    f"{r['seed_score']:.2f}",
                    f"{r['best_score']:.2f}",
                    f"{r['average_score']:.2f}",
                    str(r["rounds_played"]),
                ]
            )

        col_widths = [1.2 * cm, 7 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 1.8 * cm]
        t = Table(data, colWidths=col_widths)
        t.setStyle(_table_style())
        elements.append(t)

    doc.build(elements)
    return buf.getvalue()


# ── Paper Review Summary PDF ──────────────────────────────────────────────────


def build_paper_review_pdf(
    season_name: str,
    papers: list[dict],
    teams_by_id: dict[str, str],
) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    elements: list = []

    _header(elements, "Paper-Review Übersicht", season_name)

    status_labels = {
        "draft": "Entwurf",
        "submitted": "Eingereicht",
        "under_review": "In Prüfung",
        "accepted": "Angenommen",
        "rejected": "Abgelehnt",
        "revision_requested": "Überarbeitung",
        "resubmitted": "Neu eingereicht",
        "disqualified_ai": "Disqualifiziert (KI)",
    }
    status_colors = {
        "accepted": GREEN,
        "rejected": RED,
        "disqualified_ai": RED,
        "revision_requested": YELLOW,
    }

    data = [["Team", "Titel", "Status", "Rev.", "Reviewer", "Ø Score"]]
    for p in papers:
        reviews = p.get("reviews", [])
        submitted_reviews = [r for r in reviews if r.get("is_submitted")]
        avg_score = (
            sum(r["total_score"] for r in submitted_reviews if r.get("total_score"))
            / len(submitted_reviews)
            if submitted_reviews
            else None
        )
        data.append(
            [
                teams_by_id.get(p["team_id"], p["team_id"][:8]),
                Paragraph(_text(p["title"], 60), BODY),
                status_labels.get(p["status"], p["status"]),
                str(p.get("revision_number", 1)),
                str(len(p.get("assignments", []))),
                f"{avg_score:.1f}" if avg_score is not None else "—",
            ]
        )

    col_widths = [3.5 * cm, 6 * cm, 2.5 * cm, 1.2 * cm, 1.8 * cm, 1.8 * cm]
    t = Table(data, colWidths=col_widths)
    style = _table_style()

    # Color-code status column
    for row_idx, p in enumerate(papers, start=1):
        c = status_colors.get(p["status"])
        if c:
            style.add("TEXTCOLOR", (2, row_idx), (2, row_idx), c)
            style.add("FONTNAME", (2, row_idx), (2, row_idx), "Helvetica-Bold")
    t.setStyle(style)
    elements.append(t)

    doc.build(elements)
    return buf.getvalue()


# ── Print Job Report PDF ──────────────────────────────────────────────────────


def build_print_report_pdf(
    season_name: str,
    jobs: list[dict],
    teams_by_id: dict[str, str],
    printers_by_id: dict[str, str],
) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    elements: list = []

    _header(elements, "3D-Druck Bericht", season_name)

    # Summary stats
    total_jobs = len(jobs)
    completed = sum(1 for j in jobs if j["status"] == "completed")
    total_grams = sum(j.get("actual_grams") or j.get("estimated_grams") or 0 for j in jobs)

    summary_data = [
        ["Gesamt Aufträge", "Abgeschlossen", "Verbrauchtes Filament"],
        [str(total_jobs), str(completed), f"{total_grams:.1f} g"],
    ]
    t = Table(summary_data, colWidths=[5.5 * cm, 5.5 * cm, 5.5 * cm])
    t.setStyle(_table_style())
    elements.append(t)
    elements.append(Spacer(1, 0.5 * cm))

    # Jobs table
    elements.append(Paragraph("Druckaufträge", H2))
    data = [["Team", "Datei", "Material", "Status", "Drucker", "Gramm"]]
    for j in jobs:
        grams = (
            j.get("actual_grams") if j.get("actual_grams") is not None else j.get("estimated_grams")
        )
        data.append(
            [
                teams_by_id.get(j["team_id"], j["team_id"][:8]),
                Paragraph(escape(str(j["file_name"])[:35]), BODY),
                j.get("material", "PLA"),
                j["status"],
                printers_by_id.get(j.get("printer_id", ""), "—"),
                f"{grams:.1f}g" if grams else "—",
            ]
        )

    col_widths = [3.5 * cm, 4.5 * cm, 1.8 * cm, 2 * cm, 3 * cm, 1.8 * cm]
    t = Table(data, colWidths=col_widths)
    t.setStyle(_table_style())
    elements.append(t)

    doc.build(elements)
    return buf.getvalue()


# ── Team List PDF ─────────────────────────────────────────────────────────────


def build_team_list_pdf(
    season_name: str,
    teams: list[dict],
) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    elements: list = []

    _header(elements, "Teamliste", season_name)

    data = [["#", "Teamname", "Nummer", "Schule", "Stadt", "Land", "Status"]]
    for i, t in enumerate(teams, start=1):
        data.append(
            [
                str(i),
                t["name"],
                t.get("team_number") or "—",
                t.get("school") or "—",
                t.get("city") or "—",
                t.get("country", "DE"),
                "Aktiv" if t.get("is_active") else "Inaktiv",
            ]
        )

    col_widths = [0.8 * cm, 4 * cm, 2 * cm, 3.5 * cm, 2.5 * cm, 1.5 * cm, 1.8 * cm]
    table = Table(data, colWidths=col_widths)
    table.setStyle(_table_style())
    elements.append(table)

    doc.build(elements)
    return buf.getvalue()


# ── Overall Ranking PDF (formula engine) ──────────────────────────────────────


def _fmt(value, digits: int = 2) -> str:
    return f"{value:.{digits}f}" if isinstance(value, int | float) else "—"


def build_overall_ranking_pdf(
    event_name: str,
    season_name: str,
    entries: list[dict],
) -> bytes:
    """entries: OverallRankingEntry dicts from the formula engine, grouped by
    category in the order given."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    elements: list = []
    _header(elements, "Gesamtwertung", f"{event_name} – {season_name}")

    if not entries:
        elements.append(Paragraph("Keine Einträge vorhanden.", BODY))
    categories: list[str] = []
    for entry in entries:
        if (entry.get("category") or "") not in categories:
            categories.append(entry.get("category") or "")
    for category in categories:
        rows = [e for e in entries if (e.get("category") or "") == category]
        if category:
            elements.append(Paragraph(escape(category.capitalize()), H2))
        data = [["#", "Team", "Gesamt", "Seeding", "DE", "Doku", "Paper"]]
        for e in rows:
            data.append(
                [
                    str(e.get("rank") or "—"),
                    Paragraph(escape(str(e.get("team_name") or e.get("team_id", ""))[:60]), BODY),
                    _fmt(e.get("overall_score"), 3),
                    _fmt(e.get("seeding_score"), 3),
                    _fmt(e.get("de_score"), 3),
                    _fmt(e.get("doc_score"), 3),
                    _fmt(e.get("paper_score"), 3),
                ]
            )
        col_widths = [1 * cm, 6 * cm, 2.2 * cm, 2.2 * cm, 2 * cm, 2 * cm, 2 * cm]
        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(_table_style())
        elements.append(table)
        elements.append(Spacer(1, 0.4 * cm))

    elements.append(
        Paragraph("Werte aus der Formel-Engine der Saison (Stand zum Exportzeitpunkt).", SMALL)
    )
    doc.build(elements)
    return buf.getvalue()


# ── Team Report PDF ───────────────────────────────────────────────────────────


def build_team_report_pdf(team: dict, history: list[dict]) -> bytes:
    """A team's results at every event, oldest first, with a season summary.

    team: name, team_number, school, city, country
    history: rows as returned by the dashboard history analytics
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    elements: list = []
    location = ", ".join(p for p in (team.get("city"), team.get("country")) if p)
    subtitle = " · ".join(
        str(part)
        for part in (
            f"#{team['team_number']}" if team.get("team_number") else None,
            team.get("school"),
            location,
        )
        if part
    )
    _header(elements, f"Teambericht: {team['name']}", subtitle)

    if not history:
        elements.append(Paragraph("Das Team hat noch an keinem Event teilgenommen.", BODY))
        doc.build(elements)
        return buf.getvalue()

    # Summary per season.
    elements.append(Paragraph("Saisonübersicht", H2))
    seasons: dict[int, list[dict]] = {}
    for row in history:
        seasons.setdefault(row["season_year"], []).append(row)
    summary = [["Saison", "Events", "Bester Seeding-Rang", "Bester Gesamtrang", "Bester Lauf"]]
    for year, rows in sorted(seasons.items()):
        seeding_ranks = [r["seeding_rank"] for r in rows if r.get("seeding_rank")]
        overall_ranks = [r["overall_rank"] for r in rows if r.get("overall_rank")]
        best = [r["best_score"] for r in rows if r.get("best_score") is not None]
        summary.append(
            [
                Paragraph(escape(f"{rows[0]['season_name']} ({year})"), BODY),
                str(len(rows)),
                str(min(seeding_ranks)) if seeding_ranks else "—",
                str(min(overall_ranks)) if overall_ranks else "—",
                _fmt(max(best)) if best else "—",
            ]
        )
    table = Table(summary, colWidths=[5.5 * cm, 1.8 * cm, 3.5 * cm, 3.5 * cm, 2.5 * cm])
    table.setStyle(_table_style())
    elements.append(table)
    elements.append(Spacer(1, 0.5 * cm))

    # Every event.
    elements.append(Paragraph("Ergebnisse pro Event", H2))
    with_practice = any("practice_runs" in r for r in history)
    header = ["Saison", "Event", "Seeding", "Seed-Score", "Gesamt", "Gesamt-Score", "Läufe"]
    if with_practice:
        header.append("Übung Ø")
    data: list[list] = [header]
    for r in history:
        seeding = f"{r['seeding_rank']}/{r['seeding_teams']}" if r.get("seeding_rank") else "—"
        overall = f"{r['overall_rank']}/{r['overall_teams']}" if r.get("overall_rank") else "—"
        line = [
            str(r["season_year"]),
            Paragraph(escape(str(r["event_name"])[:80]), BODY),
            seeding,
            _fmt(r.get("seeding_score")),
            overall,
            _fmt(r.get("overall_score"), 3),
            str(r.get("official_runs", 0)),
        ]
        if with_practice:
            line.append(
                f"{_fmt(r.get('practice_avg'), 1)} ({r.get('practice_runs', 0)})"
                if r.get("practice_runs")
                else "—"
            )
        data.append(line)
    widths = [1.4 * cm, 5 * cm, 1.8 * cm, 2 * cm, 1.8 * cm, 2.2 * cm, 1.3 * cm]
    if with_practice:
        widths = [1.3 * cm, 4.2 * cm, 1.7 * cm, 1.9 * cm, 1.7 * cm, 2.1 * cm, 1.2 * cm, 2 * cm]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(_table_style())
    elements.append(table)

    doc.build(elements)
    return buf.getvalue()

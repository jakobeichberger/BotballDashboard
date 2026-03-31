"""
PDF builder using reportlab.
All exports return bytes that can be streamed as a Response.
"""
from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    HRFlowable,
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


def _header(elements: list, title: str, subtitle: str = "") -> None:
    elements.append(Paragraph("BotballDashboard", SMALL))
    elements.append(Paragraph(title, H1))
    if subtitle:
        elements.append(Paragraph(subtitle, SMALL))
    elements.append(Paragraph(
        f"Exportiert am {datetime.now().strftime('%d.%m.%Y %H:%M')} Uhr",
        SMALL,
    ))
    elements.append(HRFlowable(width="100%", thickness=1, color=PRIMARY, spaceAfter=12))


def _table_style(header_rows: int = 1) -> TableStyle:
    return TableStyle([
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
    ])


# ── Ranking PDF ───────────────────────────────────────────────────────────────

def build_ranking_pdf(
    season_name: str,
    competition_level: str,
    ranking_rows: list[dict],
    teams_by_id: dict[str, str],
) -> bytes:
    """
    ranking_rows: list of dicts with keys rank, team_id, seed_score, best_score, average_score, rounds_played
    teams_by_id: {team_id: team_name}
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    elements: list = []

    _header(elements, "Rangliste",
            f"{season_name}" + (f" – {competition_level}" if competition_level else ""))

    if not ranking_rows:
        elements.append(Paragraph("Keine Einträge vorhanden.", BODY))
    else:
        data = [["#", "Team", "Seed-Score", "Best-Score", "⌀ Score", "Runden"]]
        for r in ranking_rows:
            medal = {1: "🥇 ", 2: "🥈 ", 3: "🥉 "}.get(r["rank"], "")
            data.append([
                str(r["rank"]),
                medal + teams_by_id.get(r["team_id"], r["team_id"][:8]),
                f"{r['seed_score']:.2f}",
                f"{r['best_score']:.2f}",
                f"{r['average_score']:.2f}",
                str(r["rounds_played"]),
            ])

        col_widths = [1.2*cm, 7*cm, 2.5*cm, 2.5*cm, 2.5*cm, 1.8*cm]
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
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    elements: list = []

    _header(elements, "Paper-Review Übersicht", season_name)

    status_labels = {
        "draft": "Entwurf", "submitted": "Eingereicht",
        "under_review": "In Prüfung", "accepted": "Angenommen",
        "rejected": "Abgelehnt", "revision_requested": "Überarbeitung",
    }
    status_colors = {
        "accepted": GREEN, "rejected": RED,
        "revision_requested": YELLOW,
    }

    data = [["Team", "Titel", "Status", "Rev.", "Reviewer", "Ø Score"]]
    for p in papers:
        reviews = p.get("reviews", [])
        submitted_reviews = [r for r in reviews if r.get("is_submitted")]
        avg_score = (
            sum(r["total_score"] for r in submitted_reviews if r.get("total_score"))
            / len(submitted_reviews)
            if submitted_reviews else None
        )
        data.append([
            teams_by_id.get(p["team_id"], p["team_id"][:8]),
            Paragraph(p["title"][:60] + ("…" if len(p["title"]) > 60 else ""), BODY),
            status_labels.get(p["status"], p["status"]),
            str(p.get("revision_number", 1)),
            str(len(p.get("assignments", []))),
            f"{avg_score:.1f}" if avg_score is not None else "—",
        ])

    col_widths = [3.5*cm, 6*cm, 2.5*cm, 1.2*cm, 1.8*cm, 1.8*cm]
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
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
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
    t = Table(summary_data, colWidths=[5.5*cm, 5.5*cm, 5.5*cm])
    t.setStyle(_table_style())
    elements.append(t)
    elements.append(Spacer(1, 0.5*cm))

    # Jobs table
    elements.append(Paragraph("Druckaufträge", H2))
    data = [["Team", "Datei", "Material", "Status", "Drucker", "Gramm"]]
    for j in jobs:
        grams = j.get("actual_grams") if j.get("actual_grams") is not None else j.get("estimated_grams")
        data.append([
            teams_by_id.get(j["team_id"], j["team_id"][:8]),
            Paragraph(j["file_name"][:35], BODY),
            j.get("material", "PLA"),
            j["status"],
            printers_by_id.get(j.get("printer_id", ""), "—"),
            f"{grams:.1f}g" if grams else "—",
        ])

    col_widths = [3.5*cm, 4.5*cm, 1.8*cm, 2*cm, 3*cm, 1.8*cm]
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
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    elements: list = []

    _header(elements, "Teamliste", season_name)

    data = [["#", "Teamname", "Nummer", "Schule", "Stadt", "Land", "Status"]]
    for i, t in enumerate(teams, start=1):
        data.append([
            str(i),
            t["name"],
            t.get("team_number") or "—",
            t.get("school") or "—",
            t.get("city") or "—",
            t.get("country", "DE"),
            "Aktiv" if t.get("is_active") else "Inaktiv",
        ])

    col_widths = [0.8*cm, 4*cm, 2*cm, 3.5*cm, 2.5*cm, 1.5*cm, 1.8*cm]
    table = Table(data, colWidths=col_widths)
    table.setStyle(_table_style())
    elements.append(table)

    doc.build(elements)
    return buf.getvalue()

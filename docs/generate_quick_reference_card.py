"""
Generate a printable BIZORA Quick Reference Card PDF (landscape, cut-ready).

Run:
    python docs/generate_quick_reference_card.py

Output:
    docs/BIZORA_Quick_Reference_Card_v1.0.0.pdf
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DOCS_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(DOCS_DIR))

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm, mm
from reportlab.platypus import PageBreak, Paragraph, Spacer, Table, TableStyle

from config import APP_NAME, APP_VERSION, COMPANY_DISPLAY_NAME
from manual_pdf_common import (
    BRAND_BLUE,
    BRAND_DARK,
    BORDER_GREY,
    CardDocTemplate,
    build_styles,
    make_table,
)

OUTPUT_PATH = DOCS_DIR / f"{APP_NAME}_Quick_Reference_Card_v{APP_VERSION}.pdf"


def _card_table(rows, col_widths):
    """Compact table for quick-reference cards."""
    table = make_table(["", ""], rows, col_widths=col_widths)
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return table


def build_card_front(story, styles) -> None:
    """Front side: keyboard shortcuts."""
    story.append(Paragraph(f"{APP_NAME} — Quick Reference Card", styles["CardTitle"]))
    story.append(Paragraph(f"Version {APP_VERSION}  |  {datetime.now().strftime('%d-%m-%Y')}", styles["CardBody"]))
    story.append(Spacer(1, 4 * mm))

    left = [
        ["Ctrl+L", "Sales Entry"], ["Ctrl+B", "Purchase Entry"],
        ["Ctrl+R", "Sales Return"], ["Ctrl+U", "Purchase Return"],
        ["Ctrl+Q", "Quotation"], ["Ctrl+K", "Purchase Order"],
        ["Ctrl+T", "Cash Receipt"], ["Ctrl+M", "Cash Payment"],
        ["Ctrl+I", "Bank Receipt"], ["Ctrl+Y", "Bank Payment"],
    ]
    right = [
        ["Ctrl+J", "Journal Entry"], ["Ctrl+D", "Post Dated Cheque"],
        ["Ctrl+H", "Credit/Debit Note"], ["Ctrl+W", "Van Entry"],
        ["Ctrl+E", "Van Return"], ["F5", "Ledger"],
        ["F6", "Day Book"], ["F7", "Cash Book"],
        ["F8", "Price List"], ["F9", "Stock Report"],
    ]
    global_rows = [
        ["Ctrl+S", "Save"], ["Ctrl+P", "Print"],
        ["Ctrl+F", "Global Search"], ["Ctrl+N", "New Record"],
        ["Enter", "Next field"], ["Escape", "Previous field"],
    ]

    layout = Table(
        [[_card_table(left, [2.8 * cm, 5.5 * cm]), _card_table(right, [2.8 * cm, 5.5 * cm])]],
        colWidths=[9 * cm, 9 * cm],
    )
    layout.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(layout)
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Global Actions", styles["CardSection"]))
    story.append(_card_table(global_rows, [2.5 * cm, 6 * cm]))


def build_card_back(story, styles) -> None:
    """Back side: daily workflow and tips."""
    story.append(Paragraph("Daily Sales Workflow", styles["CardSection"]))
    for step in [
        "1. Ctrl+L → set Date, Cash/Credit, Local/Inter-state",
        "2. Select party → scan barcode or type product",
        "3. Enter through grid: Product → HSN → Tax → Rate → Qty → Disc",
        "4. Ctrl+S Save → Ctrl+P Print",
    ]:
        story.append(Paragraph(step, styles["CardBody"]))

    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Grid Navigation Tips", styles["CardSection"]))
    for tip in [
        "• Enter = forward field  |  Escape = backward field",
        "• Single-click cell = select all text for overwrite",
        "• Down Arrow in Disc column = convert to % of gross",
        "• After last column, new row starts automatically",
    ]:
        story.append(Paragraph(tip, styles["CardBody"]))

    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Admin Reminders", styles["CardSection"]))
    for tip in [
        "• Backup before year-end closing",
        "• Max 3 companies per installation",
        "• Admin role = full access; set operator permissions carefully",
        "• Previous FY opens read-only — no new entries allowed",
    ]:
        story.append(Paragraph(tip, styles["CardBody"]))

    story.append(Spacer(1, 4 * mm))
    story.append(
        Paragraph(
            f"{COMPANY_DISPLAY_NAME}  |  Print double-sided and laminate for desk use.",
            styles["CardBody"],
        )
    )


def build_manual() -> str:
    """Build the quick reference card PDF (2 landscape pages)."""
    styles = build_styles()
    story = []
    build_card_front(story, styles)
    story.append(PageBreak())
    build_card_back(story, styles)

    page_w, page_h = landscape(A4)
    doc = CardDocTemplate(
        str(OUTPUT_PATH),
        pagesize=landscape(A4),
        rightMargin=1.2 * cm,
        leftMargin=1.2 * cm,
        topMargin=1 * cm,
        bottomMargin=1.2 * cm,
    )
    doc.build(story)
    return str(OUTPUT_PATH)


def main() -> None:
    path = build_manual()
    print(f"Quick reference card generated: {path}")


if __name__ == "__main__":
    main()

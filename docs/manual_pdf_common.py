"""
Shared PDF building blocks for BIZORA user manuals.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

try:
    from config import APP_NAME, APP_VERSION, COMPANY_DISPLAY_NAME
except ImportError:
    APP_NAME = "BIZORA"
    APP_VERSION = "1.0.0"
    COMPANY_DISPLAY_NAME = "BIZORA Software Solutions"

DOCS_DIR = Path(__file__).resolve().parent
SCREENSHOTS_DIR = DOCS_DIR / "screenshots"

BRAND_BLUE = colors.HexColor("#1976D2")
BRAND_DARK = colors.HexColor("#1A1A2E")
BRAND_GREY = colors.HexColor("#555555")
TABLE_HEADER_BG = colors.HexColor("#E3F2FD")
TABLE_ALT_BG = colors.HexColor("#F5F5F5")
BORDER_GREY = colors.HexColor("#CCCCCC")


class ManualDocTemplate(BaseDocTemplate):
    """Document template with branded header, footer, and TOC hooks."""

    def __init__(self, filename: str, doc_title: str, **kwargs):
        self.doc_title = doc_title
        super().__init__(filename, **kwargs)
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="normal")
        cover_frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="cover")
        self.addPageTemplates([
            PageTemplate(id="Cover", frames=[cover_frame], onPage=self._cover_page),
            PageTemplate(id="Content", frames=[frame], onPage=self._content_page),
        ])

    def _cover_page(self, canvas, doc):
        pass

    def _content_page(self, canvas, doc):
        canvas.saveState()
        width, height = A4
        canvas.setStrokeColor(BRAND_BLUE)
        canvas.setLineWidth(0.5)
        canvas.line(doc.leftMargin, height - 45, width - doc.rightMargin, height - 45)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(BRAND_BLUE)
        canvas.drawString(doc.leftMargin, height - 38, self.doc_title)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(BRAND_GREY)
        canvas.drawRightString(width - doc.rightMargin, height - 38, COMPANY_DISPLAY_NAME)
        canvas.setStrokeColor(BORDER_GREY)
        canvas.line(doc.leftMargin, 35, width - doc.rightMargin, 35)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(doc.leftMargin, 22, f"Generated: {datetime.now().strftime('%d-%m-%Y')}")
        canvas.drawCentredString(width / 2, 22, "Confidential — For Authorized Users Only")
        canvas.drawRightString(width - doc.rightMargin, 22, f"Page {doc.page}")
        canvas.restoreState()

    def afterFlowable(self, flowable):
        if flowable.__class__.__name__ != "Paragraph":
            return
        style_name = flowable.style.name
        text = flowable.getPlainText()
        if style_name == "ChapterTitle":
            self.notify("TOCEntry", (0, text, self.page))
        elif style_name == "SectionTitle":
            self.notify("TOCEntry", (1, text, self.page))


class CardDocTemplate(BaseDocTemplate):
    """Compact template for printable quick-reference cards."""

    def __init__(self, filename: str, **kwargs):
        super().__init__(filename, **kwargs)
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="card")
        self.addPageTemplates([PageTemplate(id="Card", frames=[frame], onPage=self._card_page)])

    def _card_page(self, canvas, doc):
        canvas.saveState()
        width, height = landscape(A4)
        canvas.setStrokeColor(BORDER_GREY)
        canvas.setLineWidth(0.5)
        canvas.rect(doc.leftMargin, doc.bottomMargin, doc.width, doc.height)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(BRAND_GREY)
        canvas.drawRightString(width - doc.rightMargin, doc.bottomMargin - 10, f"{APP_NAME} v{APP_VERSION}")
        canvas.restoreState()


def build_styles() -> dict:
    """Return paragraph styles used across all manuals."""
    base = getSampleStyleSheet()
    return {
        "CoverTitle": ParagraphStyle(
            "CoverTitle", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=30, textColor=BRAND_BLUE, alignment=TA_CENTER, spaceAfter=12, leading=36,
        ),
        "CoverSubtitle": ParagraphStyle(
            "CoverSubtitle", parent=base["Normal"], fontName="Helvetica",
            fontSize=15, textColor=BRAND_DARK, alignment=TA_CENTER, spaceAfter=8,
        ),
        "CoverMeta": ParagraphStyle(
            "CoverMeta", parent=base["Normal"], fontName="Helvetica",
            fontSize=10, textColor=BRAND_GREY, alignment=TA_CENTER, spaceAfter=5,
        ),
        "ChapterTitle": ParagraphStyle(
            "ChapterTitle", parent=base["Heading1"], fontName="Helvetica-Bold",
            fontSize=17, textColor=BRAND_BLUE, spaceBefore=16, spaceAfter=8,
        ),
        "SectionTitle": ParagraphStyle(
            "SectionTitle", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=12, textColor=BRAND_DARK, spaceBefore=12, spaceAfter=5,
        ),
        "SubSectionTitle": ParagraphStyle(
            "SubSectionTitle", parent=base["Heading3"], fontName="Helvetica-Bold",
            fontSize=10, textColor=BRAND_DARK, spaceBefore=8, spaceAfter=3,
        ),
        "Body": ParagraphStyle(
            "Body", parent=base["Normal"], fontName="Helvetica", fontSize=9.5,
            textColor=BRAND_DARK, alignment=TA_JUSTIFY, spaceAfter=5,
        ),
        "Bullet": ParagraphStyle(
            "Bullet", parent=base["Normal"], fontName="Helvetica", fontSize=9.5,
            textColor=BRAND_DARK, leftIndent=16, spaceAfter=2,
        ),
        "Note": ParagraphStyle(
            "Note", parent=base["Normal"], fontName="Helvetica-Oblique",
            fontSize=8.5, textColor=BRAND_GREY, leftIndent=10, spaceAfter=5,
        ),
        "Caption": ParagraphStyle(
            "Caption", parent=base["Normal"], fontName="Helvetica-Oblique",
            fontSize=8.5, textColor=BRAND_GREY, alignment=TA_CENTER, spaceAfter=8,
        ),
        "TOCTitle": ParagraphStyle(
            "TOCTitle", parent=base["Heading1"], fontName="Helvetica-Bold",
            fontSize=18, textColor=BRAND_BLUE, spaceAfter=14,
        ),
        "CardTitle": ParagraphStyle(
            "CardTitle", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=16, textColor=BRAND_BLUE, alignment=TA_CENTER, spaceAfter=6,
        ),
        "CardSection": ParagraphStyle(
            "CardSection", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=10, textColor=BRAND_DARK, spaceBefore=4, spaceAfter=2,
        ),
        "CardBody": ParagraphStyle(
            "CardBody", parent=base["Normal"], fontName="Helvetica", fontSize=8.5,
            textColor=BRAND_DARK, spaceAfter=2,
        ),
    }


def make_table(headers: list[str], rows: list[list[str]], col_widths=None) -> Table:
    """Build a styled data table."""
    data = [headers] + rows
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), BRAND_DARK),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER_GREY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, TABLE_ALT_BG]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def chapter(story, styles, title: str) -> None:
    story.append(Paragraph(title, styles["ChapterTitle"]))


def section(story, styles, title: str) -> None:
    story.append(Paragraph(title, styles["SectionTitle"]))


def subsection(story, styles, title: str) -> None:
    story.append(Paragraph(title, styles["SubSectionTitle"]))


def body(story, styles, text: str) -> None:
    story.append(Paragraph(text, styles["Body"]))


def bullets(story, styles, items: list[str]) -> None:
    for item in items:
        story.append(Paragraph(f"• {item}", styles["Bullet"]))


def note(story, styles, text: str) -> None:
    story.append(Paragraph(f"Note: {text}", styles["Note"]))


def field_table(story, rows, headers=None) -> None:
    hdr = headers or ["Field", "Description"]
    story.append(make_table(hdr, rows, col_widths=[4.5 * cm, 12.5 * cm]))
    story.append(Spacer(1, 6))


def shortcut_table(story, rows) -> None:
    story.append(make_table(["Shortcut", "Action"], rows, col_widths=[3.5 * cm, 13.5 * cm]))
    story.append(Spacer(1, 6))


def add_screenshot(story, styles, filename: str, caption: str, max_width: float = 15.5 * cm) -> None:
    """Embed a screenshot PNG if it exists in docs/screenshots/."""
    path = SCREENSHOTS_DIR / filename
    if not path.is_file():
        note(story, styles, f"Screenshot unavailable: {caption}")
        return
    img = Image(str(path))
    aspect = img.imageHeight / float(img.imageWidth)
    img.drawWidth = max_width
    img.drawHeight = max_width * aspect
    if img.drawHeight > 18 * cm:
        img.drawHeight = 18 * cm
        img.drawWidth = img.drawHeight / aspect
    story.append(Spacer(1, 4))
    story.append(img)
    story.append(Paragraph(f"Figure: {caption}", styles["Caption"]))


def build_cover(story, styles, title: str, subtitle: str, tagline: str) -> None:
    """Build a branded cover page."""
    story.append(Spacer(1, 5.5 * cm))
    story.append(Paragraph(APP_NAME, styles["CoverTitle"]))
    story.append(Paragraph(title, styles["CoverSubtitle"]))
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(subtitle, styles["CoverMeta"]))
    story.append(Paragraph(f"Version {APP_VERSION}", styles["CoverMeta"]))
    story.append(Paragraph(COMPANY_DISPLAY_NAME, styles["CoverMeta"]))
    story.append(Spacer(1, 1 * cm))
    story.append(Paragraph(tagline, styles["CoverMeta"]))
    story.append(Spacer(1, 1.5 * cm))
    story.append(Paragraph(f"Document date: {datetime.now().strftime('%d %B %Y')}", styles["CoverMeta"]))
    story.append(NextPageTemplate("Content"))
    story.append(PageBreak())


def build_toc(story, styles) -> TableOfContents:
    """Add table of contents."""
    story.append(Paragraph("Table of Contents", styles["TOCTitle"]))
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(
            name="TOC0", fontName="Helvetica-Bold", fontSize=10,
            spaceBefore=5, spaceAfter=2, textColor=BRAND_DARK,
        ),
        ParagraphStyle(
            name="TOC1", fontName="Helvetica", fontSize=9,
            leftIndent=18, spaceBefore=2, spaceAfter=1, textColor=BRAND_GREY,
        ),
    ]
    story.append(toc)
    story.append(PageBreak())
    return toc


def render_pdf(story: list, output_path: Path, doc_title: str) -> str:
    """Build a multi-pass PDF from a story flowable list."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = ManualDocTemplate(
        str(output_path),
        doc_title=doc_title,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2.2 * cm,
        bottomMargin=2 * cm,
        title=doc_title,
        author=COMPANY_DISPLAY_NAME,
    )
    doc.multiBuild(story)
    return str(output_path)

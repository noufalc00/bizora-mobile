"""
Generate the BIZORA Operator Manual PDF (daily data-entry and reporting).

Run:
    python docs/generate_operator_manual.py
"""

from __future__ import annotations

import sys
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DOCS_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(DOCS_DIR))

from config import APP_NAME, APP_VERSION
from manual_pdf_common import (
    PageBreak,
    add_screenshot,
    body,
    build_cover,
    build_styles,
    build_toc,
    bullets,
    chapter,
    field_table,
    note,
    render_pdf,
    section,
    shortcut_table,
    subsection,
)

import generate_user_manual_pdf as full_manual

OUTPUT_PATH = DOCS_DIR / f"{APP_NAME}_Operator_Manual_v{APP_VERSION}.pdf"
DOC_TITLE = f"{APP_NAME} Operator Manual v{APP_VERSION}"


def build_operator_intro(story, styles) -> None:
    """Operator-focused introduction."""
    chapter(story, styles, "1. About This Manual")
    body(
        story,
        styles,
        "This <b>Operator Manual</b> is for daily users who enter transactions, maintain "
        "masters, view books, and run operational reports. For company setup, user "
        "management, backup, and year-end procedures, refer to the "
        "<b>Administrator Manual</b>.",
    )
    section(story, styles, "1.1 What Operators Do Daily")
    bullets(
        story,
        styles,
        [
            "Log in and set the working date",
            "Enter sales, purchase, and return bills",
            "Record cash/bank receipts and payments",
            "Maintain party and product masters",
            "View books and run reports",
            "Print invoices and share bills",
        ],
    )


def build_operator_screenshots_gallery(story, styles) -> None:
    """Visual tour of key operator screens."""
    chapter(story, styles, "2. Visual Screen Guide")
    body(story, styles, "The following screenshots show the main screens operators use every day.")
    gallery = [
        ("01_company_gateway.png", "Company Gateway — login screen"),
        ("02_dashboard.png", "Dashboard — financial overview home screen"),
        ("03_sales_entry.png", "Sales Bill entry screen"),
        ("04_purchase_entry.png", "Purchase Bill entry screen"),
        ("05_products_master.png", "Product/Service master"),
        ("06_party_master.png", "Debtor/Creditor party master"),
        ("07_ledger.png", "Ledger report"),
        ("10_cash_receipt.png", "Cash Receipt voucher"),
        ("17_sales_book.png", "Sales Book register"),
    ]
    for filename, caption in gallery:
        section(story, styles, caption)
        add_screenshot(story, styles, filename, caption)


def build_operator_daily_workflows(story, styles) -> None:
    """Operator-only workflows."""
    chapter(story, styles, "Daily Workflows")
    section(story, styles, "Sales Entry (Ctrl+L)")
    bullets(
        story,
        styles,
        [
            "Open Sales → set Date, Type (Cash/Credit), Nature (Local/Inter-state)",
            "Select party → add products via barcode or name search",
            "Press Enter through grid columns; Save with Ctrl+S",
            "Print with Ctrl+P; share via WhatsApp/SMS buttons",
        ],
    )
    add_screenshot(story, styles, "03_sales_entry.png", "Sales entry workflow reference")
    section(story, styles, "Purchase Entry (Ctrl+B)")
    bullets(
        story,
        styles,
        [
            "Open Purchase → select Creditor",
            "Use Import PO to load a purchase order",
            "Verify rates and quantities → Save",
        ],
    )
    section(story, styles, "Cash / Bank Vouchers")
    shortcut_table(
        story,
        [
            ["Ctrl+T", "Cash Receipt"], ["Ctrl+M", "Cash Payment"],
            ["Ctrl+I", "Bank Receipt"], ["Ctrl+Y", "Bank Payment"],
        ],
    )
    add_screenshot(story, styles, "10_cash_receipt.png", "Cash Receipt voucher layout")


def build_manual() -> str:
    """Build operator manual PDF."""
    styles = build_styles()
    story = []
    build_cover(
        story,
        styles,
        "Operator Manual",
        f"Version {APP_VERSION}",
        "Daily transaction entry, masters, books, and reports for data-entry operators.",
    )
    build_toc(story, styles)

    build_operator_intro(story, styles)
    story.append(PageBreak())
    build_operator_screenshots_gallery(story, styles)
    story.append(PageBreak())

    operator_chapters = [
        full_manual.build_chapter_3_gateway,
        full_manual.build_chapter_4_main_window,
        full_manual.build_chapter_6_keyboard,
        full_manual.build_chapter_7_masters,
        full_manual.build_chapter_8_entries,
        full_manual.build_chapter_9_books,
        full_manual.build_chapter_10_reports,
        full_manual.build_chapter_11_gst,
        full_manual.build_chapter_16_ui,
        build_operator_daily_workflows,
        lambda s, st: full_manual.build_chapter_20_workflows(s, st),
        full_manual.build_chapter_18_troubleshooting,
        full_manual.build_chapter_23_quick_ref,
    ]
    for builder in operator_chapters:
        builder(story, styles)
        story.append(PageBreak())

    return render_pdf(story, OUTPUT_PATH, DOC_TITLE)


def main() -> None:
    path = build_manual()
    print(f"Operator manual generated: {path}")


if __name__ == "__main__":
    main()

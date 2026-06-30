"""
Generate the BIZORA Administrator Manual PDF (setup, security, backup, year-end).

Run:
    python docs/generate_admin_manual.py
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
    subsection,
)

import generate_user_manual_pdf as full_manual

OUTPUT_PATH = DOCS_DIR / f"{APP_NAME}_Admin_Manual_v{APP_VERSION}.pdf"
DOC_TITLE = f"{APP_NAME} Administrator Manual v{APP_VERSION}"


def build_admin_intro(story, styles) -> None:
    """Administrator-focused introduction."""
    chapter(story, styles, "1. About This Manual")
    body(
        story,
        styles,
        "This <b>Administrator Manual</b> covers company setup, user management, "
        "permissions, settings, backup, year-end closing, and system maintenance. "
        "For daily sales/purchase entry and books, refer to the <b>Operator Manual</b>.",
    )
    section(story, styles, "1.1 Administrator Responsibilities")
    bullets(
        story,
        styles,
        [
            "Create and configure companies (max 3 per installation)",
            "Manage users, roles, and module permissions",
            "Configure invoice numbering, print, and barcode settings",
            "Set up automatic backups and perform restores",
            "Run year-end closing and database maintenance",
            "Monitor audit logs and system diagnostics",
        ],
    )


def build_admin_screenshots_gallery(story, styles) -> None:
    """Visual guide for admin screens."""
    chapter(story, styles, "2. Administrator Screen Guide")
    gallery = [
        ("11_new_company.png", "Create New Company wizard"),
        ("12_invoice_settings.png", "Invoice Settings — numbering and cash tender"),
        ("13_general_settings.png", "General Settings — theme and layout"),
        ("14_backup_restore.png", "Backup and Restore Data dialog"),
        ("15_user_management.png", "Manage Users and permissions"),
        ("16_account_master.png", "Chart of Accounts setup"),
    ]
    for filename, caption in gallery:
        section(story, styles, caption)
        add_screenshot(story, styles, filename, caption)


def build_admin_setup_checklist(story, styles) -> None:
    """First-time company setup checklist for admins."""
    chapter(story, styles, "Administrator Setup Checklist")
    bullets(
        story,
        styles,
        [
            "1. Create company with GSTIN, financial year, logo, signature",
            "2. Configure invoice prefixes (Settings → Invoice Settings)",
            "3. Set print format and footer terms (Print Settings)",
            "4. Create Admin and operator user accounts with correct permissions",
            "5. Enter opening ledger and stock balances",
            "6. Configure backup folder and enable auto-backup on close",
            "7. Test a sample sales bill, print, and verify GST calculations",
            "8. Run Trial Balance to confirm opening balances",
        ],
    )
    add_screenshot(story, styles, "11_new_company.png", "New company setup screen")
    add_screenshot(story, styles, "14_backup_restore.png", "Backup configuration")


def build_manual() -> str:
    """Build administrator manual PDF."""
    styles = build_styles()
    story = []
    build_cover(
        story,
        styles,
        "Administrator Manual",
        f"Version {APP_VERSION}",
        "Company setup, users, permissions, settings, backup, year-end, and maintenance.",
    )
    build_toc(story, styles)

    build_admin_intro(story, styles)
    story.append(PageBreak())
    build_admin_screenshots_gallery(story, styles)
    story.append(PageBreak())

    admin_chapters = [
        full_manual.build_chapter_2_requirements,
        full_manual.build_chapter_5_company,
        build_admin_setup_checklist,
        full_manual.build_chapter_12_settings,
        full_manual.build_chapter_13_users,
        full_manual.build_chapter_14_utilities,
        full_manual.build_chapter_15_backup,
        full_manual.build_chapter_17_readonly,
        full_manual.build_chapter_21_permissions,
        full_manual.build_chapter_22_readonly_routes,
        lambda s, st: _admin_workflows(s, st),
        full_manual.build_chapter_18_troubleshooting,
    ]
    for builder in admin_chapters:
        builder(story, styles)
        story.append(PageBreak())

    return render_pdf(story, OUTPUT_PATH, DOC_TITLE)


def _admin_workflows(story, styles) -> None:
    """Admin-specific workflows from full manual."""
    chapter(story, styles, "Year-End & Maintenance Workflows")
    section(story, styles, "Month-End Reporting")
    bullets(
        story,
        styles,
        [
            "Run Trial Balance, P&amp;L, and Balance Sheet for the month",
            "Export GST Sales/Purchase reports and GSTR-1",
            "Run manual backup before month close",
        ],
    )
    section(story, styles, "Year-End Closing")
    bullets(
        story,
        styles,
        [
            "Complete all pending entries for the financial year",
            "Run manual backup",
            "Utilities → Close Financial Year (Year-End)",
            "Re-login to the new financial year database",
        ],
    )
    note(story, styles, "Year-end locks the current database. Previous year opens in read-only mode.")


def main() -> None:
    path = build_manual()
    print(f"Administrator manual generated: {path}")


if __name__ == "__main__":
    main()

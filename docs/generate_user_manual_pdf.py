"""
Generate the BIZORA Accounting Application User Manual PDF.

Run from project root:
    python docs/generate_user_manual_pdf.py

Output:
    docs/BIZORA_User_Manual_v1.0.0.pdf
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

# Allow importing config from project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(DOCS_DIR))

try:
    from manual_pdf_common import add_screenshot
except ImportError:
    def add_screenshot(story, styles, filename, caption, max_width=15.5 * cm):
        """Fallback when manual_pdf_common is unavailable."""
        pass

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
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
    from config import APP_NAME, APP_VERSION, COMPANY_DISPLAY_NAME, APP_DESCRIPTION
except ImportError:
    APP_NAME = "BIZORA"
    APP_VERSION = "1.0.0"
    COMPANY_DISPLAY_NAME = "BIZORA Software Solutions"
    APP_DESCRIPTION = "A modern desktop accounting application"

OUTPUT_FILENAME = f"{APP_NAME}_User_Manual_v{APP_VERSION}.pdf"
OUTPUT_PATH = Path(__file__).resolve().parent / OUTPUT_FILENAME

# Brand colours
BRAND_BLUE = colors.HexColor("#1976D2")
BRAND_DARK = colors.HexColor("#1A1A2E")
BRAND_GREY = colors.HexColor("#555555")
TABLE_HEADER_BG = colors.HexColor("#E3F2FD")
TABLE_ALT_BG = colors.HexColor("#F5F5F5")
BORDER_GREY = colors.HexColor("#CCCCCC")


class ManualDocTemplate(BaseDocTemplate):
    """Custom document template with header, footer, and TOC support."""

    def __init__(self, filename: str, **kwargs):
        super().__init__(filename, **kwargs)
        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="normal",
        )
        cover_frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="cover",
        )
        self.addPageTemplates(
            [
                PageTemplate(id="Cover", frames=[cover_frame], onPage=self._cover_page),
                PageTemplate(id="Content", frames=[frame], onPage=self._content_page),
            ]
        )

    def _cover_page(self, canvas, doc):
        """Minimal cover page — no header/footer."""
        pass

    def _content_page(self, canvas, doc):
        """Draw header line, footer, and page number on content pages."""
        canvas.saveState()
        width, height = A4
        canvas.setStrokeColor(BRAND_BLUE)
        canvas.setLineWidth(0.5)
        canvas.line(doc.leftMargin, height - 45, width - doc.rightMargin, height - 45)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(BRAND_BLUE)
        canvas.drawString(doc.leftMargin, height - 38, f"{APP_NAME} User Manual v{APP_VERSION}")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(BRAND_GREY)
        canvas.drawRightString(
            width - doc.rightMargin,
            height - 38,
            COMPANY_DISPLAY_NAME,
        )
        canvas.setStrokeColor(BORDER_GREY)
        canvas.line(doc.leftMargin, 35, width - doc.rightMargin, 35)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(BRAND_GREY)
        canvas.drawString(doc.leftMargin, 22, f"Generated: {datetime.now().strftime('%d-%m-%Y')}")
        canvas.drawCentredString(width / 2, 22, "Confidential — For Authorized Users Only")
        canvas.drawRightString(width - doc.rightMargin, 22, f"Page {doc.page}")
        canvas.restoreState()

    def afterFlowable(self, flowable):
        """Register TOC entries when headings are encountered."""
        if flowable.__class__.__name__ != "Paragraph":
            return
        style_name = flowable.style.name
        text = flowable.getPlainText()
        if style_name == "ChapterTitle":
            self.notify("TOCEntry", (0, text, self.page))
        elif style_name == "SectionTitle":
            self.notify("TOCEntry", (1, text, self.page))


def build_styles() -> dict:
    """Return named paragraph styles for the manual."""
    base = getSampleStyleSheet()
    return {
        "CoverTitle": ParagraphStyle(
            "CoverTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=32,
            textColor=BRAND_BLUE,
            alignment=TA_CENTER,
            spaceAfter=12,
            leading=38,
        ),
        "CoverSubtitle": ParagraphStyle(
            "CoverSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=16,
            textColor=BRAND_DARK,
            alignment=TA_CENTER,
            spaceAfter=8,
            leading=22,
        ),
        "CoverMeta": ParagraphStyle(
            "CoverMeta",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            textColor=BRAND_GREY,
            alignment=TA_CENTER,
            spaceAfter=6,
            leading=16,
        ),
        "ChapterTitle": ParagraphStyle(
            "ChapterTitle",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=18,
            textColor=BRAND_BLUE,
            spaceBefore=18,
            spaceAfter=10,
            leading=22,
        ),
        "SectionTitle": ParagraphStyle(
            "SectionTitle",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            textColor=BRAND_DARK,
            spaceBefore=14,
            spaceAfter=6,
            leading=17,
        ),
        "SubSectionTitle": ParagraphStyle(
            "SubSectionTitle",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=BRAND_DARK,
            spaceBefore=10,
            spaceAfter=4,
            leading=14,
        ),
        "Body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            textColor=BRAND_DARK,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
            leading=14,
        ),
        "Bullet": ParagraphStyle(
            "Bullet",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            textColor=BRAND_DARK,
            leftIndent=18,
            bulletIndent=8,
            spaceAfter=3,
            leading=13,
        ),
        "Note": ParagraphStyle(
            "Note",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=9,
            textColor=BRAND_GREY,
            leftIndent=12,
            spaceAfter=6,
            leading=12,
        ),
        "Caption": ParagraphStyle(
            "Caption",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=9,
            textColor=BRAND_GREY,
            alignment=TA_CENTER,
            spaceAfter=8,
            leading=12,
        ),
        "TOCTitle": ParagraphStyle(
            "TOCTitle",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=20,
            textColor=BRAND_BLUE,
            spaceAfter=16,
        ),
    }


def make_table(headers: list[str], rows: list[list[str]], col_widths=None) -> Table:
    """Build a styled data table for field descriptions."""
    data = [headers] + rows
    table = Table(data, colWidths=col_widths, repeatRows=1)
    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), BRAND_DARK),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER_GREY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, TABLE_ALT_BG]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    table.setStyle(TableStyle(style_commands))
    return table


def chapter(story: list, styles: dict, title: str) -> None:
    """Add a chapter heading."""
    story.append(Paragraph(title, styles["ChapterTitle"]))


def section(story: list, styles: dict, title: str) -> None:
    """Add a section heading."""
    story.append(Paragraph(title, styles["SectionTitle"]))


def subsection(story: list, styles: dict, title: str) -> None:
    """Add a subsection heading."""
    story.append(Paragraph(title, styles["SubSectionTitle"]))


def body(story: list, styles: dict, text: str) -> None:
    """Add a body paragraph."""
    story.append(Paragraph(text, styles["Body"]))


def bullets(story: list, styles: dict, items: list[str]) -> None:
    """Add a bullet list."""
    for item in items:
        story.append(Paragraph(f"• {item}", styles["Bullet"]))


def note(story: list, styles: dict, text: str) -> None:
    """Add an italic note."""
    story.append(Paragraph(f"Note: {text}", styles["Note"]))


def field_table(story: list, rows: list[list[str]], headers=None) -> None:
    """Add a two-column field description table."""
    hdr = headers or ["Field", "Description"]
    story.append(make_table(hdr, rows, col_widths=[4.5 * cm, 12.5 * cm]))
    story.append(Spacer(1, 8))


def shortcut_table(story: list, rows: list[list[str]]) -> None:
    """Add a keyboard shortcut table."""
    story.append(make_table(["Shortcut", "Action"], rows, col_widths=[3.5 * cm, 13.5 * cm]))
    story.append(Spacer(1, 8))


def build_cover(story: list, styles: dict) -> None:
    """Build the cover page."""
    story.append(Spacer(1, 6 * cm))
    story.append(Paragraph(APP_NAME, styles["CoverTitle"]))
    story.append(Paragraph("Complete User Manual &amp; Reference Guide", styles["CoverSubtitle"]))
    story.append(Spacer(1, 0.8 * cm))
    story.append(Paragraph(f"Version {APP_VERSION}", styles["CoverMeta"]))
    story.append(Paragraph(COMPANY_DISPLAY_NAME, styles["CoverMeta"]))
    story.append(Spacer(1, 1.2 * cm))
    story.append(
        Paragraph(
            "Comprehensive instructions for installation, company setup, masters, "
            "transaction entry, books, reports, GST compliance, settings, users, "
            "backup, and maintenance.",
            styles["CoverMeta"],
        )
    )
    story.append(Spacer(1, 2 * cm))
    story.append(
        Paragraph(
            f"Document date: {datetime.now().strftime('%d %B %Y')}",
            styles["CoverMeta"],
        )
    )
    story.append(NextPageTemplate("Content"))
    story.append(PageBreak())


def build_toc(story: list, styles: dict) -> TableOfContents:
    """Build the table of contents page."""
    story.append(Paragraph("Table of Contents", styles["TOCTitle"]))
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(
            name="TOCLevel0",
            fontName="Helvetica-Bold",
            fontSize=11,
            leftIndent=0,
            spaceBefore=6,
            spaceAfter=2,
            textColor=BRAND_DARK,
        ),
        ParagraphStyle(
            name="TOCLevel1",
            fontName="Helvetica",
            fontSize=10,
            leftIndent=20,
            spaceBefore=2,
            spaceAfter=1,
            textColor=BRAND_GREY,
        ),
    ]
    story.append(toc)
    story.append(PageBreak())
    return toc


def build_chapter_1_intro(story: list, styles: dict) -> None:
    """Chapter 1 — Introduction."""
    chapter(story, styles, "1. Introduction")
    body(
        story,
        styles,
        f"<b>{APP_NAME}</b> is a modern desktop accounting application developed by "
        f"{COMPANY_DISPLAY_NAME}. {APP_DESCRIPTION}. It is designed for Indian businesses "
        "including retail, wholesale, trading, manufacturing, and service sectors. "
        "The application provides complete GST-compliant accounting with multi-company "
        "support, inventory management, financial reporting, and role-based user access.",
    )
    section(story, styles, "1.1 Key Features")
    bullets(
        story,
        styles,
        [
            "Multi-company support (up to 3 companies per installation)",
            "Indian GST compliance — CGST, SGST, IGST, CESS, GSTR-1",
            "Sales, Purchase, Returns, Quotations, Purchase Orders",
            "Cash, Bank, Journal, and Post-Dated Cheque vouchers",
            "Van sales workflow for mobile distribution",
            "Complete chart of accounts and party masters",
            "Product/Service master with barcode support",
            "Books and registers for day-to-day operations",
            "Financial statements — Trial Balance, P&amp;L, Balance Sheet",
            "Barcode label printing and stock checker utility",
            "Automatic backup and financial year-end processing",
            "Dark and Light themes with layout memory",
            "Keyboard-driven data entry for high-speed operation",
            "Role-based users with granular module permissions",
        ],
    )
    section(story, styles, "1.2 Technology &amp; Defaults")
    field_table(
        story,
        [
            ["Application Name", APP_NAME],
            ["Version", APP_VERSION],
            ["Platform", "Windows 10/11 Desktop (PySide6 / Qt)"],
            ["Database", "SQLite (default); MySQL-ready architecture"],
            ["Currency", "Indian Rupee (₹) with 2 decimal places"],
            ["Date Format", "dd-MM-yyyy (e.g., 27-06-2026)"],
            ["Default Window Size", "1200 × 800 pixels (minimum 800 × 600)"],
            ["Default Font", "Segoe UI, size 10"],
            ["Default Theme", "Dark Theme"],
        ],
    )
    section(story, styles, "1.3 Who Should Use This Manual")
    body(
        story,
        styles,
        "This manual is intended for business owners, accountants, data entry operators, "
        "and system administrators who use BIZORA for daily accounting operations. "
        "Administrators should pay special attention to Chapters 15 (Users &amp; Permissions), "
        "16 (Utilities), and 17 (Backup &amp; Maintenance).",
    )


def build_chapter_2_requirements(story: list, styles: dict) -> None:
    """Chapter 2 — System Requirements & Installation."""
    chapter(story, styles, "2. System Requirements &amp; Installation")
    section(story, styles, "2.1 Minimum System Requirements")
    bullets(
        story,
        styles,
        [
            "Operating System: Windows 10 or Windows 11 (64-bit recommended)",
            "Processor: Intel Core i3 or equivalent",
            "Memory (RAM): 4 GB minimum; 8 GB recommended",
            "Storage: 500 MB free disk space for application; additional space for company databases and backups",
            "Display: 1280 × 720 minimum resolution",
            "Printer: Optional — for invoices, reports, and barcode labels",
            "Internet: Optional — for WhatsApp/SMS bill sharing features",
        ],
    )
    section(story, styles, "2.2 Installation Steps")
    bullets(
        story,
        styles,
        [
            "Obtain the BIZORA installer or application package from your authorized distributor.",
            "Run the installer and follow the on-screen prompts.",
            "Choose an installation directory (default is recommended).",
            "Allow the installer to create desktop and Start Menu shortcuts.",
            "Launch BIZORA from the desktop shortcut or Start Menu.",
            "On first launch, the Company Gateway screen appears — proceed to Chapter 3.",
        ],
    )
    section(story, styles, "2.3 First Launch Checklist")
    bullets(
        story,
        styles,
        [
            "Create your first company (File → Create New Company) or open an existing one",
            "Set up the default Admin user password",
            "Configure invoice numbering prefixes (Settings → Invoice Settings)",
            "Enter opening balances for ledgers and stock (Entry → Opening Balance)",
            "Create party masters (Masters → Debtor/Creditor)",
            "Create product masters (Masters → Product/Service)",
            "Configure backup folder (Utilities → Backup and Restore Data)",
            "Set print defaults (Settings → Print Settings or Utilities → Print Settings)",
        ],
    )


def build_chapter_3_gateway(story: list, styles: dict) -> None:
    """Chapter 3 — Company Gateway & Login."""
    chapter(story, styles, "3. Company Gateway &amp; Login")
    body(
        story,
        styles,
        "When you start BIZORA, the <b>Company Gateway</b> appears as a full-screen floating "
        "window. This is your entry point for selecting a company, logging in, and setting "
        "your working date before entering the main workspace.",
    )
    section(story, styles, "3.1 Gateway File Menu")
    field_table(
        story,
        [
            ["Open Companies", "Browse and select an existing company database to work with."],
            ["Create New Company", "Launch the new company wizard. Maximum 3 companies per installation."],
        ],
    )
    section(story, styles, "3.2 Login Card Fields")
    field_table(
        story,
        [
            ["Company Label", "Displays the selected business name, GSTIN, and state (read-only summary)."],
            ["Username", "Dropdown list of users registered in the selected company database."],
            ["Password", "Required. Verified against stored password hash. Press Enter to log in."],
            ["Date", "Working/login date with calendar popup. All transactions use this as the default date."],
            ["Login Button", "Authenticates credentials and opens the main workspace with a loading screen."],
            ["Exit Button", "Closes the application entirely."],
        ],
    )
    section(story, styles, "3.3 Login Keyboard Shortcuts")
    bullets(
        story,
        styles,
        [
            "Username field → Enter: moves focus to Password field",
            "Password field → Enter: triggers Login",
            "Escape: closes the login dialog (where applicable)",
        ],
    )
    section(story, styles, "3.4 Session Information Stored at Login")
    bullets(
        story,
        styles,
        [
            "Active username and role (User or Admin)",
            "Module permissions (comma-separated list or ALL for Admin)",
            "Working date for the session",
            "Active company database connection",
        ],
    )
    note(
        story,
        styles,
        "If you open a previous financial year company in read-only mode, the window title "
        "will show [READ ONLY - PREVIOUS FINANCIAL YEAR]. See Chapter 18 for details.",
    )
    add_screenshot(story, styles, "01_company_gateway.png", "Company Gateway login screen")


def build_chapter_4_main_window(story: list, styles: dict) -> None:
    """Chapter 4 — Main Window Tour."""
    chapter(story, styles, "4. Main Window Tour")
    body(
        story,
        styles,
        "After successful login, BIZORA displays the main workspace. The default view is the "
        "<b>Dashboard</b>, which provides a financial overview. The workspace consists of "
        "four primary areas: Topbar, Shortcut Toolbar, Sidebar, and Central Content Area.",
    )
    section(story, styles, "4.1 Topbar")
    field_table(
        story,
        [
            ["Company Name", "Shows the active company business name."],
            ["Date &amp; Time", "Current system date and time display."],
            ["User Role", "Displays logged-in username and role (User/Admin)."],
            ["Calculator", "Opens an on-screen calculator dialog for quick calculations."],
            ["Log Out", "Ends the session and returns to the Company Gateway."],
        ],
    )
    section(story, styles, "4.2 Shortcut Toolbar")
    body(
        story,
        styles,
        "The shortcut toolbar provides one-click access to frequently used modules with icon "
        "buttons. It also includes a <b>Global Search</b> field (Ctrl+F) that finds menu routes "
        "and settings subsections across the entire application.",
    )
    bullets(
        story,
        styles,
        [
            "Sales (Ctrl+L), Sales Return (Ctrl+R), Purchase (Ctrl+B)",
            "Cash Receipt (Ctrl+T), Cash Payment (Ctrl+M)",
            "Day Book (F6), Cash Book (F7), Ledger (F5)",
            "Stock Report (F9), Price List (F8)",
            "Global Search — type any module or setting name and press Enter",
        ],
    )
    section(story, styles, "4.3 Sidebar Navigation")
    body(
        story,
        styles,
        "The left sidebar uses an accordion-style menu with nine sections. Click a section "
        "header to expand or collapse it. Click any menu item to open the corresponding module. "
        "Many entry screens open in standalone resizable windows.",
    )
    bullets(
        story,
        styles,
        [
            "File — View Company, Close Company",
            "Masters — Account, Debtor/Creditor, Bank Account, Product/Service",
            "Entry — All transaction entry screens (Sales, Purchase, Vouchers, etc.)",
            "Books — Registers and operational books",
            "Reports — Financial and operational reports",
            "Utilities — Barcode, Stock Checker, Backup, Year-End, etc.",
            "Windows — Cascade (listed; not currently implemented)",
            "Settings — General, Tax, Invoice, User, Barcode, Print Settings",
            "About Me — Listed; use File → View Company for company profile",
        ],
    )
    section(story, styles, "4.4 Dashboard (Home Screen)")
    body(
        story,
        styles,
        "The Dashboard is the default home screen showing key business metrics and charts.",
    )
    field_table(
        story,
        [
            ["Net Realized Sale", "Total net sales realized for the current period."],
            ["Total to Give to Creditors", "Outstanding amounts payable to suppliers/creditors."],
            ["Total to Get from Debtors", "Outstanding amounts receivable from customers/debtors."],
            ["Day Credit Sale", "Credit sales recorded for the current working day."],
            ["Monthly Sales Chart", "Bar chart showing month-wise sales trend."],
            ["Monthly Purchases Chart", "Bar chart showing month-wise purchase trend."],
            ["Recent Activity", "Last 5 transactions; auto-refreshes every 15 seconds."],
        ],
    )
    section(story, styles, "4.5 Standalone Module Windows")
    body(
        story,
        styles,
        "Many modules (Sales Entry, Purchase Entry, Masters, etc.) open in separate resizable "
        "windows rather than replacing the Dashboard. Window sizes and positions are remembered "
        "by the UI Memory system (see Chapter 19). You can have multiple module windows open "
        "simultaneously.",
    )
    add_screenshot(story, styles, "02_dashboard.png", "Dashboard home screen with metrics and charts")


def build_chapter_5_company(story: list, styles: dict) -> None:
    """Chapter 7 — Company Setup."""
    chapter(story, styles, "5. Company Setup &amp; Profile")
    section(story, styles, "5.1 Creating a New Company")
    body(
        story,
        styles,
        "Navigate to the Company Gateway → File → Create New Company. A wizard guides you "
        "through company creation. The system allows a maximum of <b>3 companies</b> per installation.",
    )
    subsection(story, styles, "5.1.1 Company Information")
    field_table(
        story,
        [
            ["Business Name *", "Legal or trading name of the business. Required."],
            ["Financial Year *", "Select the active financial year (e.g., 2025-26). Required."],
            ["Phone", "Business contact phone number."],
            ["GSTIN", "15-character GST Identification Number."],
            ["GST Registration Type", "Regular or Composition."],
            ["Email", "Business email address."],
        ],
    )
    subsection(story, styles, "5.1.2 Business Details")
    field_table(
        story,
        [
            ["Business Type", "Retail, Wholesale, Service, Manufacturing, Trading, or Other."],
            ["Business Category", "General, Electronics, Grocery, Textile, Medical, Restaurant, or Other."],
            ["Address", "Full business address (multi-line)."],
            ["State", "Indian state (editable combo with state codes)."],
            ["Pincode", "Postal/ZIP code."],
        ],
    )
    subsection(story, styles, "5.1.3 Uploads")
    field_table(
        story,
        [
            ["Logo", "Company logo for invoices. Formats: PNG, JPG, JPEG, PDF. Max 2 MB."],
            ["Signature", "Authorized signatory image. Same formats and size limit as logo."],
        ],
    )
    section(story, styles, "5.2 View Company (File → View Company)")
    body(
        story,
        styles,
        "Opens a read-only standalone window showing the complete company profile including "
        "Basic Information, Business Details, Address, print visibility toggles for invoice "
        "fields, logo/signature preview, and options to export or print the profile.",
    )
    section(story, styles, "5.3 Close Company (File → Close Company)")
    body(
        story,
        styles,
        "Closes the active company session after confirmation, clears session data, and "
        "returns to the Dashboard. Use this before switching companies or logging out.",
    )
    section(story, styles, "5.4 Financial Year Guard")
    body(
        story,
        styles,
        "All date fields in transaction entry screens are guarded by the Financial Year Guard. "
        "Dates outside the active company's financial year range will trigger a warning and "
        "are clamped to valid dates. This prevents accidental posting to wrong periods.",
    )
    add_screenshot(story, styles, "11_new_company.png", "Create New Company wizard")


def build_chapter_6_keyboard(story: list, styles: dict) -> None:
    """Chapter 6 — Keyboard Navigation Reference."""
    chapter(story, styles, "6. Keyboard Navigation Reference")
    body(
        story,
        styles,
        "BIZORA is designed for high-speed keyboard-driven data entry. The Enter and Escape "
        "keys provide forward and backward navigation through fields. Global shortcuts open "
        "modules instantly from anywhere in the application.",
    )
    section(story, styles, "6.1 Global Action Shortcuts")
    shortcut_table(
        story,
        [
            ["Ctrl+S", "Save — saves the current record/voucher in context modules"],
            ["Ctrl+P", "Print — prints the current document"],
            ["Ctrl+F", "Global Search — search all menu routes and settings"],
            ["Ctrl+N", "New Record — create a new entry in context modules"],
        ],
    )
    section(story, styles, "6.2 Module Navigation Shortcuts")
    shortcut_table(
        story,
        [
            ["Ctrl+L", "Sales Entry"],
            ["Ctrl+R", "Sales Return"],
            ["Ctrl+B", "Purchase Entry"],
            ["Ctrl+U", "Purchase Return"],
            ["Ctrl+Q", "Quotation Entry"],
            ["Ctrl+K", "Purchase Order"],
            ["Ctrl+T", "Cash Receipt"],
            ["Ctrl+M", "Cash Payment"],
            ["Ctrl+I", "Bank Receipt"],
            ["Ctrl+Y", "Bank Payment"],
            ["Ctrl+J", "Journal Entry"],
            ["Ctrl+D", "Post Dated Cheque"],
            ["Ctrl+H", "Credit/Debit Note"],
            ["Ctrl+W", "Van Entry"],
            ["Ctrl+E", "Van Return Entry"],
            ["F5", "Ledger"],
            ["F6", "Day Book"],
            ["F7", "Cash Book"],
            ["F8", "Price List"],
            ["F9", "Stock Report"],
        ],
    )
    section(story, styles, "6.3 Enter / Escape Navigation Rules")
    body(
        story,
        styles,
        "<b>Universal Rule:</b> Enter moves forward to the next field. Escape moves backward "
        "to the previous field. This applies consistently across all data entry screens.",
    )
    subsection(story, styles, "6.3.1 Sales / Purchase / Return Billing Grid")
    bullets(
        story,
        styles,
        [
            "<b>Local GST Enter flow:</b> Product → HSN → CGST → SGST → CESS → Rate → Qty → Gross → Disc",
            "<b>Inter-state Enter flow:</b> Product → HSN → IGST → CESS → Rate → Qty → Gross → Disc",
            "<b>Escape:</b> Reverse of the above column sequence",
            "After the last column (Disc): a new row is created; focus moves to Barcode (if enabled) or Product",
            "<b>Down Arrow in Disc column:</b> Converts the discount value to a percentage of gross amount",
            "<b>Qty Enter:</b> May block entry if stock limit is exceeded (configurable behaviour)",
            "<b>Single mouse click</b> on an editable cell: activates edit mode and selects all text for immediate overwrite",
        ],
    )
    subsection(story, styles, "6.3.2 Cash / Bank Vouchers")
    bullets(
        story,
        styles,
        [
            "Enter/Escape on grid cell widgets moves forward/backward through cells",
            "Tab navigation between header fields follows standard form order",
        ],
    )
    subsection(story, styles, "6.3.3 Opening Balance Grids")
    bullets(
        story,
        styles,
        [
            "Enter → next column; Escape → previous column or previous row",
            "Account selection auto-suggests Dr/Cr based on account type",
        ],
    )
    subsection(story, styles, "6.3.4 Product Master")
    bullets(
        story,
        styles,
        [
            "Enter-key jump order is configurable in Settings → Tax Settings (Product Settings)",
            "Default order follows the visual field layout on the Product Entry form",
        ],
    )
    subsection(story, styles, "6.3.5 Credit / Debit Note")
    bullets(
        story,
        styles,
        [
            "Sequential Enter/Escape across all header fields: Note No → Date → Type → Party → Reason → etc.",
        ],
    )


def build_chapter_7_masters(story: list, styles: dict) -> None:
    """Chapter 7 — Masters Module."""
    chapter(story, styles, "7. Masters Module")
    body(
        story,
        styles,
        "Master data forms the foundation of all accounting transactions. Set up masters "
        "before entering transactions. Access all masters from the sidebar <b>Masters</b> section.",
    )
    section(story, styles, "7.1 Account (Chart of Accounts)")
    body(story, styles, "Path: Masters → Account. Three tabs: Create Account, Account Groups, Account List.")
    subsection(story, styles, "7.1.1 Account Types")
    bullets(
        story,
        styles,
        [
            "Party (Debtor/Creditor)",
            "Cash/Bank Account",
            "Income Account",
            "Expense Account",
            "Tax Liability (GST)",
            "Capital Account",
            "Stock Account",
        ],
    )
    subsection(story, styles, "7.1.2 Create Account Fields")
    field_table(
        story,
        [
            ["Account Name *", "Unique name for the ledger account. Required."],
            ["Account Type *", "Select from the types listed above. Required."],
            ["Group", "Searchable account group (e.g., Salary, Rent, Direct Expenses)."],
            ["Opening Balance", "Numeric opening balance amount."],
            ["Dr/Cr", "Debit or Credit indicator for the opening balance."],
            ["Account Code", "Optional short code for quick reference."],
        ],
    )
    subsection(story, styles, "7.1.3 Account Groups")
    body(story, styles, "Create custom groups via the Account Groups tab. Group Name examples: Salary, Rent, Direct Expenses, Indirect Expenses.")
    subsection(story, styles, "7.1.4 Edit Account")
    field_table(
        story,
        [
            ["Name", "Modify account name."],
            ["Type", "Change account type."],
            ["Group", "Reassign to a different group."],
            ["Opening Balance", "Update opening balance."],
            ["Balance Type", "Dr or Cr."],
            ["Code", "Update account code."],
        ],
    )
    section(story, styles, "7.2 Debtor / Creditor (Party Master)")
    body(story, styles, "Path: Masters → Debtor/Creditor. Two pages: Party Entry and Party List.")
    field_table(
        story,
        [
            ["Party Name *", "Full name of the customer/supplier. Required."],
            ["Code", "Short party code, max 7 characters. Auto-suggested on entry."],
            ["Party Type *", "Debtor (customer), Creditor (supplier), or Both. Required."],
            ["Opening Balance", "Outstanding balance at start of financial year."],
            ["Mobile Number", "Contact mobile for SMS/WhatsApp bill sharing."],
            ["Email", "Contact email address."],
            ["Credit Limit", "Maximum credit allowed for this party."],
            ["GSTIN", "15-character GST Identification Number."],
            ["State", "Indian state (editable combo with all states)."],
            ["Contact Person", "Name of primary contact (auto title-cased)."],
            ["Address", "Full postal address."],
            ["Notes", "Free-text notes about the party."],
        ],
    )
    body(story, styles, "Party List supports filtering, search, and export to PDF, Word, or Excel.")
    section(story, styles, "7.3 Bank Account Master")
    field_table(
        story,
        [
            ["Account Name *", "Display name for this bank account. Required."],
            ["Bank Name *", "Name of the bank institution. Required."],
            ["Account Number *", "Bank account number. Required."],
            ["IFSC Code", "Indian Financial System Code."],
            ["Branch Name", "Bank branch location."],
            ["Opening Balance", "Balance at start of financial year."],
            ["Notes", "Additional notes."],
        ],
    )
    section(story, styles, "7.4 Product / Service Master")
    body(story, styles, "Path: Masters → Product/Service. Pages: Product Entry, Product List, Settings (gear).")
    field_table(
        story,
        [
            ["Product Name *", "Unique product or service name. Required."],
            ["Barcode", "Product barcode with Auto-generate checkbox."],
            ["HSN", "HSN code for GST."],
            ["Color / Size / Unit / Category", "Product attributes."],
            ["Purchase Rate / Sale Price / Wholesale / MRP", "Pricing with margin display."],
            ["CGST / SGST / IGST / CESS %", "Tax rate percentages."],
            ["Reorder Level / Quantity", "Stock management fields."],
            ["Description", "Free-text description."],
        ],
    )
    add_screenshot(story, styles, "06_party_master.png", "Debtor/Creditor party master entry form")
    add_screenshot(story, styles, "05_products_master.png", "Product/Service master entry form")
    add_screenshot(story, styles, "16_account_master.png", "Chart of Accounts master")


def build_chapter_8_entries(story: list, styles: dict) -> None:
    """Chapter 8 — Transaction Entry."""
    chapter(story, styles, "8. Transaction Entry")
    section(story, styles, "8.1 Sales Bill (Ctrl+L)")
    subsection(story, styles, "8.1.1 Header Fields")
    field_table(
        story,
        [
            ["Invoice No", "Auto-generated. ▲▼ navigate bills. Fixed mode for specific numbers."],
            ["Date / Type / Nature", "Date, Cash/Credit, Local/Inter-state GST."],
            ["Form of Sale", "B2B, B2CS, or B2CL."],
            ["Party / Due Date", "Party filter and payment due date (+30 days default)."],
        ],
    )
    subsection(story, styles, "8.1.2 Party Matrix")
    field_table(
        story,
        [
            ["Name / Address / Mobile / GSTIN / State", "Party details with master lookup."],
            ["Narration / Salesman", "Narration text and assigned salesman."],
        ],
    )
    subsection(story, styles, "8.1.3 Product Strip & Grid")
    body(story, styles, "Barcode scan, Product search popup, Rate selector (Sales/Purchase/Wholesale/MRP).")
    body(story, styles, "Grid columns: SL, Product, HSN, CGST%, SGST%, IGST%, CESS%, Rate, Qty, Gross, Disc, Net, Tax, Total.")
    subsection(story, styles, "8.1.4 Footer & Actions")
    field_table(
        story,
        [
            ["Balances", "Opening Bal, Closing Bal, Grand Total, Amt Received, Balance."],
            ["Adjustments", "Freight, Round Off, Discount (Down-arrow = %), Net Amount."],
            ["Tax Summary", "Net Value, CGST, SGST, IGST, Tax Amount, Cess."],
            ["Actions", "Save/Update, Print, WhatsApp, SMS, Reset All, Remove Item, Remove Bill, Export PDF."],
        ],
    )
    note(story, styles, "Cash Tender dialog appears after save if enabled in Invoice Settings.")
    add_screenshot(story, styles, "03_sales_entry.png", "Sales Bill entry screen")
    section(story, styles, "8.2 Purchase Bill (Ctrl+B)")
    bullets(
        story,
        styles,
        [
            "Title: PURCHASE BILL; Purchase No instead of Invoice No",
            "Creditor-focused party matrix with Code field and Creditor button",
            "Import PO button to import from Purchase Order",
            "Grid includes Sales Rate column (15 columns total)",
            "Checkbox: Entry with Specific Purchase No.",
        ],
    )
    add_screenshot(story, styles, "04_purchase_entry.png", "Purchase Bill entry screen")
    section(story, styles, "8.3 Sales Return (Ctrl+R) & Purchase Return (Ctrl+U)")
    body(story, styles, "Same UI patterns as parent entry with return-specific columns and rate handling.")
    section(story, styles, "8.4 Quotation (Ctrl+Q)")
    body(story, styles, "Full quotation entry. Can convert to Sales Bill when accepted by customer.")
    section(story, styles, "8.5 Purchase Order (Ctrl+K)")
    body(story, styles, "PO entry screen. Importable into Purchase Bill via Import PO button.")
    section(story, styles, "8.6 Cash & Bank Vouchers")
    body(story, styles, "Cash Receipt (Ctrl+T), Cash Payment (Ctrl+M), Bank Receipt (Ctrl+I), Bank Payment (Ctrl+Y).")
    field_table(
        story,
        [
            ["Tabs", "General A/C | Debtor A/C | Creditor A/C | Bill Receipt/Payment"],
            ["Voucher No", "Auto-numbered with ▲▼ navigation."],
            ["Date", "Voucher date."],
            ["Cash/Bank Account", "Searchable combo with current balance display."],
            ["Remark", "Voucher narration."],
            ["Grid", "SL No, Account, Towards V.No., Amount (+ discount on receipts)."],
        ],
    )
    add_screenshot(story, styles, "10_cash_receipt.png", "Cash Receipt voucher entry")
    section(story, styles, "8.7 Journal Entry (Ctrl+J)")
    field_table(
        story,
        [
            ["Voucher No / Date / Remark", "Header fields with ▲▼ navigation."],
            ["Lines Table", "Account (searchable), Debit, Credit, Narration."],
            ["Actions", "Add Line, Delete Line, Save, Navigate ▲▼."],
        ],
    )
    section(story, styles, "8.8 Post Dated Cheque (Ctrl+D)")
    body(story, styles, "Tabs: Receipt | Issue. Fields: party, bank, cheque number, dates, amounts. Due-date alerts. View in PDC Book.")
    section(story, styles, "8.9 Credit / Debit Note (Ctrl+H)")
    body(story, styles, "Memo-only entry (no ledger/stock posting). Reason options:")
    bullets(
        story,
        styles,
        [
            "Deficit/Damage on goods purchased / sold",
            "Discount on purchases / sales",
            "Purchase/Sales price variation",
            "Purchase return / Sales return",
        ],
    )
    section(story, styles, "8.10 Van Entry (Ctrl+W) & Van Return (Ctrl+E)")
    body(story, styles, "Mobile van stock load and return. Van Entry can convert to Sales Bill.")
    section(story, styles, "8.11 Opening Balance & Opening Stock")
    body(story, styles, "Entry → Opening Balance (same page for stock tab).")
    field_table(
        story,
        [
            ["Ledger Tab", "SL, Ledger, Dr/Cr, Amount, Narration"],
            ["Stock Tab", "SL, Barcode, Product, Qty, Rate, Value"],
        ],
    )
    section(story, styles, "8.12 Stock Adjustment")
    body(story, styles, "Stock quantity adjustments using billing-style product grid.")


def build_chapter_9_books(story: list, styles: dict) -> None:
    """Chapter 9 — Books & Registers."""
    chapter(story, styles, "9. Books &amp; Registers")
    body(story, styles, "Books provide read-only registers of all transactions. Most books support date filters, export, and double-click to open source voucher for editing.")
    section(story, styles, "9.1 Core Accounts")
    field_table(
        story,
        [
            ["Day Book (F6)", "All vouchers chronologically for a date range."],
            ["Cash Book (F7)", "Cash account movements."],
            ["Ledger (F5)", "Account-wise ledger with Type filter (General/Cash&Bank/Debtors/Creditors), date range, summary or detail view. Export Excel/PDF."],
            ["Ledger Statement", "Party/account statement format."],
        ],
    )
    section(story, styles, "9.2 Sales & Returns Books")
    field_table(
        story,
        [
            ["Sales Book", "All sales invoices. Double-click to edit."],
            ["Sales Return Book", "Sales return register."],
            ["Bill History", "Customer-wise bill history."],
            ["Cash Tender History", "Cash tender payment records."],
            ["Sales Wise Profit", "Profit analysis per sale."],
        ],
    )
    section(story, styles, "9.3 Purchases & Returns Books")
    field_table(
        story,
        [
            ["Purchase Book", "All purchase bills. Double-click to edit."],
            ["Purchase Return Book", "Purchase return register."],
            ["Purchase Order Book", "Open and closed purchase orders."],
        ],
    )
    section(story, styles, "9.4 Other Books")
    field_table(
        story,
        [
            ["Quotation Book", "All quotations."],
            ["Stock Report (F9)", "Current stock levels."],
            ["Daily Stock Register", "Day-wise stock movement."],
            ["Price List (F8)", "Product rates."],
            ["GST Sales/Purchase Reports", "GST compliance registers."],
            ["GSTR-1", "GSTR-1 export."],
            ["Journal Book", "Journal vouchers."],
            ["PDC Book", "Post-dated cheques."],
            ["Monthly Analysis", "Period analysis."],
        ],
    )
    add_screenshot(story, styles, "07_ledger.png", "Ledger report with filters")
    add_screenshot(story, styles, "08_day_book.png", "Day Book chronological register")
    add_screenshot(story, styles, "17_sales_book.png", "Sales Book invoice register")


def build_chapter_10_reports(story: list, styles: dict) -> None:
    """Chapter 10 — Reports."""
    chapter(story, styles, "10. Reports")
    section(story, styles, "10.1 Financial Statements")
    field_table(
        story,
        [
            ["Trial Balance", "Ledger balances with Opening/Period/Closing Dr/Cr. Filters: date range, type, search."],
            ["Profit and Loss Account", "Income and expense statement for a period."],
            ["Balance Sheet", "Assets and liabilities as of date."],
        ],
    )
    section(story, styles, "10.2 Operational Reports")
    field_table(
        story,
        [
            ["Daily Collection Report", "Daily collection summary."],
            ["Stock Value", "Inventory valuation."],
            ["Best Sellers", "Top products by sales."],
            ["Salesman Record Book", "Salesman-wise records."],
        ],
    )
    add_screenshot(story, styles, "09_trial_balance.png", "Trial Balance financial report")


def build_chapter_11_gst(story: list, styles: dict) -> None:
    """Chapter 11 — GST."""
    chapter(story, styles, "11. GST Compliance")
    bullets(
        story,
        styles,
        [
            "Local GST: CGST + SGST on intra-state transactions",
            "Inter-state: IGST on inter-state transactions",
            "Form of Sale: B2B, B2CS, B2CL classification",
            "HSN codes on line items from product master",
            "GST Sales Report, GST Purchase Report, GSTR-1 export",
        ],
    )
    add_screenshot(story, styles, "18_gst_sales_report.png", "GST Sales Report")


def build_chapter_12_settings(story: list, styles: dict) -> None:
    """Chapter 12 — Settings."""
    chapter(story, styles, "12. Settings &amp; Configuration")
    section(story, styles, "12.1 General Settings")
    field_table(
        story,
        [
            ["Theme", "Dark (default) or Light with live preview."],
            ["Bold Fonts", "Toggle bold text across the application."],
            ["Reset Layouts", "Restore default window sizes and column widths."],
        ],
    )
    section(story, styles, "12.2 Invoice Settings")
    field_table(
        story,
        [
            ["Cash Tender", "Show payment dialog after sales save."],
            ["Invoice Numbering", "Prefix + entry type per voucher; 3-digit sequence."],
            ["Debug Mode", "Enable console debug output."],
            ["Confirm Delete", "Confirm before deleting transactions."],
        ],
    )
    section(story, styles, "12.3 Print & Barcode Settings")
    field_table(
        story,
        [
            ["Print Format", "A4 or Thermal."],
            ["Print Theme", "Classic or Modern Pink."],
            ["Header/Footer Text", "Quotes, offers, terms and conditions."],
            ["Barcode", "Label size, printer, offsets, live preview."],
        ],
    )
    note(story, styles, "Tax Settings opens Product Enter-navigation settings, not GST rate config.")
    add_screenshot(story, styles, "12_invoice_settings.png", "Invoice Settings screen")
    add_screenshot(story, styles, "13_general_settings.png", "General Settings — theme and layout")


def build_chapter_13_users(story: list, styles: dict) -> None:
    """Chapter 13 — Users."""
    chapter(story, styles, "13. Users &amp; Permissions")
    body(story, styles, "Admin role has ALL permissions. User role requires explicit module checkboxes.")
    field_table(
        story,
        [
            ["Sales", "Sales, Returns, Van, Credit/Debit Note"],
            ["Purchases", "Purchase, Returns, PO"],
            ["Quotations", "Quotation entry"],
            ["Payments", "Cash/Bank Payment, PDC, Journal"],
            ["Receipts", "Cash/Bank Receipt"],
            ["Reports", "All books and reports"],
            ["Settings", "Opening balance, utilities, backup, settings"],
        ],
        headers=["Permission", "Modules Covered"],
    )
    bullets(story, styles, ["Add/Update/Delete User", "Force Reset Password", "Manage via Utilities → Manage Users"])
    add_screenshot(story, styles, "15_user_management.png", "User Management and permissions dialog")


def build_chapter_14_utilities(story: list, styles: dict) -> None:
    """Chapter 14 — Utilities."""
    chapter(story, styles, "14. Utilities")
    field_table(
        story,
        [
            ["Barcode", "Print queue and label manager."],
            ["Stock Checker", "Physical stock audit with barcode scan."],
            ["System Diagnostics", "Health checks."],
            ["Audit Logs", "Change audit trail."],
            ["Inter-Company Transfer", "Move data between companies."],
            ["Close Financial Year", "Lock FY and create new database."],
            ["Compact and Repair", "VACUUM, REINDEX, integrity check."],
        ],
    )


def build_chapter_15_backup(story: list, styles: dict) -> None:
    """Chapter 15 — Backup."""
    chapter(story, styles, "15. Backup, Restore &amp; Maintenance")
    section(story, styles, "15.1 Backup Settings")
    field_table(
        story,
        [
            ["Backup Folder Path", "Target directory for backup files."],
            ["Auto-Backup on Close", "Automatic backup when application closes."],
            ["Run Manual Backup Now", "Immediate backup of company database."],
            ["Restore from Backup", "DANGER: Overwrites all data. Restore scheduled on restart."],
        ],
    )
    add_screenshot(story, styles, "14_backup_restore.png", "Backup and Restore Data dialog")
    section(story, styles, "15.2 Compact and Repair")
    body(story, styles, "Runs PRAGMA integrity_check, REINDEX, and VACUUM. Reports database size before/after and space saved.")
    section(story, styles, "15.3 Close Financial Year")
    bullets(
        story,
        styles,
        [
            "Locks current financial year database",
            "Creates new company database with carried-forward balances",
            "Requires re-login to new financial year",
            "Application closes after completion",
        ],
    )


def build_chapter_16_ui(story: list, styles: dict) -> None:
    """Chapter 16 — UI Features."""
    chapter(story, styles, "16. UI Features &amp; Preferences")
    section(story, styles, "16.1 UI Memory")
    body(
        story,
        styles,
        "BIZORA remembers your layout preferences automatically:",
    )
    bullets(
        story,
        styles,
        [
            "Main window geometry and splitter state",
            "Standalone module window sizes and positions",
            "QTableWidget column widths and order",
            "Reset via General Settings or Invoice Settings → Reset Layouts",
        ],
    )
    section(story, styles, "16.2 Themes")
    bullets(story, styles, ["Dark Theme (default)", "Modern Light Theme", "Bold font toggle", "Live preview in settings"])
    section(story, styles, "16.3 Global Search (Ctrl+F)")
    body(story, styles, "Search all menu routes and settings subsections: Theme, Font, Layout, Cash Tender, Invoice Numbering, etc.")
    section(story, styles, "16.4 Calculator")
    body(story, styles, "Topbar calculator button opens an on-screen calculator.")


def build_chapter_17_readonly(story: list, styles: dict) -> None:
    """Chapter 17 — Read-Only Mode."""
    chapter(story, styles, "17. Read-Only Previous Financial Year Mode")
    body(
        story,
        styles,
        "When opening a previous financial year company, the application enters read-only mode. "
        "Window title shows: [READ ONLY - PREVIOUS FINANCIAL YEAR].",
    )
    section(story, styles, "17.1 Allowed in Read-Only Mode")
    bullets(
        story,
        styles,
        [
            "View Company, Close Company",
            "All Books: Day Book, Cash Book, Ledger, Sales/Purchase Books, etc.",
            "All Reports: Trial Balance, P&amp;L, Balance Sheet, GST reports",
            "Stock Report, Price List, Bill History",
        ],
    )
    section(story, styles, "17.2 Blocked in Read-Only Mode")
    bullets(
        story,
        styles,
        [
            "All Entry screens (Sales, Purchase, Vouchers, etc.)",
            "Master data creation/editing",
            "Settings changes, Backup restore, Year-end",
        ],
    )


def build_chapter_18_troubleshooting(story: list, styles: dict) -> None:
    """Chapter 18 — Troubleshooting & Glossary."""
    chapter(story, styles, "18. Troubleshooting &amp; Glossary")
    section(story, styles, "18.1 Common Issues")
    field_table(
        story,
        [
            ["Application Not Responding", "Heavy data loading — wait for processEvents. Reduce date range in reports."],
            ["Cannot Save Transaction", "Check financial year date guard. Verify required fields. Check user permissions."],
            ["Stock Limit Exceeded", "Product stock insufficient. Adjust stock or disable limit check."],
            ["Login Failed", "Verify username/password. Contact Admin for password reset."],
            ["Backup Failed", "Check backup folder path exists and is writable."],
            ["Print Not Working", "Verify printer in Print Settings. Check default format (A4/Thermal)."],
        ],
    )
    section(story, styles, "18.2 Glossary")
    field_table(
        story,
        [
            ["Debtor", "Customer who owes money to your business (Accounts Receivable)."],
            ["Creditor", "Supplier to whom your business owes money (Accounts Payable)."],
            ["B2B", "Business-to-Business sale (registered GST customer)."],
            ["B2CS", "Business-to-Consumer Small (unregistered, below threshold)."],
            ["B2CL", "Business-to-Consumer Large (unregistered, above threshold)."],
            ["CGST", "Central Goods and Services Tax (intra-state)."],
            ["SGST", "State Goods and Services Tax (intra-state)."],
            ["IGST", "Integrated GST (inter-state)."],
            ["HSN", "Harmonized System of Nomenclature — product classification code."],
            ["GSTIN", "GST Identification Number (15 characters)."],
            ["FY", "Financial Year (April to March in India)."],
            ["PDC", "Post-Dated Cheque — cheque with future date."],
            ["ITC", "Input Tax Credit — GST paid on purchases."],
            ["MRP", "Maximum Retail Price."],
            ["PO", "Purchase Order."],
            ["WAL", "Write-Ahead Logging — SQLite journal mode for performance."],
        ],
    )


def build_chapter_20_workflows(story: list, styles: dict) -> None:
    """Chapter 20 — Step-by-Step Workflows."""
    chapter(story, styles, "20. Step-by-Step Workflows")
    section(story, styles, "20.1 Daily Sales Entry Workflow")
    bullets(
        story,
        styles,
        [
            "1. Press Ctrl+L or click Entry → Sales from sidebar",
            "2. Verify Date and set Type (Cash/Credit) and Nature (Local/Inter-state)",
            "3. Enter Party Name (type and press Enter to search, or use Debtors button)",
            "4. Enable Barcode tick if scanning; scan barcode or type product name",
            "5. Verify Rate, enter Qty — press Enter through grid columns",
            "6. Add more line items; adjust Freight, Discount, Round Off if needed",
            "7. Review Tax Summary and Grand Total",
            "8. Press Ctrl+S or click Save/Update",
            "9. Complete Cash Tender dialog if enabled",
            "10. Press Ctrl+P to print invoice",
        ],
    )
    section(story, styles, "20.2 New Company Setup Workflow")
    bullets(
        story,
        styles,
        [
            "1. Company Gateway → File → Create New Company",
            "2. Fill Business Name, Financial Year, GSTIN, State",
            "3. Select Business Type and Category",
            "4. Upload Logo and Signature (optional)",
            "5. Click Create — default Admin user is created",
            "6. Login with Admin credentials",
            "7. Settings → Invoice Settings — configure prefixes",
            "8. Masters → Account — verify default accounts",
            "9. Masters → Debtor/Creditor — add parties",
            "10. Masters → Product/Service — add products with HSN and tax rates",
            "11. Entry → Opening Balance — enter ledger and stock opening balances",
            "12. Utilities → Backup — set backup folder and enable auto-backup",
        ],
    )
    section(story, styles, "20.3 Purchase with PO Import Workflow")
    bullets(
        story,
        styles,
        [
            "1. Entry → Purchase Order — create PO with supplier and items",
            "2. Save the Purchase Order",
            "3. Entry → Purchase — open Purchase Bill",
            "4. Select the Creditor (supplier)",
            "5. Click Import PO — select the purchase order",
            "6. Verify imported line items and rates",
            "7. Save the Purchase Bill",
        ],
    )
    section(story, styles, "20.4 Quotation to Sales Conversion")
    bullets(
        story,
        styles,
        [
            "1. Entry → Quotation — create quotation with customer and items",
            "2. Save quotation",
            "3. When customer accepts, use Convert to Sales Bill option",
            "4. Review and save as Sales Invoice",
        ],
    )
    section(story, styles, "20.5 Van Sales Workflow")
    bullets(
        story,
        styles,
        [
            "1. Entry → Van Entry — load stock onto van with products and quantities",
            "2. Save van load entry",
            "3. During route sales, convert Van Entry to Sales Bill",
            "4. Entry → Van Return Entry — return unsold stock at end of day",
        ],
    )
    section(story, styles, "20.6 Month-End Reporting Workflow")
    bullets(
        story,
        styles,
        [
            "1. Books → Day Book — verify all vouchers for the month",
            "2. Reports → Trial Balance — run for month date range",
            "3. Reports → Profit and Loss Account — review income/expenses",
            "4. Books → GST Sales Report and GST Purchase Report",
            "5. Books → GSTR-1 — export for GST filing",
            "6. Reports → Balance Sheet — verify assets/liabilities",
            "7. Utilities → Backup — run manual backup before month close",
        ],
    )
    section(story, styles, "20.7 Year-End Closing Workflow")
    bullets(
        story,
        styles,
        [
            "1. Complete all pending entries for the financial year",
            "2. Run Trial Balance and verify balances",
            "3. Run manual backup (Utilities → Backup and Restore Data)",
            "4. Utilities → Close Financial Year (Year-End)",
            "5. Confirm year-end process — current DB is locked",
            "6. New FY database is created with carried-forward balances",
            "7. Re-login to the new financial year company",
        ],
    )


def build_chapter_21_permissions(story: list, styles: dict) -> None:
    """Chapter 21 — Permission Matrix."""
    chapter(story, styles, "21. Appendix — Permission Matrix")
    body(story, styles, "The following table maps each menu route to required user permission tokens:")
    perm_rows = [
        ["Sales, Sales Return, Van Entry, Van Return", "sales"],
        ["Purchase, Purchase Return, Purchase Order", "purchases"],
        ["Quotation", "quotations"],
        ["Cash Payment, Bank Payment, PDC, Journal", "payments"],
        ["Cash Receipt, Bank Receipt", "receipts"],
        ["Credit/Debit Note", "sales + purchases"],
        ["All Books (Day Book, Ledger, Sales Book, etc.)", "reports"],
        ["All Reports (Trial Balance, P&amp;L, Balance Sheet)", "reports"],
        ["GST Reports, GSTR-1", "reports"],
        ["Opening Balance, Stock Adjustment", "settings"],
        ["All Settings screens", "settings"],
        ["Backup, Year-End, Compact, Audit Logs", "settings"],
        ["Barcode, Stock Checker, System Diagnostics", "settings"],
        ["File → View Company, Close Company", "No permission required"],
        ["Masters (Account, Party, Bank, Product)", "No permission required"],
    ]
    story.append(make_table(["Module Group", "Required Permission"], perm_rows, col_widths=[9 * cm, 8 * cm]))
    story.append(Spacer(1, 8))
    note(story, styles, "Admin role bypasses all permission checks. Users with ALL permission string also have unrestricted access.")


def build_chapter_22_readonly_routes(story: list, styles: dict) -> None:
    """Chapter 22 — Read-Only Allowed Routes."""
    chapter(story, styles, "22. Appendix — Read-Only Mode Allowed Routes")
    body(story, styles, "When viewing a previous financial year, these routes remain accessible:")
    routes = sorted([
        "View Company", "Close Company", "Day Book", "Cash Book", "Ledger",
        "Ledger Statement", "Bill History", "Cash Tender History",
        "Sales Book", "Sales Return Book", "Purchase Book", "Purchase Return Book",
        "Purchase Order Book", "Quotation Book", "Journal Book", "PDC Book",
        "Daily Stock Register", "Price List", "Stock Report", "Sales Wise Profit",
        "Monthly Analysis", "GST Sales Report", "GST Purchase Report", "GSTR-1",
        "Daily Collection Report", "Best Sellers (Top Products)", "Salesman Record Book",
        "Trial Balance", "Profit and Loss Account", "Balance Sheet", "Stock Value",
        "Stock Checker", "System Diagnostics", "Audit Logs", "Print Settings", "Barcode",
    ])
    for i in range(0, len(routes), 2):
        pair = routes[i:i + 2]
        row = [[pair[0], pair[1] if len(pair) > 1 else ""]]
        story.append(make_table(["Route", "Route"], row, col_widths=[8.5 * cm, 8.5 * cm]))
    story.append(Spacer(1, 8))


def build_chapter_23_quick_ref(story: list, styles: dict) -> None:
    """Chapter 23 — Quick Reference Card."""
    chapter(story, styles, "23. Quick Reference Card")
    section(story, styles, "23.1 Essential Shortcuts")
    shortcut_table(
        story,
        [
            ["Ctrl+L", "Sales"], ["Ctrl+B", "Purchase"], ["Ctrl+S", "Save"],
            ["Ctrl+P", "Print"], ["Ctrl+F", "Search"], ["F5", "Ledger"],
            ["F6", "Day Book"], ["F7", "Cash Book"], ["F9", "Stock Report"],
            ["Enter", "Next field"], ["Escape", "Previous field"],
        ],
    )
    section(story, styles, "23.2 Support & Document Information")
    field_table(
        story,
        [
            ["Application", f"{APP_NAME} v{APP_VERSION}"],
            ["Publisher", COMPANY_DISPLAY_NAME],
            ["Database", "SQLite (per-company files)"],
            ["Max Companies", "3 per installation"],
            ["Currency / Date", "INR (₹) / dd-MM-yyyy"],
            ["Document Version", APP_VERSION],
            ["Generated", datetime.now().strftime("%d-%m-%Y")],
        ],
    )
    body(
        story,
        styles,
        "For technical support, contact your authorized BIZORA distributor or system administrator. "
        "Always maintain regular backups before performing year-end closing or restore operations.",
    )


def build_chapter_19_appendix(story: list, styles: dict) -> None:
    """Chapter 19 — Complete Menu Index."""
    chapter(story, styles, "19. Appendix — Complete Menu Index")
    from bizora_core.navigation_catalog import NAVIGATION_MENU

    for section_name, items in NAVIGATION_MENU.items():
        section(story, styles, f"19.{list(NAVIGATION_MENU.keys()).index(section_name) + 1} {section_name}")
        rows = []
        for item in items:
            if item.startswith("--"):
                rows.append([item.strip("- ").strip(), "(Category divider — not clickable)"])
            else:
                rows.append([item, "Click to open module"])
        story.append(make_table(["Menu Item", "Description"], rows, col_widths=[6 * cm, 11 * cm]))
        story.append(Spacer(1, 6))


def build_manual() -> str:
    """Build the complete user manual PDF and return output path."""
    styles = build_styles()
    story: list = []

    build_cover(story, styles)
    build_toc(story, styles)

    builders = [
        build_chapter_1_intro,
        build_chapter_2_requirements,
        build_chapter_3_gateway,
        build_chapter_4_main_window,
        build_chapter_5_company,
        build_chapter_6_keyboard,
        build_chapter_7_masters,
        build_chapter_8_entries,
        build_chapter_9_books,
        build_chapter_10_reports,
        build_chapter_11_gst,
        build_chapter_12_settings,
        build_chapter_13_users,
        build_chapter_14_utilities,
        build_chapter_15_backup,
        build_chapter_16_ui,
        build_chapter_17_readonly,
        build_chapter_18_troubleshooting,
        build_chapter_19_appendix,
        build_chapter_20_workflows,
        build_chapter_21_permissions,
        build_chapter_22_readonly_routes,
        build_chapter_23_quick_ref,
    ]
    for builder in builders:
        builder(story, styles)
        story.append(PageBreak())

    doc = ManualDocTemplate(
        str(OUTPUT_PATH),
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2.2 * cm,
        bottomMargin=2 * cm,
        title=f"{APP_NAME} User Manual",
        author=COMPANY_DISPLAY_NAME,
    )
    doc.multiBuild(story)
    return str(OUTPUT_PATH)


def main() -> None:
    """Entry point for manual PDF generation."""
    os.makedirs(OUTPUT_PATH.parent, exist_ok=True)
    output = build_manual()
    print(f"User manual generated successfully:")
    print(f"  {output}")
    print(f"  Size: {os.path.getsize(output):,} bytes")


if __name__ == "__main__":
    main()
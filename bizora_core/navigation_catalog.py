"""
Central navigation catalog for sidebar menus and global search.

Keeping menu definitions in one place ensures the topbar search index stays
aligned with sidebar routes.
"""

from __future__ import annotations

# Section name -> list of route labels (dividers use "-- title --" format).
NAVIGATION_MENU: dict[str, list[str]] = {
    "File": ["View Company", "Close Company"],
    "Masters": [
        "Account",
        "Debtor/Creditor",
        "Bank Account",
        "Product/Service",
    ],
    "Entry": [
        "Sales",
        "Sales Return",
        "Purchase",
        "Purchase Return",
        "Quotation",
        "Purchase Order",
        "Cash Receipt",
        "Cash Payment",
        "Bank Receipt",
        "Bank Payment",
        "Post Dated Cheque",
        "Journal Entry",
        "Credit/Debit Note",
        "Van Entry",
        "Van Return Entry",
        "Opening Balance",
        "Opening Stock Entry",
        "Stock Adjustment",
    ],
    "Books": [
        "-- Core Accounts --",
        "Day Book",
        "Cash Book",
        "Ledger",
        "Ledger Statement",
        "-- Sales & Returns --",
        "Sales Book",
        "Sales Return Book",
        "Bill History",
        "Cash Tender History",
        "Sales Wise Profit",
        "-- Purchases & Returns --",
        "Purchase Book",
        "Purchase Return Book",
        "Purchase Order Book",
        "-- Quotations --",
        "Quotation Book",
        "-- Stock & Inventory --",
        "Stock Report",
        "Daily Stock Register",
        "Price List",
        "-- Tax & Compliance --",
        "GST Sales Report",
        "GST Purchase Report",
        "GSTR-1",
        "-- Misc Financials --",
        "Journal Book",
        "PDC Book",
        "Monthly Analysis",
    ],
    "Reports": [
        "-- Core Financials --",
        "Trial Balance",
        "Profit and Loss Account",
        "Balance Sheet",
        "-- Operations --",
        "Daily Collection Report",
        "Stock Value",
        "Best Sellers (Top Products)",
        "Salesman Record Book",
    ],
    "Utilities": [
        "Barcode",
        "Stock Checker",
        "System Diagnostics",
        "Print Settings",
        "Audit Logs",
        "Manage Users",
        "Backup and Restore Data",
        "Inter-Company Transfer",
        "Close Financial Year (Year-End)",
        "Compact and Repair Data",
    ],
    "Settings": [
        "General Settings",
        "Tax Settings",
        "Invoice Settings",
        "User Settings",
        "Barcode Settings",
        "Print Settings",
    ],
    "About Me": ["About Me"],
}

# Nested settings panes searchable from the topbar.
SETTINGS_SUBSECTIONS: tuple[dict[str, str], ...] = (
  {
      "label": "Color Mode",
      "parent_route": "General Settings",
      "section_id": "color_mode",
      "keywords": (
          "color mode",
          "theme selection",
          "theme",
          "dark",
          "light",
          "appearance",
      ),
  },
  {
      "label": "Font Settings",
      "parent_route": "General Settings",
      "section_id": "font_settings",
      "keywords": ("font settings", "font", "bold font", "bold fonts"),
  },
  {
      "label": "Time Format",
      "parent_route": "General Settings",
      "section_id": "time_format",
      "keywords": ("time format", "12 hour", "24 hour", "clock", "am pm"),
  },
  {
      "label": "Window & Layout",
      "parent_route": "General Settings",
      "section_id": "layout_memory",
      "keywords": ("window layout", "layout memory", "reset layouts", "window & layout"),
  },
  {
      "label": "Cash Tender",
      "parent_route": "Invoice Settings",
      "section_id": "cash_tender",
      "keywords": ("cash tender",),
  },
  {
      "label": "Invoice Numbering",
      "parent_route": "Invoice Settings",
      "section_id": "invoice_numbering",
      "keywords": ("invoice numbering", "invoice prefix", "voucher prefix", "numbering"),
  },
  {
      "label": "Other Options",
      "parent_route": "Invoice Settings",
      "section_id": "other_options",
      "keywords": ("other options", "debug mode", "confirm delete"),
  },
  {
      "label": "Invoice Window & Layout",
      "parent_route": "Invoice Settings",
      "section_id": "layout_memory",
      "keywords": ("invoice layout", "invoice window layout"),
  },
)


def is_category_divider(label: str) -> bool:
    """Return True when a menu label is a non-clickable divider."""
    return label.startswith("--") and label.endswith("--")


def normalize_route_name(label: str) -> str:
    """Map a visible sidebar label to the route name used by MainWindow."""
    if label == "Debtor/Creditor":
        return "Debitor/Creditor"
    return label


def iter_navigation_routes() -> list[tuple[str, str]]:
    """
    Return (section_name, route_name) pairs for every clickable sidebar route.
    """
    routes: list[tuple[str, str]] = []
    for section_name, items in NAVIGATION_MENU.items():
        for item in items:
            if is_category_divider(item):
                continue
            routes.append((section_name, normalize_route_name(item)))
    return routes


def routes_for_section(section_name: str) -> list[str]:
    """Return clickable route names for one sidebar section."""
    items = NAVIGATION_MENU.get(section_name, [])
    return [
        normalize_route_name(item)
        for item in items
        if not is_category_divider(item)
    ]

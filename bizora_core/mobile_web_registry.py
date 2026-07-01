"""
Mobile web route registry for Books and Reports sidebar menus.

Maps desktop sidebar labels to API slugs, filter schemas, and handler types.
"""

from __future__ import annotations

import re
from typing import Any

from bizora_core.navigation_catalog import NAVIGATION_MENU

STANDARD_DATE_FILTERS: tuple[dict[str, Any], ...] = (
    {"key": "from_date", "label": "From Date", "type": "date", "required": True},
    {"key": "to_date", "label": "To Date", "type": "date", "required": True},
)

SEARCH_FILTER = {"key": "search", "label": "Search", "type": "text", "required": False}

VOUCHER_BOOK_MODES: tuple[dict[str, str], ...] = (
    {"label": "Bill Wise", "method": "get_bill_wise"},
    {"label": "Item Wise", "method": "get_item_wise"},
    {"label": "Tax Wise", "method": "get_tax_wise"},
    {"label": "Tax Summary", "method": "get_tax_summary"},
    {"label": "Credit / Pending", "method": "get_credit_or_pending"},
    {"label": "Party Wise", "method": "get_party_wise"},
    {"label": "Category Wise", "method": "get_category_wise"},
)

VOUCHER_BOOK_FILTERS: tuple[dict[str, Any], ...] = STANDARD_DATE_FILTERS + (
    {
        "key": "report_mode",
        "label": "Report Mode",
        "type": "select",
        "required": True,
        "options": [mode["label"] for mode in VOUCHER_BOOK_MODES],
        "default": "Bill Wise",
    },
    SEARCH_FILTER,
    {"key": "party", "label": "Party", "type": "text", "required": False},
    {"key": "product", "label": "Product", "type": "text", "required": False},
    {"key": "category", "label": "Category", "type": "text", "required": False},
    {"key": "gst", "label": "GST %", "type": "number", "required": False},
)

ACCOUNT_TYPE_FILTER = {
    "key": "account_type",
    "label": "Account Type",
    "type": "select",
    "required": False,
    "options": [
        "All",
        "Cash/Bank",
        "Party",
        "Income",
        "Expense",
        "Tax",
        "Capital",
        "Stock",
        "Asset",
        "Liability",
    ],
    "default": "All",
}

LEDGER_VIEW_FILTER = {
    "key": "ledger_view",
    "label": "Ledger View",
    "type": "select",
    "required": True,
    "options": ["General", "Debtors", "Creditors", "Cash/Bank"],
    "default": "General",
}


def slugify_route_label(label: str) -> str:
    """Convert a sidebar label into a stable API slug."""
    text = re.sub(r"^--+|--+?$", "", label.strip()).strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text.lower()


def _route(
    title: str,
    section: str,
    handler: str,
    *,
    filters: tuple[dict[str, Any], ...] | None = None,
    modes: tuple[dict[str, str], ...] | None = None,
    logic_key: str | None = None,
) -> dict[str, Any]:
    """Build one mobile route definition."""
    return {
        "slug": slugify_route_label(title),
        "title": title,
        "section": section,
        "handler": handler,
        "logic_key": logic_key or slugify_route_label(title),
        "filters": list(filters or STANDARD_DATE_FILTERS),
        "modes": list(modes or ()),
    }


# Explicit handler metadata for every Books / Reports sidebar route.
ROUTE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "day-book": _route("Day Book", "Books", "day_book", filters=STANDARD_DATE_FILTERS + (
        {"key": "summarize_entries", "label": "Summarize Entries", "type": "boolean", "default": True},
        {"key": "summarize_debtors", "label": "Summarize Debtors", "type": "boolean", "default": False},
        {"key": "summarize_creditors", "label": "Summarize Creditors", "type": "boolean", "default": False},
    )),
    "cash-book": _route("Cash Book", "Books", "cash_book"),
    "ledger": _route(
        "Ledger",
        "Books",
        "ledger",
        filters=STANDARD_DATE_FILTERS + (
            LEDGER_VIEW_FILTER,
            {"key": "search", "label": "Account", "type": "account", "required": False},
        ),
    ),
    "ledger-statement": _route(
        "Ledger Statement",
        "Books",
        "ledger_statement",
        filters=STANDARD_DATE_FILTERS + (
            {"key": "account_id", "label": "Account", "type": "account", "required": True},
        ),
    ),
    "sales-book": _route(
        "Sales Book",
        "Books",
        "voucher_book",
        logic_key="sales-book",
        filters=VOUCHER_BOOK_FILTERS,
        modes=VOUCHER_BOOK_MODES,
    ),
    "sales-return-book": _route(
        "Sales Return Book",
        "Books",
        "voucher_book",
        logic_key="sales-return-book",
        filters=VOUCHER_BOOK_FILTERS,
        modes=VOUCHER_BOOK_MODES,
    ),
    "bill-history": _route(
        "Bill History",
        "Books",
        "bill_history",
        filters=STANDARD_DATE_FILTERS + (
            {
                "key": "voucher_type",
                "label": "Voucher Type",
                "type": "select",
                "options": ["All", "Sales", "Purchase", "Sales Return", "Purchase Return"],
                "default": "All",
            },
            SEARCH_FILTER,
        ),
    ),
    "cash-tender-history": _route(
        "Cash Tender History",
        "Books",
        "cash_tender_history",
        filters=STANDARD_DATE_FILTERS + (SEARCH_FILTER,),
    ),
    "sales-wise-profit": _route(
        "Sales Wise Profit",
        "Books",
        "sales_profit_book",
        filters=STANDARD_DATE_FILTERS + (
            {
                "key": "report_mode",
                "label": "Report Mode",
                "type": "select",
                "required": True,
                "options": ["Bill Wise Profit", "Party Wise Profit", "Item Wise Profit"],
                "default": "Bill Wise Profit",
            },
            SEARCH_FILTER,
        ),
        modes=(
            {"label": "Bill Wise Profit", "method": "get_bill_wise"},
            {"label": "Party Wise Profit", "method": "get_party_wise"},
            {"label": "Item Wise Profit", "method": "get_item_wise"},
        ),
    ),
    "purchase-book": _route(
        "Purchase Book",
        "Books",
        "voucher_book",
        logic_key="purchase-book",
        filters=VOUCHER_BOOK_FILTERS,
        modes=VOUCHER_BOOK_MODES,
    ),
    "purchase-return-book": _route(
        "Purchase Return Book",
        "Books",
        "voucher_book",
        logic_key="purchase-return-book",
        filters=VOUCHER_BOOK_FILTERS,
        modes=VOUCHER_BOOK_MODES,
    ),
    "purchase-order-book": _route(
        "Purchase Order Book",
        "Books",
        "purchase_order_book",
        filters=STANDARD_DATE_FILTERS + (
            {
                "key": "status",
                "label": "Status",
                "type": "select",
                "options": ["All", "Pending", "Completed", "Cancelled"],
                "default": "All",
            },
            {"key": "search", "label": "Search Creditor", "type": "text", "required": False},
        ),
    ),
    "quotation-book": _route(
        "Quotation Book",
        "Books",
        "voucher_book",
        logic_key="quotation-book",
        filters=VOUCHER_BOOK_FILTERS,
        modes=VOUCHER_BOOK_MODES,
    ),
    "stock-report": _route(
        "Stock Report",
        "Books",
        "stock_report",
        filters=STANDARD_DATE_FILTERS + (
            {"key": "category", "label": "Category", "type": "text", "required": False},
            SEARCH_FILTER,
        ),
    ),
    "daily-stock-register": _route(
        "Daily Stock Register",
        "Books",
        "daily_stock_register",
        filters=STANDARD_DATE_FILTERS + (
            {"key": "product", "label": "Product", "type": "text", "required": False},
            {
                "key": "voucher_type",
                "label": "Movement Type",
                "type": "select",
                "required": False,
                "options": [
                    "All",
                    "opening",
                    "purchase",
                    "sale",
                    "return",
                    "sales_return",
                    "purchase_return",
                    "adjustment",
                    "adjustment_in",
                    "adjustment_out",
                    "transfer_in",
                    "transfer_out",
                ],
                "default": "All",
            },
        ),
    ),
    "price-list": _route("Price List", "Books", "price_list", filters=(SEARCH_FILTER,)),
    "gst-sales-report": _route("GST Sales Report", "Books", "gst_sales_report"),
    "gst-purchase-report": _route("GST Purchase Report", "Books", "gst_purchase_report"),
    "gstr-1": _route("GSTR-1", "Books", "gstr1"),
    "journal-book": _route("Journal Book", "Books", "journal_book"),
    "pdc-book": _route(
        "PDC Book",
        "Books",
        "pdc_book",
        filters=STANDARD_DATE_FILTERS + (
            {
                "key": "transaction_type",
                "label": "Transaction Type",
                "type": "select",
                "options": ["All", "RECEIPT", "ISSUE"],
                "default": "All",
            },
            {
                "key": "status",
                "label": "Status",
                "type": "select",
                "options": ["All", "PENDING", "CLEARED", "BOUNCED", "CANCELLED"],
                "default": "All",
            },
            {"key": "party", "label": "Party", "type": "text", "required": False},
        ),
    ),
    "monthly-analysis": _route(
        "Monthly Analysis",
        "Books",
        "monthly_analysis",
        filters=(
            {"key": "financial_year", "label": "Financial Year", "type": "text", "default": ""},
            {"key": "from_month", "label": "From Month", "type": "text", "default": "April"},
            {"key": "to_month", "label": "To Month", "type": "text", "default": "March"},
        ),
    ),
    "trial-balance": _route(
        "Trial Balance",
        "Reports",
        "trial_balance",
        filters=STANDARD_DATE_FILTERS + (ACCOUNT_TYPE_FILTER, SEARCH_FILTER),
    ),
    "profit-and-loss-account": _route(
        "Profit and Loss Account",
        "Reports",
        "profit_and_loss",
        filters=STANDARD_DATE_FILTERS,
    ),
    "balance-sheet": _route(
        "Balance Sheet",
        "Reports",
        "balance_sheet",
        filters=(
            {"key": "as_of_date", "label": "As Of Date", "type": "date", "required": True},
        ),
    ),
    "daily-collection-report": _route("Daily Collection Report", "Reports", "daily_collection"),
    "stock-value": _route("Stock Value", "Reports", "stock_value"),
    "best-sellers-top-products": _route("Best Sellers (Top Products)", "Reports", "best_sellers"),
    "salesman-record-book": _route("Salesman Record Book", "Reports", "salesman_book"),
}


def build_navigation_payload() -> dict[str, list[dict[str, Any]]]:
    """Return Books and Reports navigation aligned with the desktop sidebar."""
    payload: dict[str, list[dict[str, Any]]] = {"Books": [], "Reports": []}
    for section in ("Books", "Reports"):
        for label in NAVIGATION_MENU.get(section, []):
            if label.startswith("--"):
                payload[section].append(
                    {"type": "divider", "title": label.strip("- ").strip()}
                )
                continue
            slug = slugify_route_label(label)
            definition = ROUTE_DEFINITIONS.get(slug)
            if definition is None:
                continue
            payload[section].append(
                {
                    "type": "route",
                    "slug": slug,
                    "title": definition["title"],
                    "handler": definition["handler"],
                }
            )
    return payload


def get_route_definition(slug: str) -> dict[str, Any] | None:
    """Return route metadata for one slug."""
    return ROUTE_DEFINITIONS.get((slug or "").strip().lower())

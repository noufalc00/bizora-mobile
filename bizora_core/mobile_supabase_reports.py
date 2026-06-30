"""
Supabase table routing for mobile Books/Reports cloud mode.
"""

from __future__ import annotations

# slug -> (table_name, date_column or None, filter_mode)
SUPABASE_REPORT_SOURCES: dict[str, tuple[str, str | None, str | None]] = {
    "day-book": ("ledger_entries", "voucher_date", None),
    "cash-book": ("ledger_entries", "voucher_date", "cash_bank"),
    "ledger-statement": ("ledger_entries", "voucher_date", "account_id"),
    "journal-book": ("ledger_entries", "voucher_date", "journal"),
    "sales-book": ("sales", "invoice_date", None),
    "sales-return-book": ("sales_returns", "return_date", None),
    "bill-history": ("sales", "invoice_date", None),
    "cash-tender-history": ("sales", "invoice_date", None),
    "sales-wise-profit": ("sales_items", None, None),
    "purchase-book": ("purchases", "purchase_date", None),
    "purchase-return-book": ("purchase_returns", "return_date", None),
    "stock-report": ("products", None, None),
    "price-list": ("products", None, None),
    "gst-sales-report": ("sales", "invoice_date", None),
    "gst-purchase-report": ("purchases", "purchase_date", None),
    "gstr-1": ("sales", "invoice_date", None),
    "monthly-analysis": ("sales", "invoice_date", None),
    "trial-balance": ("ledger_accounts", None, None),
    "balance-sheet": ("ledger_accounts", None, None),
    "profit-and-loss-account": ("ledger_entries", "voucher_date", None),
    "daily-collection-report": ("sales", "invoice_date", None),
    "stock-value": ("products", None, None),
    "best-sellers-top-products": ("sales_items", None, None),
    "salesman-record-book": ("sales", "invoice_date", None),
    "quotation-book": ("quotations", "quotation_date", None),
    "purchase-order-book": ("purchase_orders", "date", "purchase_order"),
    "pdc-book": ("pdc_register", "cheque_date", "pdc"),
    "daily-stock-register": ("stock_movements", "created_at", "daily_stock"),
}

UNSUPPORTED_CLOUD_MESSAGE = (
    "This route is not available in cloud mode yet. "
    "On your PC run: python setup_supabase.py and python sync_bulk_to_supabase.py"
)


def get_report_source(slug: str) -> tuple[str, str | None, str | None] | None:
    """Return the Supabase source mapping for one report slug."""
    return SUPABASE_REPORT_SOURCES.get(slug)

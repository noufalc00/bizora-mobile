"""
Desktop-matched column definitions for every mobile Books/Reports route.
"""

from __future__ import annotations

from typing import Any

from bizora_core.report_column_catalog import columns_for_voucher_mode

# (label, row key) pairs — mirrors desktop report table headers.
SLUG_REPORT_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "day-book": [
        ("Date", "date"),
        ("V.No", "voucher_no"),
        ("Particulars", "particulars"),
        ("Debit", "debit"),
        ("Credit", "credit"),
        ("Voucher Type", "voucher_type"),
    ],
    "cash-book": [
        ("SL No", "sl_no"),
        ("Date", "voucher_date"),
        ("Voucher No", "voucher_no"),
        ("Type", "voucher_type"),
        ("Particulars", "particulars"),
        ("Narration", "narration"),
        ("Receipt (Dr)", "debit"),
        ("Payment (Cr)", "credit"),
        ("Balance", "running_balance"),
    ],
    "ledger-statement": [
        ("Date", "voucher_date"),
        ("Particulars", "particulars"),
        ("Debit (Dr)", "debit"),
        ("Credit (Cr)", "credit"),
        ("Running Balance", "running_balance"),
    ],
    "bill-history": [
        ("Date", "voucher_date"),
        ("Bill No", "bill_no"),
        ("Type", "voucher_type"),
        ("Party Name", "party_name"),
        ("Total Amount", "grand_total"),
        ("Status", "status"),
    ],
    "cash-tender-history": [
        ("Bill No", "bill_no"),
        ("Bill Amount", "bill_amount"),
        ("Cash Received", "cash_received"),
        ("Balance Returned", "balance_returned"),
        ("Payment Mode", "payment_mode"),
        ("Created At", "created_at"),
    ],
    "trial-balance": [
        ("SL No", "sl_no"),
        ("Ledger Account", "account_name"),
        ("Account Type", "account_type"),
        ("Opening Debit", "opening_debit"),
        ("Opening Credit", "opening_credit"),
        ("Period Debit", "period_debit"),
        ("Period Credit", "period_credit"),
        ("Closing Debit", "closing_debit"),
        ("Closing Credit", "closing_credit"),
    ],
    "profit-and-loss-account": [
        ("Particulars", "particulars"),
        ("Amount", "amount"),
    ],
    "balance-sheet": [
        ("Particulars", "particulars"),
        ("Amount", "amount"),
    ],
    "journal-book": [
        ("Date", "voucher_date"),
        ("Voucher No", "voucher_no"),
        ("Account", "account_name"),
        ("Debit", "debit"),
        ("Credit", "credit"),
        ("Narration", "narration"),
    ],
    "pdc-book": [
        ("PDC No", "id"),
        ("Type", "transaction_type"),
        ("Party/Account", "party_name"),
        ("Cheque Date", "cheque_date"),
        ("Cheque No", "cheque_number"),
        ("Amount", "amount"),
        ("Status", "status"),
    ],
    "purchase-order-book": [
        ("Date", "date"),
        ("PO No", "po_number"),
        ("Creditor", "creditor_name"),
        ("Status", "status"),
        ("Grand Total", "grand_total"),
    ],
    "stock-report": [
        ("Barcode", "barcode"),
        ("Product Name", "product_name"),
        ("Category", "category"),
        ("Unit", "unit"),
        ("Current Qty", "current_qty"),
        ("Rate", "rate"),
        ("Stock Value", "stock_value"),
    ],
    "daily-stock-register": [
        ("Date", "movement_date"),
        ("Product", "product_name"),
        ("Movement Type", "movement_type"),
        ("Qty In", "qty_in"),
        ("Qty Out", "qty_out"),
        ("Balance", "balance_qty"),
    ],
    "price-list": [
        ("Item Code", "item_code"),
        ("Item Name", "product_name"),
        ("Current Stock", "current_stock"),
        ("Purchase Rate", "purchase_rate"),
        ("Sales Rate", "sales_rate"),
        ("Wholesale Rate", "wholesale_rate"),
        ("MRP", "mrp"),
    ],
    "gst-sales-report": [
        ("Date", "voucher_date"),
        ("Bill No", "voucher_no"),
        ("Party", "party_name"),
        ("Taxable", "taxable_amount"),
        ("Tax", "tax_total"),
        ("Grand Total", "grand_total"),
    ],
    "gst-purchase-report": [
        ("Date", "voucher_date"),
        ("Bill No", "voucher_no"),
        ("Party", "party_name"),
        ("Taxable", "taxable_amount"),
        ("Tax", "tax_total"),
        ("Grand Total", "grand_total"),
    ],
    "daily-collection-report": [
        ("Date", "collection_date"),
        ("Party", "party_name"),
        ("Amount", "amount"),
        ("Mode", "payment_mode"),
    ],
    "stock-value": [
        ("Barcode", "barcode"),
        ("Product Name", "product_name"),
        ("Category", "category"),
        ("Unit", "unit"),
        ("Current Qty", "current_qty"),
        ("Rate", "rate"),
        ("Stock Value", "stock_value"),
    ],
    "best-sellers-top-products": [
        ("Rank", "rank"),
        ("Item Name", "product_name"),
        ("Total Quantity Sold", "quantity_sold"),
        ("Total Revenue Generated", "revenue"),
    ],
    "salesman-record-book": [
        ("Salesman Name", "salesman_name"),
        ("Total Bills Generated", "bill_count"),
        ("Total Revenue (Net Sales)", "net_sales"),
        ("Avg Bill Value", "avg_bill_value"),
    ],
}

LEDGER_VIEW_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "General": [
        ("SL No", "sl_no"),
        ("Account Name", "account_name"),
        ("Type", "account_type"),
        ("Opening", "opening_display"),
        ("Debit", "period_debit"),
        ("Credit", "period_credit"),
        ("Closing", "closing_display"),
        ("Dr/Cr", "closing_balance_type"),
    ],
    "Debtors": [
        ("SL No", "sl_no"),
        ("Debtor Name", "account_name"),
        ("Opening", "opening_display"),
        ("Debit", "period_debit"),
        ("Credit", "period_credit"),
        ("Closing", "closing_display"),
        ("Dr/Cr", "closing_balance_type"),
    ],
    "Creditors": [
        ("SL No", "sl_no"),
        ("Creditor Name", "account_name"),
        ("Opening", "opening_display"),
        ("Debit", "period_debit"),
        ("Credit", "period_credit"),
        ("Closing", "closing_display"),
        ("Dr/Cr", "closing_balance_type"),
    ],
    "Cash/Bank": [
        ("SL No", "sl_no"),
        ("Cash/Bank Account", "account_name"),
        ("Opening", "opening_display"),
        ("Debit", "period_debit"),
        ("Credit", "period_credit"),
        ("Closing", "closing_display"),
        ("Dr/Cr", "closing_balance_type"),
    ],
}

ROW_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("date", "voucher_date", "invoice_date", "purchase_date", "return_date"),
    "voucher_date": ("voucher_date", "date", "invoice_date", "purchase_date"),
    "voucher_no": ("voucher_no", "invoice_number", "purchase_number", "return_no", "bill_no"),
    "bill_no": ("bill_no", "voucher_no", "invoice_number", "purchase_number"),
    "voucher_type": ("voucher_type", "entry_type", "type"),
    "particulars": ("particulars", "account_name", "narration", "party_name", "product_name"),
    "party_name": ("party_name", "customer_name", "creditor_name", "account_name"),
    "product_name": ("product_name", "name", "item_name"),
    "account_name": ("account_name", "name", "ledger_name"),
    "grand_total": ("grand_total", "total_amount", "amount"),
    "amount": ("amount", "grand_total", "total_amount"),
    "debit": ("debit", "period_debit", "amount_received"),
    "credit": ("credit", "period_credit"),
    "running_balance": ("running_balance", "balance", "closing_balance"),
    "status": ("status", "payment_status"),
    "movement_date": ("movement_date", "date", "created_at"),
    "product_name": ("product_name", "name"),
    "current_qty": ("current_qty", "quantity", "stock_qty", "qty"),
    "stock_value": ("stock_value", "value"),
    "quantity_sold": ("quantity_sold", "qty_sold", "total_qty"),
    "revenue": ("revenue", "total_revenue", "net_sales"),
    "salesman_name": ("salesman_name", "salesman"),
    "bill_count": ("bill_count", "total_bills"),
    "net_sales": ("net_sales", "total_revenue"),
    "avg_bill_value": ("avg_bill_value", "average_bill"),
    "po_date": ("po_date", "date", "purchase_order_date"),
    "po_number": ("po_number", "purchase_order_number"),
    "creditor_name": ("creditor_name", "party_name", "supplier_name"),
    "collection_date": ("collection_date", "date", "voucher_date"),
    "pdc_no": ("pdc_no", "id"),
    "transaction_type": ("transaction_type", "type"),
    "cheque_date": ("cheque_date", "date"),
    "cheque_number": ("cheque_number", "cheque_no"),
    "cheque_no": ("cheque_no", "cheque_number"),
    "item_code": ("item_code", "barcode", "product_code"),
    "current_stock": ("current_stock", "quantity", "stock"),
    "purchase_rate": ("purchase_rate", "cost_rate"),
    "sales_rate": ("sales_rate", "rate"),
    "wholesale_rate": ("wholesale_rate", "wholesale_price"),
    "mrp": ("mrp", "maximum_retail_price"),
    "taxable_amount": ("taxable_amount", "taxable"),
    "tax_total": ("tax_total", "tax_amount", "tax"),
    "payment_mode": ("payment_mode", "mode"),
    "cash_received": ("cash_received", "amount_received"),
    "balance_returned": ("balance_returned", "change_returned"),
    "bill_amount": ("bill_amount", "grand_total"),
    "account_type": ("account_type", "type", "group_name"),
    "opening_debit": ("opening_debit",),
    "opening_credit": ("opening_credit",),
    "closing_debit": ("closing_debit",),
    "closing_credit": ("closing_credit",),
    "period_debit": ("period_debit", "debit"),
    "period_credit": ("period_credit", "credit"),
    "rank": ("rank", "sl_no"),
    "qty_in": ("qty_in", "quantity_in"),
    "qty_out": ("qty_out", "quantity_out"),
    "balance_qty": ("balance_qty", "balance", "closing_qty"),
    "movement_type": ("movement_type", "voucher_type"),
    "unit": ("unit", "uom"),
    "rate": ("rate", "sales_rate"),
    "barcode": ("barcode", "item_code"),
    "category": ("category", "product_category"),
    "created_at": ("created_at", "date"),
}


def resolve_report_columns(
    slug: str,
    *,
    handler: str | None = None,
    report_mode: str | None = None,
    filters: dict[str, Any] | None = None,
) -> list[tuple[str, str]]:
    """Return desktop column pairs for one mobile report route."""
    if handler == "voucher_book":
        meta = columns_for_voucher_mode(report_mode)
        return [(item["label"], item["key"]) for item in meta]

    if slug == "ledger":
        view = str((filters or {}).get("ledger_view") or "General")
        return LEDGER_VIEW_COLUMNS.get(view, LEDGER_VIEW_COLUMNS["General"])

    return SLUG_REPORT_COLUMNS.get(slug, [])


def _format_opening_closing(row: dict[str, Any], amount_key: str, type_key: str) -> str:
    """Format opening/closing like desktop Dr/Cr display."""
    amount = row.get(amount_key)
    if amount in (None, "", 0, 0.0):
        return ""
    balance_type = str(row.get(type_key) or "Dr").strip()
    try:
        numeric = float(amount)
    except (TypeError, ValueError):
        return str(amount)
    if numeric == 0:
        return ""
    return f"{numeric:,.2f} {balance_type}"


def _resolve_cell_value(row: dict[str, Any], key: str, row_index: int) -> Any:
    """Resolve one projected cell from a logic-layer row."""
    if key == "sl_no":
        return row_index

    if key == "opening_display":
        return _format_opening_closing(row, "opening_balance", "opening_balance_type")

    if key == "closing_display":
        return _format_opening_closing(row, "closing_balance", "closing_balance_type")

    if key in row and row[key] not in (None, ""):
        return row[key]

    for alias in ROW_KEY_ALIASES.get(key, ()):
        if alias in row and row[alias] not in (None, ""):
            return row[alias]

    return row.get(key, "")


def project_rows_for_columns(
    rows: list[dict[str, Any]],
    column_pairs: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    """Keep only desktop-visible fields for mobile tables."""
    if not column_pairs:
        return rows

    projected: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        projected.append(
            {
                key: _resolve_cell_value(row, key, index)
                for _, key in column_pairs
            }
        )
    return projected


def build_slug_table_payload(
    slug: str,
    rows: list[dict[str, Any]],
    *,
    handler: str | None = None,
    report_mode: str | None = None,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return rows and columns matching the desktop report for one slug."""
    from bizora_core.mobile_report_display import format_rows_for_display

    column_pairs = resolve_report_columns(
        slug,
        handler=handler,
        report_mode=report_mode,
        filters=filters,
    )
    if not column_pairs:
        from bizora_core.mobile_report_display import build_report_table_payload

        return build_report_table_payload(rows)

    projected = project_rows_for_columns(rows, column_pairs)
    cleaned = format_rows_for_display(projected)
    columns = [{"label": label, "key": key} for label, key in column_pairs]
    return {
        "rows": cleaned,
        "columns": columns,
        "row_count": len(cleaned),
    }

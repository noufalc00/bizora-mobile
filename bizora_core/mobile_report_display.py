"""
Mobile report row formatting and desktop-style column labels.
"""

from __future__ import annotations

from typing import Any

# Keys hidden from mobile tables unless they are the only data present.
HIDDEN_ROW_KEYS = frozenset(
    {
        "id",
        "company_id",
        "party_id",
        "voucher_id",
        "product_id",
        "account_id",
        "sale_id",
        "purchase_id",
        "created_at",
        "updated_at",
    }
)

COLUMN_LABELS: dict[str, str] = {
    "voucher_no": "Bill No",
    "invoice_number": "Bill No",
    "purchase_number": "Bill No",
    "return_no": "Return No",
    "quotation_no": "Quotation No",
    "po_number": "PO No",
    "voucher_date": "Date",
    "invoice_date": "Date",
    "purchase_date": "Date",
    "return_date": "Date",
    "quotation_date": "Date",
    "date": "Date",
    "cheque_date": "Cheque Date",
    "party_name": "Party",
    "creditor_name": "Creditor",
    "customer_name": "Customer",
    "product_name": "Product",
    "account_name": "Account",
    "voucher_type": "Type",
    "movement_type": "Movement",
    "nature": "Nature",
    "taxable_amount": "Taxable",
    "discount_total": "Discount",
    "tax_total": "Tax",
    "grand_total": "Grand Total",
    "settled_amount": "Settled",
    "round_off": "Round Off",
    "voucher_subtype": "Type",
    "quantity": "Qty",
    "gross_value": "Gross",
    "discount": "Discount",
    "tax_amount": "Tax",
    "tax_percent": "Tax %",
    "cgst": "CGST %",
    "sgst": "SGST %",
    "igst": "IGST %",
    "cess": "CESS %",
    "cess_amount": "CESS",
    "hsn": "HSN",
    "bill_count": "Bill Count",
    "party_type": "Type",
    "quantity_total": "Qty",
    "category": "Category",
    "due_date": "Due Date",
    "balance_amount": "Balance",
    "debit": "Debit",
    "credit": "Credit",
    "opening_balance": "Opening",
    "closing_balance": "Closing",
    "period_debit": "Period Debit",
    "period_credit": "Period Credit",
    "status": "Status",
    "narration": "Narration",
    "barcode": "Barcode",
    "qty": "Qty",
    "rate": "Rate",
    "net_amount": "Net Amount",
    "cgst_amount": "CGST",
    "sgst_amount": "SGST",
    "igst_amount": "IGST",
    "item_count": "Items",
    "salesman": "Salesman",
    "payment_mode": "Payment",
}

PREFERRED_COLUMN_ORDER: tuple[str, ...] = (
    "voucher_no",
    "invoice_number",
    "purchase_number",
    "return_no",
    "quotation_no",
    "po_number",
    "voucher_date",
    "invoice_date",
    "purchase_date",
    "return_date",
    "quotation_date",
    "date",
    "cheque_date",
    "party_name",
    "creditor_name",
    "customer_name",
    "account_name",
    "product_name",
    "nature",
    "voucher_type",
    "taxable_amount",
    "discount_total",
    "tax_total",
    "grand_total",
    "amount_received",
    "balance_amount",
    "debit",
    "credit",
    "opening_balance",
    "closing_balance",
    "period_debit",
    "period_credit",
    "status",
    "narration",
    "barcode",
    "qty",
    "rate",
    "net_amount",
)


def _format_cell(value: Any) -> Any:
    """Normalize one cell for JSON/mobile display."""
    if value is None:
        return ""
    if isinstance(value, float):
        return round(value, 2)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return value


def build_display_columns(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Build ordered column metadata from report rows."""
    if not rows:
        return []

    discovered: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in discovered:
                discovered.append(key)

    visible = [key for key in discovered if key not in HIDDEN_ROW_KEYS]
    if not visible:
        visible = discovered[:12]

    ordered: list[str] = []
    for key in PREFERRED_COLUMN_ORDER:
        if key in visible:
            ordered.append(key)
    for key in visible:
        if key not in ordered:
            ordered.append(key)

    return [
        {
            "key": key,
            "label": COLUMN_LABELS.get(key, key.replace("_", " ").title()),
        }
        for key in ordered[:14]
    ]


def format_rows_for_display(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return cleaned row dictionaries for the mobile table UI."""
    formatted: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        formatted.append({key: _format_cell(value) for key, value in row.items()})
    return formatted


def build_report_table_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Return rows plus desktop-style column metadata for mobile clients."""
    cleaned = format_rows_for_display(rows)
    columns = build_display_columns(cleaned)
    return {
        "rows": cleaned,
        "columns": columns,
        "row_count": len(cleaned),
    }

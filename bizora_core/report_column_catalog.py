"""
Desktop report column definitions shared by mobile web tables.
"""

from __future__ import annotations

from typing import Any

VOUCHER_REPORT_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "Bill Wise": [
        ("Date", "voucher_date"),
        ("No", "voucher_no"),
        ("Party", "party_name"),
        ("Type", "voucher_subtype"),
        ("Nature", "nature"),
        ("Taxable", "taxable_amount"),
        ("CGST", "cgst_amount"),
        ("SGST", "sgst_amount"),
        ("IGST", "igst_amount"),
        ("CESS", "cess_amount"),
        ("Tax", "tax_total"),
        ("Discount", "discount_total"),
        ("Round Off", "round_off"),
        ("Grand Total", "grand_total"),
        ("Settled", "settled_amount"),
        ("Balance", "balance_amount"),
    ],
    "Item Wise": [
        ("Date", "voucher_date"),
        ("No", "voucher_no"),
        ("Party", "party_name"),
        ("Product", "product_name"),
        ("Barcode", "barcode"),
        ("HSN", "hsn"),
        ("Qty", "quantity"),
        ("Rate", "rate"),
        ("Gross", "gross_value"),
        ("Discount", "discount"),
        ("Taxable", "taxable_amount"),
        ("Tax %", "tax_percent"),
        ("CGST", "cgst_amount"),
        ("SGST", "sgst_amount"),
        ("IGST", "igst_amount"),
        ("CESS", "cess_amount"),
        ("Tax", "tax_amount"),
        ("Total", "grand_total"),
    ],
    "Tax Wise": [
        ("Date", "voucher_date"),
        ("No", "voucher_no"),
        ("Party", "party_name"),
        ("HSN", "hsn"),
        ("Product", "product_name"),
        ("Tax %", "tax_percent"),
        ("CGST %", "cgst"),
        ("SGST %", "sgst"),
        ("IGST %", "igst"),
        ("CESS %", "cess"),
        ("Taxable", "taxable_amount"),
        ("CGST", "cgst_amount"),
        ("SGST", "sgst_amount"),
        ("IGST", "igst_amount"),
        ("CESS", "cess_amount"),
        ("Tax", "tax_amount"),
        ("Total", "grand_total"),
    ],
    "Tax Summary": [
        ("Tax %", "tax_percent"),
        ("CGST %", "cgst"),
        ("SGST %", "sgst"),
        ("IGST %", "igst"),
        ("CESS %", "cess"),
        ("Nature", "nature"),
        ("Bill Count", "bill_count"),
        ("Taxable", "taxable_amount"),
        ("CGST", "cgst_amount"),
        ("SGST", "sgst_amount"),
        ("IGST", "igst_amount"),
        ("CESS", "cess_amount"),
        ("Tax", "tax_amount"),
        ("Total", "grand_total"),
    ],
    "Credit": [
        ("Date", "voucher_date"),
        ("No", "voucher_no"),
        ("Party", "party_name"),
        ("Grand Total", "grand_total"),
        ("Settled", "settled_amount"),
        ("Balance", "balance_amount"),
        ("Due Date", "due_date"),
        ("Status", "status"),
    ],
    "Party Wise": [
        ("Party", "party_name"),
        ("Type", "party_type"),
        ("Bill Count", "bill_count"),
        ("Taxable", "taxable_amount"),
        ("Tax", "tax_total"),
        ("Discount", "discount_total"),
        ("Grand Total", "grand_total"),
        ("Settled", "settled_amount"),
        ("Balance", "balance_amount"),
    ],
    "Category Wise": [
        ("Category", "category"),
        ("Bill Count", "bill_count"),
        ("Qty", "quantity_total"),
        ("Taxable", "taxable_amount"),
        ("Tax", "tax_total"),
        ("Discount", "discount_total"),
        ("Grand Total", "grand_total"),
    ],
    "Bill Wise Profit": [
        ("Date", "invoice_date"),
        ("Invoice No", "invoice_number"),
        ("Party", "party_name"),
        ("Sales Value", "sales_value"),
        ("Cost Value", "cost_value"),
        ("Gross Profit", "profit"),
        ("Margin %", "margin_percent"),
    ],
    "Party Wise Profit": [
        ("Date", "invoice_date"),
        ("Invoice No", "invoice_number"),
        ("Party", "party_name"),
        ("Sales Value", "sales_value"),
        ("Cost Value", "cost_value"),
        ("Gross Profit", "profit"),
        ("Margin %", "margin_percent"),
    ],
    "Item Wise Profit": [
        ("Product", "product_name"),
        ("Qty Sold", "qty_sold"),
        ("Sales Value", "sales_value"),
        ("Cost Value", "cost_value"),
        ("Gross Profit", "profit"),
        ("Margin %", "margin_percent"),
    ],
}

MODE_LABEL_ALIASES: dict[str, str] = {"Credit / Pending": "Credit"}


def normalize_report_mode(mode: str | None) -> str:
    """Map mobile filter labels to desktop report column keys."""
    label = str(mode or "Bill Wise").strip()
    return MODE_LABEL_ALIASES.get(label, label)


def columns_for_voucher_mode(mode: str | None) -> list[dict[str, str]]:
    """Return ordered column metadata for one voucher book mode."""
    key = normalize_report_mode(mode)
    pairs = VOUCHER_REPORT_COLUMNS.get(key) or VOUCHER_REPORT_COLUMNS["Bill Wise"]
    return [{"label": label, "key": data_key} for label, data_key in pairs]


def build_voucher_table_payload(
    rows: list[dict[str, Any]],
    mode: str | None,
) -> dict[str, Any]:
    """Build mobile table payload using desktop voucher column order."""
    from bizora_core.mobile_report_display import format_rows_for_display

    cleaned = format_rows_for_display(rows)
    column_meta = columns_for_voucher_mode(mode)
    return {
        "rows": cleaned,
        "columns": column_meta,
        "row_count": len(cleaned),
    }

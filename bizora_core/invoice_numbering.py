"""
Unified voucher / invoice numbering for sales, purchase, returns, and quotations.

Numbers use the company invoice prefix from settings plus a 3-digit sequence
starting at 001 (e.g. prefix ``INV-`` -> ``INV-001``).
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from bizora_core.settings_logic import get_settings

INVOICE_PREFIX_KEY = "invoice_prefix"

VOUCHER_PREFIX_SETTINGS = {
    "sales": "invoice_prefix_sales",
    "purchase": "invoice_prefix_purchase",
    "sales_return": "invoice_prefix_sales_return",
    "purchase_return": "invoice_prefix_purchase_return",
    "quotation": "invoice_prefix_quotation",
    "purchase_order": "invoice_prefix_purchase_order",
}

VOUCHER_PREFIX_LABELS = {
    "sales": "Sales Entry",
    "purchase": "Purchase Entry",
    "sales_return": "Sales Return",
    "purchase_return": "Purchase Return",
    "quotation": "Quotation",
    "purchase_order": "Purchase Order",
}

VOUCHER_TABLES: Dict[str, Tuple[str, str]] = {
    "sales": ("sales", "invoice_number"),
    "purchase": ("purchases", "purchase_number"),
    "sales_return": ("sales_returns", "return_no"),
    "purchase_return": ("purchase_returns", "return_no"),
    "quotation": ("quotations", "quotation_no"),
    "purchase_order": ("purchase_orders", "po_number"),
}


def get_invoice_prefix(db, company_id: int, voucher_type: str = "") -> str:
    """Return the configured invoice prefix for one company and voucher type."""
    try:
        settings = get_settings(db, company_id)
        if voucher_type:
            specific_key = VOUCHER_PREFIX_SETTINGS.get(voucher_type)
            if specific_key:
                specific_prefix = str(settings.get(specific_key, "") or "").strip()
                if specific_prefix:
                    return specific_prefix
        return str(settings.get(INVOICE_PREFIX_KEY, "") or "")
    except Exception:
        return ""


def format_voucher_number(prefix: str, sequence: int) -> str:
    """Build a display voucher number from prefix and sequence."""
    safe_sequence = max(1, int(sequence or 1))
    return f"{prefix or ''}{safe_sequence:03d}"


def parse_voucher_sequence(value: str, prefix: str = "") -> Optional[int]:
    """Extract the trailing numeric sequence from a voucher number."""
    text = str(value or "").strip()
    if not text:
        return None

    normalized_prefix = str(prefix or "")
    if normalized_prefix and text.lower().startswith(normalized_prefix.lower()):
        suffix = text[len(normalized_prefix):]
    else:
        suffix = text

    digits = ""
    for character in reversed(suffix):
        if character.isdigit():
            digits = character + digits
        elif digits:
            break

    if not digits:
        return None

    try:
        return int(digits)
    except (TypeError, ValueError):
        return None


def get_max_voucher_sequence(
    db,
    company_id: int,
    voucher_type: str,
    prefix: str | None = None,
) -> int:
    """Return the highest saved numeric sequence for a voucher type."""
    table_info = VOUCHER_TABLES.get(voucher_type)
    if not table_info:
        return 0

    table_name, column_name = table_info
    resolved_prefix = (
        get_invoice_prefix(db, company_id, voucher_type)
        if prefix is None
        else str(prefix or "")
    )
    placeholder = db._get_placeholder()

    try:
        if resolved_prefix:
            pattern = f"{resolved_prefix}%"
            query = f"""
                SELECT {column_name}
                FROM {table_name}
                WHERE company_id = {placeholder}
                  AND {column_name} LIKE {placeholder}
            """
            rows = db.execute_query(query, (company_id, pattern)) or []
        else:
            query = f"""
                SELECT {column_name}
                FROM {table_name}
                WHERE company_id = {placeholder}
            """
            rows = db.execute_query(query, (company_id,)) or []
    except Exception:
        return 0

    max_sequence = 0
    for row in rows:
        if isinstance(row, dict):
            raw_value = row.get(column_name)
        else:
            raw_value = row[0] if row else ""
        sequence = parse_voucher_sequence(str(raw_value or ""), resolved_prefix)
        if sequence is not None and sequence > max_sequence:
            max_sequence = sequence
    return max_sequence


def get_next_voucher_number(db, company_id: int, voucher_type: str) -> str:
    """Return the next unused voucher number based on saved records."""
    prefix = get_invoice_prefix(db, company_id, voucher_type)
    next_sequence = get_max_voucher_sequence(db, company_id, voucher_type, prefix) + 1
    return format_voucher_number(prefix, next_sequence)


def get_next_voucher_from_current(
    db,
    company_id: int,
    voucher_type: str,
    current_value: str,
) -> str:
    """Return the next voucher number after the current field value or DB max."""
    prefix = get_invoice_prefix(db, company_id, voucher_type)
    current_sequence = parse_voucher_sequence(current_value, prefix) or 0
    saved_max = get_max_voucher_sequence(db, company_id, voucher_type, prefix)
    next_sequence = max(current_sequence, saved_max) + 1
    return format_voucher_number(prefix, next_sequence)

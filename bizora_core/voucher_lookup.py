"""
Lookup saved voucher records by display number for entry-page navigation.
"""

from __future__ import annotations

from typing import Optional

from bizora_core.invoice_numbering import (
    VOUCHER_TABLES,
    format_voucher_number,
    get_invoice_prefix,
    parse_voucher_sequence,
)

VOUCHER_ID_LOADERS = {
    "sales": "load_sale_by_id",
    "purchase": "load_purchase",
    "sales_return": "load_return_by_id",
    "purchase_return": "load_return_by_id",
    "quotation": "load_quotation_by_id",
    "purchase_order": "load_po_by_id",
}


def _lookup_voucher_id_exact(
    db,
    company_id: int,
    table_name: str,
    column_name: str,
    number: str,
) -> Optional[int]:
    """Return a voucher id when the stored number matches exactly."""
    placeholder = db._get_placeholder()
    try:
        rows = db.execute_query(
            f"""
            SELECT id
            FROM {table_name}
            WHERE company_id = {placeholder}
              AND {column_name} = {placeholder}
            ORDER BY id DESC
            LIMIT 1
            """,
            (company_id, number),
        ) or []
    except Exception:
        return None

    if not rows:
        return None

    row = rows[0]
    raw_id = row.get("id") if isinstance(row, dict) else row[0]
    try:
        return int(raw_id)
    except (TypeError, ValueError):
        return None


def _candidate_voucher_numbers(
    db,
    company_id: int,
    voucher_type: str,
    voucher_number: str,
) -> list[str]:
    """Build likely stored voucher numbers from user input such as 002 or SL-002."""
    number = str(voucher_number or "").strip()
    if not number:
        return []

    candidates = [number]
    prefix = get_invoice_prefix(db, company_id, voucher_type)
    sequence = parse_voucher_sequence(number, prefix)
    if sequence is None:
        sequence = parse_voucher_sequence(number, "")

    if sequence is not None:
        if prefix:
            prefixed = format_voucher_number(prefix, sequence)
            if prefixed not in candidates:
                candidates.append(prefixed)
        bare = format_voucher_number("", sequence)
        if bare not in candidates:
            candidates.append(bare)

    if prefix and not number.lower().startswith(prefix.lower()):
        prefixed_input = f"{prefix}{number}"
        if prefixed_input not in candidates:
            candidates.append(prefixed_input)

    return candidates


def find_voucher_id(db, company_id: int, voucher_type: str, voucher_number: str) -> Optional[int]:
    """Return the primary-key id for a saved voucher number, if it exists."""
    table_info = VOUCHER_TABLES.get(voucher_type)
    number = str(voucher_number or "").strip()
    if not table_info or not number:
        return None

    table_name, column_name = table_info
    for candidate in _candidate_voucher_numbers(db, company_id, voucher_type, number):
        voucher_id = _lookup_voucher_id_exact(
            db,
            company_id,
            table_name,
            column_name,
            candidate,
        )
        if voucher_id:
            return voucher_id
    return None

"""
Dashboard metric calculations for Supabase-backed mobile web.

Pure-Python port of key DashboardLogic formulas using synced rows.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Mapping

_QUOTE_VOUCHER_TYPES = frozenset(
    {"quotation", "estimate", "quote", "Quotation", "Estimate", "Quote"}
)


def _parse_date(value: Any) -> date | None:
    """Parse an ISO date string from Supabase/SQLite."""
    text = str(value or "").strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def is_credit_sale(row: Mapping[str, Any]) -> bool:
    """Return True when a sale row represents a credit sale."""
    payment_mode = str(row.get("payment_mode") or "").lower()
    sales_type = str(row.get("sales_type") or "").lower()
    return "credit" in payment_mode or sales_type in {"credit sales", "credit"}


def calculate_day_credit_sales(sales_rows: Iterable[Mapping[str, Any]], voucher_date: str) -> float:
    """Sum today's credit sales."""
    target = voucher_date[:10]
    total = 0.0
    for row in sales_rows:
        if str(row.get("invoice_date") or "")[:10] != target:
            continue
        if str(row.get("status") or "Active").lower() == "voided":
            continue
        if is_credit_sale(row):
            total += float(row.get("grand_total") or 0.0)
    return round(total, 2)


def calculate_net_realized_sale(
    sales_rows: Iterable[Mapping[str, Any]],
    sales_return_rows: Iterable[Mapping[str, Any]],
    company_id: int,
    start_date: str,
    end_date: str,
) -> float:
    """Approximate net realized sale for one date range from synced headers."""
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if not start or not end:
        return 0.0

    total_sales = 0.0
    credit_sales = 0.0
    for row in sales_rows:
        if int(row.get("company_id") or 0) != company_id:
            continue
        if str(row.get("status") or "Active").lower() == "voided":
            continue
        invoice_date = _parse_date(row.get("invoice_date"))
        if not invoice_date or invoice_date < start or invoice_date > end:
            continue
        amount = float(row.get("grand_total") or 0.0)
        total_sales += amount
        if is_credit_sale(row):
            credit_sales += amount

    sales_returns = 0.0
    for row in sales_return_rows:
        if int(row.get("company_id") or 0) != company_id:
            continue
        if str(row.get("status") or "Active").lower() == "voided":
            continue
        return_date = _parse_date(row.get("return_date"))
        if not return_date or return_date < start or return_date > end:
            continue
        sales_returns += float(row.get("grand_total") or 0.0)

    return round(total_sales - credit_sales - sales_returns, 2)


def _opening_signed(account: Mapping[str, Any]) -> float:
    """Return signed opening balance for one ledger account."""
    amount = float(account.get("opening_balance") or 0.0)
    balance_type = str(account.get("opening_balance_type") or "Dr").lower()
    if balance_type.startswith("cr"):
        return -amount
    return amount


def _account_matches_group(account: Mapping[str, Any], group_name: str) -> bool:
    """Return True when a ledger account belongs to a sundry group."""
    target = group_name.strip().lower()
    group = str(account.get("group_name") or "").strip().lower()
    name = str(account.get("account_name") or "").strip().lower()
    return group == target or name == target


def calculate_sundry_group_balance_total(
    ledger_accounts: Iterable[Mapping[str, Any]],
    ledger_entries: Iterable[Mapping[str, Any]],
    company_id: int,
    from_date: date,
    to_date: date,
    group_name: str,
    balance_side: str,
) -> float:
    """Sum debtor or creditor closing balances from synced ledger rows."""
    accounts = [
        row
        for row in ledger_accounts
        if int(row.get("company_id") or 0) == company_id
        and int(row.get("is_active", 1) or 0) == 1
        and _account_matches_group(row, group_name)
    ]
    if not accounts:
        return 0.0

    account_ids = {int(row["id"]) for row in accounts if row.get("id") is not None}
    entries_by_account: dict[int, list[Mapping[str, Any]]] = {account_id: [] for account_id in account_ids}
    for entry in ledger_entries:
        if int(entry.get("company_id") or 0) != company_id:
            continue
        if str(entry.get("voucher_type") or "") in _QUOTE_VOUCHER_TYPES:
            continue
        account_id = entry.get("account_id")
        if account_id is None:
            continue
        account_key = int(account_id)
        if account_key in entries_by_account:
            entries_by_account[account_key].append(entry)

    total = 0.0
    for account in accounts:
        account_id = int(account["id"])
        closing_net = _opening_signed(account)
        for entry in entries_by_account.get(account_id, []):
            entry_date = _parse_date(entry.get("voucher_date"))
            if entry_date is None:
                continue
            movement = float(entry.get("debit") or 0.0) - float(entry.get("credit") or 0.0)
            if entry_date < from_date:
                closing_net += movement
            elif from_date <= entry_date <= to_date:
                closing_net += movement

        if balance_side.strip().lower().startswith("cr"):
            if closing_net < -0.004:
                total += abs(closing_net)
        elif closing_net > 0.004:
            total += closing_net

    return round(total, 2)

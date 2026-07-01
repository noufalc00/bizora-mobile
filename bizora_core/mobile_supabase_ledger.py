"""
Ledger summary calculations for Supabase-backed mobile web.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Mapping

from bizora_core.mobile_supabase_party_links import party_by_ledger_account

_QUOTE_VOUCHER_TYPES = frozenset(
    {"quotation", "estimate", "quote", "Quotation", "Estimate", "Quote"}
)


def _parse_date(value: Any) -> date | None:
    """Parse ISO date strings from synced rows."""
    text = str(value or "").strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _split_balance(debit: float, credit: float) -> tuple[float, str]:
    """Return absolute balance and Dr/Cr type."""
    net = round(debit - credit, 2)
    if net >= 0:
        return abs(net), "Dr"
    return abs(net), "Cr"


def _opening_balance_parts(account: Mapping[str, Any]) -> tuple[float, float]:
    """Convert opening balance fields into debit/credit components."""
    amount = float(account.get("opening_balance") or 0.0)
    balance_type = str(account.get("opening_balance_type") or "Dr").strip()
    if balance_type == "Cr":
        return 0.0, amount
    return amount, 0.0


def _entries_for_account(
    entries: Iterable[Mapping[str, Any]],
    company_id: int,
    account_id: int,
) -> list[Mapping[str, Any]]:
    """Filter ledger entries for one account."""
    account_key = str(account_id)
    company_key = str(company_id)
    filtered: list[Mapping[str, Any]] = []
    for entry in entries:
        if str(entry.get("company_id")) != company_key:
            continue
        if str(entry.get("account_id")) != account_key:
            continue
        voucher_type = str(entry.get("voucher_type") or "")
        if voucher_type in _QUOTE_VOUCHER_TYPES:
            continue
        filtered.append(entry)
    return filtered


def _balance_before_date(
    account: Mapping[str, Any],
    entries: Iterable[Mapping[str, Any]],
    company_id: int,
    account_id: int,
    before_date: date,
) -> dict[str, float]:
    """Compute debit/credit/net before a date (exclusive)."""
    opening_debit, opening_credit = _opening_balance_parts(account)
    period_debit = 0.0
    period_credit = 0.0
    for entry in _entries_for_account(entries, company_id, account_id):
        entry_date = _parse_date(entry.get("voucher_date"))
        if entry_date is None or entry_date >= before_date:
            continue
        period_debit += float(entry.get("debit") or 0.0)
        period_credit += float(entry.get("credit") or 0.0)
    debit = round(opening_debit + period_debit, 2)
    credit = round(opening_credit + period_credit, 2)
    return {"debit": debit, "credit": credit, "net": round(debit - credit, 2)}


def _period_totals(
    entries: Iterable[Mapping[str, Any]],
    company_id: int,
    account_id: int,
    from_date: date,
    to_date: date,
) -> dict[str, float]:
    """Sum debit/credit inside the selected period."""
    debit = 0.0
    credit = 0.0
    for entry in _entries_for_account(entries, company_id, account_id):
        entry_date = _parse_date(entry.get("voucher_date"))
        if entry_date is None or entry_date < from_date or entry_date > to_date:
            continue
        debit += float(entry.get("debit") or 0.0)
        credit += float(entry.get("credit") or 0.0)
    return {"debit": round(debit, 2), "credit": round(credit, 2)}


def build_account_summary(
    accounts: list[dict[str, Any]],
    entries: list[dict[str, Any]],
    company_id: int,
    from_date: date,
    to_date: date,
) -> list[dict[str, Any]]:
    """Build ledger summary rows for the provided accounts."""
    summary: list[dict[str, Any]] = []
    for account in accounts:
        account_id = account.get("id")
        if account_id is None:
            continue
        account_id_int = int(account_id)
        opening_data = _balance_before_date(account, entries, company_id, account_id_int, from_date)
        period = _period_totals(entries, company_id, account_id_int, from_date, to_date)
        opening_balance, opening_type = _split_balance(
            opening_data.get("debit", 0.0),
            opening_data.get("credit", 0.0),
        )
        closing_debit = float(opening_data.get("debit", 0.0)) + period["debit"]
        closing_credit = float(opening_data.get("credit", 0.0)) + period["credit"]
        closing_balance, closing_type = _split_balance(closing_debit, closing_credit)
        summary.append(
            {
                "id": account_id_int,
                "party_id": account.get("party_id"),
                "account_name": account.get("account_name", ""),
                "account_type": account.get("account_type", ""),
                "group_name": account.get("group_name", ""),
                "party_type": account.get("party_type", ""),
                "opening_balance": opening_balance,
                "opening_balance_type": opening_type,
                "period_debit": period["debit"],
                "period_credit": period["credit"],
                "closing_balance": closing_balance,
                "closing_balance_type": closing_type,
            }
        )
    return summary


def filter_accounts_for_view(
    ledger_accounts: list[dict[str, Any]],
    parties: list[dict[str, Any]],
    view: str,
) -> list[dict[str, Any]]:
    """Return ledger accounts for General / Debtors / Creditors / Cash-Bank views."""
    party_by_ledger = party_by_ledger_account(parties, ledger_accounts)
    active_accounts = [
        row for row in ledger_accounts
        if str(row.get("is_active", 1)) not in {"0", "false", "False"}
    ]
    view_name = str(view or "General")

    if view_name == "Debtors":
        accounts: list[dict[str, Any]] = []
        for account in active_accounts:
            if str(account.get("account_type") or "").lower() != "party":
                continue
            party = party_by_ledger.get(int(account.get("id") or 0))
            if not party:
                continue
            if str(party.get("party_type") or "") not in {"Debitor", "Both"}:
                continue
            enriched = dict(account)
            enriched["party_id"] = party.get("id")
            enriched["party_type"] = party.get("party_type")
            accounts.append(enriched)
        return accounts

    if view_name == "Creditors":
        accounts = []
        for account in active_accounts:
            if str(account.get("account_type") or "").lower() != "party":
                continue
            party = party_by_ledger.get(int(account.get("id") or 0))
            if not party:
                continue
            if str(party.get("party_type") or "") not in {"Creditor", "Both"}:
                continue
            enriched = dict(account)
            enriched["party_id"] = party.get("id")
            enriched["party_type"] = party.get("party_type")
            accounts.append(enriched)
        return accounts

    if view_name == "Cash/Bank":
        return [
            row for row in active_accounts
            if str(row.get("account_type") or "").lower() == "cash_bank"
        ]

    return [
        row for row in active_accounts
        if str(row.get("account_type") or "").lower() not in {"party", "cash_bank"}
    ]

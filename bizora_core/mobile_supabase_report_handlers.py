"""
Cloud (Supabase) report handlers that return desktop-shaped row data.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Callable

from bizora_core.mobile_report_columns import build_slug_table_payload
from bizora_core.mobile_supabase_ledger import build_account_summary, filter_accounts_for_view

_QUOTE_TYPES = frozenset(
    {"quotation", "estimate", "quote", "Quotation", "Estimate", "Quote"}
)


def _parse_date(value: Any) -> str:
    return str(value or "")[:10]


def _in_range(value: Any, from_date: str, to_date: str) -> bool:
    text = _parse_date(value)
    if not text:
        return False
    if from_date and text < from_date:
        return False
    if to_date and text > to_date:
        return False
    return True


def _safe_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _finish(slug: str, rows: list[dict[str, Any]], filters: dict[str, Any], handler: str) -> dict[str, Any]:
    """Attach desktop column metadata to one cloud report result."""
    table_payload = build_slug_table_payload(
        slug,
        rows,
        handler=handler,
        report_mode=filters.get("report_mode"),
        filters=filters,
    )
    return {
        "success": True,
        "message": "" if rows else "No records found for the selected filters.",
        "data_source": "supabase",
        **table_payload,
    }


def run_cloud_day_book(
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Build Day Book rows (Date, V.No, Particulars, Debit, Credit, Voucher Type)."""
    from_date = _parse_date(filters.get("from_date"))
    to_date = _parse_date(filters.get("to_date"))
    summarize = bool(filters.get("summarize_entries", True))

    accounts = fetch_table(
        "ledger_accounts",
        company_id,
        select="id,account_name,account_type",
        limit=2000,
    )
    account_names = {
        int(row["id"]): str(row.get("account_name") or "")
        for row in accounts
        if row.get("id") is not None
    }

    entries = fetch_table(
        "ledger_entries",
        company_id,
        select="voucher_date,voucher_no,voucher_type,voucher_id,account_id,debit,credit,narration",
        limit=15000,
        order_col="voucher_date",
    )

    filtered = [
        row for row in entries
        if _in_range(row.get("voucher_date"), from_date, to_date)
        and str(row.get("voucher_type") or "") not in _QUOTE_TYPES
    ]

    if summarize:
        buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in filtered:
            key = (
                _parse_date(row.get("voucher_date")),
                str(row.get("voucher_no") or ""),
                str(row.get("voucher_type") or ""),
            )
            account_id = row.get("account_id")
            particulars = account_names.get(int(account_id), "") if account_id is not None else ""
            if not particulars:
                particulars = str(row.get("narration") or "Ledger Account")
            bucket = buckets.setdefault(
                key,
                {
                    "date": key[0],
                    "voucher_no": key[1],
                    "particulars": particulars,
                    "debit": 0.0,
                    "credit": 0.0,
                    "voucher_type": key[2].replace("_", " ").title(),
                },
            )
            bucket["debit"] += _safe_float(row.get("debit"))
            bucket["credit"] += _safe_float(row.get("credit"))
            if len(particulars) > len(str(bucket.get("particulars") or "")):
                bucket["particulars"] = particulars

        rows = [
            {
                "date": value["date"],
                "voucher_no": value["voucher_no"],
                "particulars": value["particulars"],
                "debit": round(value["debit"], 2),
                "credit": round(value["credit"], 2),
                "voucher_type": value["voucher_type"],
            }
            for value in sorted(buckets.values(), key=lambda item: (item["date"], item["voucher_no"]))
        ]
    else:
        rows = []
        for row in filtered:
            account_id = row.get("account_id")
            particulars = account_names.get(int(account_id), "") if account_id is not None else ""
            if not particulars:
                particulars = str(row.get("narration") or "Ledger Account")
            rows.append(
                {
                    "date": _parse_date(row.get("voucher_date")),
                    "voucher_no": row.get("voucher_no", ""),
                    "particulars": particulars,
                    "debit": round(_safe_float(row.get("debit")), 2),
                    "credit": round(_safe_float(row.get("credit")), 2),
                    "voucher_type": str(row.get("voucher_type") or "").replace("_", " ").title(),
                }
            )

    return _finish("day-book", rows, filters, "day_book")


def run_cloud_cash_book(
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Build Cash Book rows matching desktop columns."""
    from_date = _parse_date(filters.get("from_date"))
    to_date = _parse_date(filters.get("to_date"))

    accounts = fetch_table(
        "ledger_accounts",
        company_id,
        select="id,account_name,account_type",
        limit=2000,
    )
    cash_accounts = [
        row for row in accounts
        if str(row.get("account_type") or "").lower() == "cash_bank"
    ]
    if not cash_accounts:
        cash_accounts = [
            row for row in accounts
            if "cash" in str(row.get("account_name") or "").lower()
        ]

    cash_ids = {int(row["id"]) for row in cash_accounts if row.get("id") is not None}
    account_names = {
        int(row["id"]): str(row.get("account_name") or "")
        for row in accounts
        if row.get("id") is not None
    }

    entries = fetch_table(
        "ledger_entries",
        company_id,
        select="voucher_date,voucher_no,voucher_type,account_id,debit,credit,narration",
        limit=15000,
        order_col="voucher_date",
    )

    cash_entries = [
        row for row in entries
        if row.get("account_id") is not None
        and int(row["account_id"]) in cash_ids
        and _in_range(row.get("voucher_date"), from_date, to_date)
        and str(row.get("voucher_type") or "") not in _QUOTE_TYPES
    ]

    by_voucher: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in entries:
        if str(row.get("voucher_type") or "") in _QUOTE_TYPES:
            continue
        key = (str(row.get("voucher_no") or ""), str(row.get("voucher_type") or ""))
        by_voucher[key].append(row)

    running = 0.0
    rows: list[dict[str, Any]] = []
    for index, entry in enumerate(
        sorted(cash_entries, key=lambda item: (_parse_date(item.get("voucher_date")), str(item.get("voucher_no") or ""))),
        start=1,
    ):
        voucher_key = (str(entry.get("voucher_no") or ""), str(entry.get("voucher_type") or ""))
        contra_name = ""
        for sibling in by_voucher.get(voucher_key, []):
            sibling_id = sibling.get("account_id")
            if sibling_id is not None and int(sibling_id) not in cash_ids:
                contra_name = account_names.get(int(sibling_id), "")
                if contra_name:
                    break

        debit = _safe_float(entry.get("debit"))
        credit = _safe_float(entry.get("credit"))
        running = round(running + debit - credit, 2)
        rows.append(
            {
                "sl_no": index,
                "voucher_date": _parse_date(entry.get("voucher_date")),
                "voucher_no": entry.get("voucher_no", ""),
                "voucher_type": str(entry.get("voucher_type") or "").replace("_", " ").title(),
                "particulars": contra_name or "Unknown",
                "narration": entry.get("narration", ""),
                "debit": round(debit, 2),
                "credit": round(credit, 2),
                "running_balance": running,
            }
        )

    return _finish("cash-book", rows, filters, "cash_book")


def run_cloud_journal_book(
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Return journal voucher lines with desktop columns."""
    from_date = _parse_date(filters.get("from_date"))
    to_date = _parse_date(filters.get("to_date"))

    accounts = fetch_table(
        "ledger_accounts",
        company_id,
        select="id,account_name",
        limit=2000,
    )
    account_names = {
        int(row["id"]): str(row.get("account_name") or "")
        for row in accounts
        if row.get("id") is not None
    }

    entries = fetch_table(
        "ledger_entries",
        company_id,
        select="voucher_date,voucher_no,voucher_type,account_id,debit,credit,narration",
        limit=15000,
        order_col="voucher_date",
    )

    rows = []
    for entry in entries:
        if not _in_range(entry.get("voucher_date"), from_date, to_date):
            continue
        if "journal" not in str(entry.get("voucher_type") or "").lower():
            continue
        account_id = entry.get("account_id")
        rows.append(
            {
                "voucher_date": _parse_date(entry.get("voucher_date")),
                "voucher_no": entry.get("voucher_no", ""),
                "account_name": account_names.get(int(account_id), "") if account_id is not None else "",
                "debit": round(_safe_float(entry.get("debit")), 2),
                "credit": round(_safe_float(entry.get("credit")), 2),
                "narration": entry.get("narration", ""),
            }
        )

    return _finish("journal-book", rows, filters, "journal_book")


def run_cloud_ledger_summary(
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Run ledger summary views with desktop columns."""
    from_dt = date.fromisoformat(_parse_date(filters.get("from_date") or date.today()))
    to_dt = date.fromisoformat(_parse_date(filters.get("to_date") or date.today()))
    view = str(filters.get("ledger_view") or "General")

    ledger_accounts = fetch_table(
        "ledger_accounts",
        company_id,
        select="id,company_id,account_name,account_type,group_name,opening_balance,opening_balance_type,is_active",
        limit=2000,
    )
    parties = fetch_table("parties", company_id, select="id,party_type,name", limit=2000)
    entries = fetch_table(
        "ledger_entries",
        company_id,
        select="company_id,account_id,voucher_type,voucher_date,debit,credit",
        limit=15000,
        order_col="voucher_date",
    )
    accounts = filter_accounts_for_view(ledger_accounts, parties, view)
    rows = build_account_summary(accounts, entries, company_id, from_dt, to_dt)

    search = str(filters.get("search") or "").strip().lower()
    if search:
        rows = [row for row in rows if search in str(row.get("account_name", "")).lower()]

    return _finish("ledger", rows, filters, "ledger")


def run_cloud_handler_report(
    handler: str,
    slug: str,
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any] | None:
    """Dispatch one cloud report handler; None when not implemented."""
    handlers = {
        "day_book": lambda: run_cloud_day_book(fetch_table, company_id, filters),
        "cash_book": lambda: run_cloud_cash_book(fetch_table, company_id, filters),
        "journal_book": lambda: run_cloud_journal_book(fetch_table, company_id, filters),
        "ledger": lambda: run_cloud_ledger_summary(fetch_table, company_id, filters),
    }
    runner = handlers.get(handler)
    if runner is None:
        return None
    return runner()

"""
Desktop-parity financial reports for cloud mode using in-memory ledger snapshots.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

from bizora_core.mobile_report_columns import build_slug_table_payload
from bizora_core.mobile_supabase_memory_db import load_ledger_memory_db


def _parse_date(value: Any) -> str:
    return str(value or "").strip()[:10]


def _parse_iso_date(value: Any, fallback: date | None = None) -> date:
    """Parse one filter date safely for cloud financial reports."""
    fallback = fallback or date.today()
    text = _parse_date(value)
    if not text:
        return fallback
    try:
        return date.fromisoformat(text)
    except ValueError:
        return fallback


def _finish(slug: str, rows: list[dict[str, Any]], filters: dict[str, Any], handler: str, **extra: Any) -> dict[str, Any]:
    """Attach desktop column metadata to one cloud report result."""
    table_payload = build_slug_table_payload(
        slug,
        rows,
        handler=handler,
        filters=filters,
    )
    payload = {
        "success": True,
        "message": "" if rows else "No records found for the selected filters.",
        "data_source": "supabase",
        **table_payload,
    }
    payload.update(extra)
    return payload


def build_profit_and_loss_rows(result: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """Shape FinancialReportingEngine output into desktop P&L table rows."""
    rows: list[dict[str, Any]] = []

    def append_row(
        left_label: str,
        left_amount: Any,
        right_label: str,
        right_amount: Any,
        row_type: str = "",
    ) -> None:
        rows.append(
            {
                "left_particulars": left_label,
                "left_amount": left_amount or "",
                "right_particulars": right_label,
                "right_amount": right_amount or "",
                "row_type": row_type,
            }
        )

    gross_profit = float(result.get("gross_profit", 0) or 0)
    net_profit = float(result.get("net_profit", 0) or 0)

    rows.append(
        {
            "left_particulars": "TRADING ACCOUNT",
            "left_amount": "",
            "right_particulars": "",
            "right_amount": "",
            "row_type": "section",
        }
    )
    left_rows = [(f"To {acc['account_name']}", acc["balance"]) for acc in result.get("direct_expenses", [])]
    left_total = float(result.get("total_direct_expenses", 0) or 0)
    right_rows = [(f"By {acc['account_name']}", acc["balance"]) for acc in result.get("direct_incomes", [])]
    right_total = float(result.get("total_direct_incomes", 0) or 0)
    if gross_profit >= 0:
        left_rows.append(("To Gross Profit c/d", gross_profit))
        left_total += gross_profit
    else:
        right_rows.append(("By Gross Loss c/d", abs(gross_profit)))
        right_total += abs(gross_profit)
    final_total = max(left_total, right_total)
    for index in range(max(len(left_rows), len(right_rows))):
        left_label, left_amount = left_rows[index] if index < len(left_rows) else ("", 0)
        right_label, right_amount = right_rows[index] if index < len(right_rows) else ("", 0)
        append_row(left_label, left_amount, right_label, right_amount)
    append_row("Total", final_total, "Total", final_total, "total")

    rows.append(
        {
            "left_particulars": "PROFIT & LOSS ACCOUNT",
            "left_amount": "",
            "right_particulars": "",
            "right_amount": "",
            "row_type": "section",
        }
    )
    left_rows = [(f"To {acc['account_name']}", acc["balance"]) for acc in result.get("indirect_expenses", [])]
    left_total = float(result.get("total_indirect_expenses", 0) or 0)
    if gross_profit >= 0:
        right_rows = [("By Gross Profit b/d", gross_profit)]
        right_total = gross_profit
    else:
        left_rows.append(("To Gross Loss b/d", abs(gross_profit)))
        left_total += abs(gross_profit)
        right_rows = []
        right_total = 0.0
    for acc in result.get("indirect_incomes", []):
        right_rows.append((f"By {acc['account_name']}", acc["balance"]))
    right_total += float(result.get("total_indirect_incomes", 0) or 0)
    if net_profit >= 0:
        left_rows.append(("To Net Profit", net_profit))
        left_total += net_profit
    else:
        right_rows.append(("By Net Loss", abs(net_profit)))
        right_total += abs(net_profit)
    final_total = max(left_total, right_total)
    for index in range(max(len(left_rows), len(right_rows))):
        left_label, left_amount = left_rows[index] if index < len(left_rows) else ("", 0)
        right_label, right_amount = right_rows[index] if index < len(right_rows) else ("", 0)
        append_row(left_label, left_amount, right_label, right_amount)
    append_row("Total", final_total, "Total", final_total, "total")

    summary = {
        "gross_profit": gross_profit,
        "net_profit": net_profit,
        "total_direct_incomes": float(result.get("total_direct_incomes", 0) or 0),
        "total_direct_expenses": float(result.get("total_direct_expenses", 0) or 0),
        "total_indirect_incomes": float(result.get("total_indirect_incomes", 0) or 0),
        "total_indirect_expenses": float(result.get("total_indirect_expenses", 0) or 0),
    }
    return rows, summary


def build_balance_sheet_rows(result: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, float]]:
    """Shape FinancialReportingEngine output into desktop balance-sheet rows."""
    left_rows: list[tuple[str, float]] = []
    for acc in result.get("capital_accounts", []) or []:
        left_rows.append((acc.get("account_name", ""), float(acc.get("balance") or 0)))
    net_profit = float(result.get("net_profit", 0) or 0)
    if net_profit >= 0:
        left_rows.append(("Add: Net Profit", net_profit))
    else:
        left_rows.append(("Less: Net Loss", abs(net_profit)))
    for acc in result.get("current_liabilities", []) or []:
        left_rows.append((acc.get("account_name", ""), float(acc.get("balance") or 0)))

    right_rows: list[tuple[str, float]] = []
    for acc in result.get("fixed_assets", []) or []:
        right_rows.append((acc.get("account_name", ""), float(acc.get("balance") or 0)))
    for acc in result.get("current_assets", []) or []:
        right_rows.append((acc.get("account_name", ""), float(acc.get("balance") or 0)))

    left_total = abs(
        float(result.get("adjusted_capital", 0) or 0) + float(result.get("total_liabilities", 0) or 0)
    )
    right_total = abs(float(result.get("total_assets", 0) or 0))
    left_rows.append(("Total", left_total))
    right_rows.append(("Total", right_total))

    rows: list[dict[str, Any]] = []
    for index in range(max(len(left_rows), len(right_rows))):
        left_label, left_amount = left_rows[index] if index < len(left_rows) else ("", 0)
        right_label, right_amount = right_rows[index] if index < len(right_rows) else ("", 0)
        row_type = "total" if (left_label == "Total" or right_label == "Total") else ""
        rows.append(
            {
                "left_particulars": left_label,
                "left_amount": left_amount or "",
                "right_particulars": right_label,
                "right_amount": right_amount or "",
                "row_type": row_type,
            }
        )

    summary = {
        "net_profit": net_profit,
        "total_assets": float(result.get("total_assets", 0) or 0),
        "total_liabilities": float(result.get("total_liabilities", 0) or 0),
        "adjusted_capital": float(result.get("adjusted_capital", 0) or 0),
    }
    return rows, summary


def run_cloud_ledger_desktop_parity(
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Run Ledger views through the same LedgerLogic layer as the desktop app."""
    from bizora_core.ledger_logic import LedgerLogic

    memory_db = load_ledger_memory_db(fetch_table, company_id)
    logic = LedgerLogic(memory_db)
    from_dt = _parse_iso_date(filters.get("from_date"))
    to_dt = _parse_iso_date(filters.get("to_date"))
    view = str(filters.get("ledger_view") or "General")

    try:
        if view == "Debtors":
            rows = logic.get_debtor_summary(company_id, from_dt, to_dt)
        elif view == "Creditors":
            rows = logic.get_creditor_summary(company_id, from_dt, to_dt)
        elif view == "Cash/Bank":
            rows = logic.get_cash_bank_summary(company_id, from_dt, to_dt)
        else:
            rows = logic.get_general_account_summary(company_id, from_dt, to_dt)
    except Exception as exc:
        memory_db.force_disconnect()
        return {
            "success": False,
            "message": f"Ledger report failed: {exc}",
            "rows": [],
            "data_source": "supabase",
        }

    search = str(filters.get("search") or "").strip().lower()
    if search:
        rows = [row for row in rows if search in str(row.get("account_name", "")).lower()]

    result = _finish("ledger", rows, filters, "ledger")
    memory_db.force_disconnect()
    return result


def run_cloud_profit_and_loss(
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Run Profit and Loss through FinancialReportingEngine on synced ledger data."""
    from bizora_core.financial_reporting_engine import FinancialReportingEngine

    memory_db = load_ledger_memory_db(fetch_table, company_id)
    engine = FinancialReportingEngine(memory_db)
    from_text = _parse_date(filters.get("from_date") or date.today())
    to_text = _parse_date(filters.get("to_date") or date.today())

    try:
        result = engine.generate_profit_and_loss(company_id, from_text, to_text) or {}
        rows, summary = build_profit_and_loss_rows(result)
    except Exception as exc:
        memory_db.force_disconnect()
        return {
            "success": False,
            "message": f"Profit and Loss failed: {exc}",
            "rows": [],
            "data_source": "supabase",
        }

    payload = _finish(
        "profit-and-loss-account",
        rows,
        filters,
        "profit_and_loss",
        meta=result,
        summary=summary,
        summary_labels={
            "gross_profit": "Gross Profit",
            "net_profit": "Net Profit",
            "total_direct_incomes": "Direct Incomes",
            "total_direct_expenses": "Direct Expenses",
            "total_indirect_incomes": "Indirect Incomes",
            "total_indirect_expenses": "Indirect Expenses",
        },
    )
    memory_db.force_disconnect()
    return payload


def run_cloud_balance_sheet(
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Run Balance Sheet through FinancialReportingEngine on synced ledger data."""
    from bizora_core.financial_reporting_engine import FinancialReportingEngine

    memory_db = load_ledger_memory_db(fetch_table, company_id)
    engine = FinancialReportingEngine(memory_db)
    as_of_text = _parse_date(filters.get("as_of_date") or filters.get("to_date") or date.today())

    try:
        result = engine.generate_balance_sheet(company_id, as_of_text) or {}
        rows, summary = build_balance_sheet_rows(result)
    except Exception as exc:
        memory_db.force_disconnect()
        return {
            "success": False,
            "message": f"Balance Sheet failed: {exc}",
            "rows": [],
            "data_source": "supabase",
        }

    payload = _finish(
        "balance-sheet",
        rows,
        filters,
        "balance_sheet",
        meta=result,
        summary=summary,
        summary_labels={
            "net_profit": "Net Profit",
            "total_assets": "Total Assets",
            "total_liabilities": "Total Liabilities",
            "adjusted_capital": "Adjusted Capital",
        },
    )
    memory_db.force_disconnect()
    return payload

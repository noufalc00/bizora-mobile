"""Shape account-ledger data like the desktop Ledger page detail grid."""

from __future__ import annotations

from typing import Any, Mapping

from utils.date_display import format_display_date

DESKTOP_LEDGER_SUMMARY_LABELS: dict[str, str] = {
    "opening_balance": "Opening",
    "period_debit": "Debit",
    "period_credit": "Credit",
    "closing_balance": "Closing",
}

# Bump when ledger-statement row shaping changes (used by /api/status).
LEDGER_STATEMENT_FORMAT_VERSION = 2


def pretty_voucher_type(value: Any) -> str:
    """Match ``LedgerPageWidget.pretty_voucher_type``."""
    return str(value or "").replace("_", " ").title()


def format_signed_balance(net: float) -> str:
    """Match desktop running-balance cells (Dr/Cr suffix)."""
    rounded = round(float(net or 0), 2)
    if abs(rounded) < 0.001:
        return "0.00"
    if rounded >= 0:
        return f"{abs(rounded):,.2f} Dr"
    return f"{abs(rounded):,.2f} Cr"


def resolve_ledger_account_id(filters: Mapping[str, Any] | None) -> int | None:
    """Return one explicit ledger account id from mobile ledger filters."""
    for key in ("search", "account_id"):
        raw = (filters or {}).get(key)
        if raw in (None, "", 0):
            continue
        text = str(raw).strip()
        if text.isdigit():
            return int(text)
    return None


def ledger_summary_totals(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Match desktop ledger summary footer totals."""
    opening = 0.0
    debit = 0.0
    credit = 0.0
    for row in rows:
        try:
            opening += float(row.get("opening_balance") or 0.0)
        except (TypeError, ValueError):
            pass
        try:
            debit += float(row.get("period_debit") or 0.0)
        except (TypeError, ValueError):
            pass
        try:
            credit += float(row.get("period_credit") or 0.0)
        except (TypeError, ValueError):
            pass
    return {
        "opening_balance": round(opening, 2),
        "period_debit": round(debit, 2),
        "period_credit": round(credit, 2),
    }


def _float_value(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def build_desktop_ledger_statement_payload(
    ledger_result: dict[str, Any],
    *,
    account_id: int,
    account_name: str = "",
) -> dict[str, Any]:
    """Return rows and summary matching ``ui/ledger_page.populate_detailed``."""
    account = ledger_result.get("account") or {}
    if not account_name:
        account_name = str(account.get("account_name") or "Selected Account")

    raw_entries = ledger_result.get("entries") or []
    opening = _float_value(ledger_result.get("opening_balance"))
    closing = _float_value(ledger_result.get("closing_balance"))
    period_debit = _float_value(ledger_result.get("period_debit"))
    period_credit = _float_value(ledger_result.get("period_credit"))
    if not period_debit and not period_credit and raw_entries:
        period_debit = sum(_float_value(entry.get("debit")) for entry in raw_entries)
        period_credit = sum(_float_value(entry.get("credit")) for entry in raw_entries)

    opening_row = {
        "voucher_date": "",
        "voucher_type": "Opening Balance",
        "voucher_no": "",
        "particulars": account_name,
        "debit": "",
        "credit": "",
        "running_balance": opening,
        "running_balance_display": format_signed_balance(opening),
        "row_type": "opening",
        "account_id": account_id,
    }

    entry_rows: list[dict[str, Any]] = []
    for entry in raw_entries:
        debit = _float_value(entry.get("debit"))
        credit = _float_value(entry.get("credit"))
        running = _float_value(entry.get("running_balance"))
        narration = str(entry.get("narration") or "")
        entry_rows.append(
            {
                "voucher_date": format_display_date(entry.get("voucher_date")),
                "voucher_type": pretty_voucher_type(entry.get("voucher_type")),
                "voucher_no": str(entry.get("voucher_no") or ""),
                "particulars": narration,
                "narration": narration,
                "debit": debit,
                "credit": credit,
                "running_balance": running,
                "running_balance_display": format_signed_balance(running),
                "account_id": account_id,
                "voucher_id": entry.get("voucher_id"),
                "id": entry.get("id"),
            }
        )

    closing_row = {
        "voucher_date": "",
        "voucher_type": "Closing Balance",
        "voucher_no": "",
        "particulars": account_name,
        "debit": "",
        "credit": "",
        "running_balance": closing,
        "running_balance_display": format_signed_balance(closing),
        "row_type": "closing_balance",
        "account_id": account_id,
    }

    return {
        "rows": [opening_row] + entry_rows + [closing_row],
        "summary": {
            "opening_balance": opening,
            "period_debit": period_debit,
            "period_credit": period_credit,
            "closing_balance": closing,
        },
        "summary_labels": dict(DESKTOP_LEDGER_SUMMARY_LABELS),
        "ledger_statement_format": LEDGER_STATEMENT_FORMAT_VERSION,
    }

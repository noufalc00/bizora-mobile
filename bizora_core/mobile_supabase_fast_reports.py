"""
Fast-path Books/Reports handlers backed by Supabase views + RPC functions.

These bypass the SQLite hydration bridge for reports whose logic has been
mirrored in `sql/supabase_views_functions.sql`. When an RPC is missing or
returns an error, callers should fall back to the desktop bridge so the
web app never surfaces partial data.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable

from bizora_core.mobile_report_columns import build_slug_table_payload

# Route slug -> RPC handler dispatcher key.
FAST_PATH_HANDLERS: dict[str, str] = {
    "trial-balance": "trial_balance",
    "monthly-analysis": "monthly_analysis",
}


class FastPathUnavailable(RuntimeError):
    """Raised when a Supabase RPC is missing so callers can fall back."""


def _parse_iso(value: Any, fallback: date | None = None) -> str:
    """Normalize incoming filter dates to ISO YYYY-MM-DD strings."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    text = str(value or "").strip()[:10]
    if text:
        return text
    return (fallback or date.today()).isoformat()


def _call_rpc(client: Any, name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Invoke a Postgres RPC through Supabase, mapping missing RPCs to a fallback."""
    try:
        response = client.rpc(name, params).execute()
    except Exception as exc:
        message = str(exc)
        if "Could not find the function" in message or "PGRST202" in message:
            raise FastPathUnavailable(name) from exc
        raise
    return response.data or []


def _run_trial_balance(
    client: Any,
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Trial Balance via `f_trial_balance` RPC."""
    account_type = str(filters.get("account_type") or "All").strip() or "All"
    search_raw = filters.get("search")
    search_value: str | None = str(search_raw).strip() if search_raw else None
    if not search_value:
        search_value = None
    rows = _call_rpc(
        client,
        "f_trial_balance",
        {
            "p_company_id": int(company_id),
            "p_from_date": _parse_iso(filters.get("from_date")),
            "p_to_date": _parse_iso(filters.get("to_date")),
            "p_account_type": account_type,
            "p_search": search_value,
        },
    )
    for row in rows:
        row["sl_no"] = int(row.get("sl_no") or 0)
    totals: dict[str, float] = {
        "opening_debit": 0.0,
        "opening_credit": 0.0,
        "period_debit": 0.0,
        "period_credit": 0.0,
        "closing_debit": 0.0,
        "closing_credit": 0.0,
    }
    for row in rows:
        for key in totals:
            totals[key] += float(row.get(key) or 0.0)
    return {
        "success": True,
        "message": "",
        "rows": rows,
        "totals": totals,
        "summary": totals,
        "summary_labels": {
            "opening_debit": "Opening Dr",
            "opening_credit": "Opening Cr",
            "period_debit": "Period Dr",
            "period_credit": "Period Cr",
            "closing_debit": "Closing Dr",
            "closing_credit": "Closing Cr",
        },
        "data_source": "supabase_view",
    }


_MONTH_NAMES: dict[int, str] = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}


def _resolve_financial_year_window(filters: dict[str, Any]) -> tuple[str, str, str]:
    """Return (from_date, to_date, fy_label) matching desktop MonthlyAnalysisLogic.

    Precedence:
        1. explicit filters.financial_year like '2026-27' -> April 1 to March 31.
        2. filters.from_date + filters.to_date if both present.
        3. get_working_financial_year_label() (desktop-shared default).
        4. current-year fallback based on today's month.
    """
    fy_label = str(filters.get("financial_year") or "").strip()
    if not fy_label:
        try:
            from utils.financial_year import get_working_financial_year_label

            fy_label = (get_working_financial_year_label() or "").strip()
        except Exception:
            fy_label = ""

    if not fy_label and filters.get("from_date") and filters.get("to_date"):
        return (
            _parse_iso(filters.get("from_date")),
            _parse_iso(filters.get("to_date")),
            "",
        )

    if not fy_label:
        today = date.today()
        start = today.year if today.month >= 4 else today.year - 1
        fy_label = f"{start}-{str(start + 1)[-2:]}"

    start_year = int(fy_label.split("-", 1)[0])
    return (
        f"{start_year}-04-01",
        f"{start_year + 1}-03-31",
        fy_label,
    )


def _financial_year_month_keys(fy_from: str, fy_to: str) -> list[tuple[int, int]]:
    """Enumerate (year, month) pairs for every month in the requested window."""
    start = datetime.strptime(fy_from, "%Y-%m-%d")
    end = datetime.strptime(fy_to, "%Y-%m-%d")
    keys: list[tuple[int, int]] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        keys.append((year, month))
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return keys


def _run_monthly_analysis(
    client: Any,
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Monthly Analysis via `f_monthly_analysis` RPC.

    Mirrors MonthlyAnalysisLogic on the desktop:
      * takes the financial-year window (default April to March)
      * zero-fills every month in the window, even when no ledger rows exist,
        so callers get a stable 12-row payload for the FY.
    """
    from_date, to_date, _fy_label = _resolve_financial_year_window(filters)
    rows = _call_rpc(
        client,
        "f_monthly_analysis",
        {
            "p_company_id": int(company_id),
            "p_from_date": from_date,
            "p_to_date": to_date,
        },
    )

    zero_row = lambda year, month: {
        "fy_year": year,
        "fy_month": month,
        "year": year,
        "month": month,
        "month_name": _MONTH_NAMES.get(month, str(month)),
        "trading_income": 0.0,
        "direct_expenses": 0.0,
        "indirect_income": 0.0,
        "indirect_expenses": 0.0,
        "gross_profit": 0.0,
        "net_profit": 0.0,
        "month_label": f"{_MONTH_NAMES.get(month, str(month))} {year}",
    }

    by_key: dict[tuple[int, int], dict[str, Any]] = {
        key: zero_row(*key) for key in _financial_year_month_keys(from_date, to_date)
    }

    for row in rows:
        year = int(row.get("out_fy_year") or row.get("fy_year") or 0)
        month = int(row.get("out_fy_month") or row.get("fy_month") or 0)
        if not year or not month:
            continue
        target = by_key.get((year, month))
        if target is None:
            target = zero_row(year, month)
            by_key[(year, month)] = target
        target["trading_income"] = float(row.get("out_trading_income") or row.get("trading_income") or 0)
        target["direct_expenses"] = float(row.get("out_direct_expenses") or row.get("direct_expenses") or 0)
        target["indirect_income"] = float(row.get("out_indirect_income") or row.get("indirect_income") or 0)
        target["indirect_expenses"] = float(row.get("out_indirect_expenses") or row.get("indirect_expenses") or 0)
        target["gross_profit"] = float(row.get("out_gross_profit") or row.get("gross_profit") or 0)
        target["net_profit"] = float(row.get("out_net_profit") or row.get("net_profit") or 0)
        month_name = row.get("out_month_name") or row.get("month_name") or _MONTH_NAMES.get(month, str(month))
        target["month_name"] = month_name
        target["month_label"] = f"{str(month_name).strip()} {year}"

    normalized: list[dict[str, Any]] = [by_key[key] for key in sorted(by_key.keys())]

    summary = {
        "trading_income": round(sum(float(r.get("trading_income") or 0) for r in normalized), 2),
        "direct_expenses": round(sum(float(r.get("direct_expenses") or 0) for r in normalized), 2),
        "indirect_income": round(sum(float(r.get("indirect_income") or 0) for r in normalized), 2),
        "indirect_expenses": round(sum(float(r.get("indirect_expenses") or 0) for r in normalized), 2),
        "gross_profit": round(sum(float(r.get("gross_profit") or 0) for r in normalized), 2),
        "net_profit": round(sum(float(r.get("net_profit") or 0) for r in normalized), 2),
    }
    return {
        "success": True,
        "message": "",
        "rows": normalized,
        "summary": summary,
        "summary_labels": {
            "trading_income": "Trading Income",
            "direct_expenses": "Direct Expenses",
            "indirect_income": "Indirect Income",
            "indirect_expenses": "Indirect Expenses",
            "gross_profit": "Gross Profit",
            "net_profit": "Net Profit",
        },
        "data_source": "supabase_view",
    }


def try_run_fast_report(
    client_factory: Callable[[], Any],
    slug: str,
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any] | None:
    """Run one fast-path report or return None so the caller falls back."""
    handler_key = FAST_PATH_HANDLERS.get(slug)
    if not handler_key:
        return None
    client = client_factory()
    try:
        if handler_key == "trial_balance":
            result = _run_trial_balance(client, company_id, filters)
        elif handler_key == "monthly_analysis":
            result = _run_monthly_analysis(client, company_id, filters)
        else:
            return None
    except FastPathUnavailable as exc:
        print(f"[MOBILE-FAST] RPC '{exc}' missing; falling back to SQLite bridge.")
        return None
    except Exception as exc:
        print(f"[MOBILE-FAST] '{slug}' fast-path failed: {exc}")
        return None

    payload = build_slug_table_payload(slug, result.get("rows") or [], handler=handler_key, filters=filters)
    return {**result, **payload}

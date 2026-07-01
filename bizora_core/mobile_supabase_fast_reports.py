"""
Fast-path Books/Reports handlers backed by Supabase views + RPC functions.

These bypass the SQLite hydration bridge for reports whose logic has been
mirrored in `sql/supabase_views_functions.sql`. When an RPC is missing or
returns an error, callers should fall back to the desktop bridge so the
web app never surfaces partial data.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Callable

from bizora_core.mobile_report_columns import build_slug_table_payload

# Structured logger so FastAPI/uvicorn can route these to the same
# handlers as everything else. `print` calls remain for parity with the
# rest of the codebase; drop the print calls once the whole app has
# migrated to logging.
log = logging.getLogger("bizora.mobile.fast_reports")

# Route slug -> RPC handler dispatcher key.
FAST_PATH_HANDLERS: dict[str, str] = {
    "trial-balance": "trial_balance",
    "monthly-analysis": "monthly_analysis",
    "cash-book": "cash_book",
}


class FastPathUnavailable(RuntimeError):
    """Raised when a Supabase RPC is missing so callers can fall back."""


# ---- error classification helpers -----------------------------------------

def _extract_error_meta(exc: BaseException) -> dict[str, Any]:
    """Pull code / message / status / details out of any RPC exception shape.

    supabase-py 2.x raises `postgrest.exceptions.APIError` which is dict-like
    (code / message / hint / details). httpx / requests raise their own
    exception types. Wrap everything into a normalized dict so downstream
    classification can inspect a single shape.
    """
    meta: dict[str, Any] = {
        "type": type(exc).__name__,
        "message": str(exc),
        "code": None,
        "status": None,
        "hint": None,
        "details": None,
    }

    # supabase-py APIError: attributes vary across versions - try both.
    for attr in ("code", "status_code", "hint", "details", "message"):
        value = getattr(exc, attr, None)
        if value not in (None, ""):
            meta[attr if attr != "status_code" else "status"] = value

    # Some drivers stash the payload on .args[0] as a dict.
    if not meta["code"] and exc.args and isinstance(exc.args[0], dict):
        payload = exc.args[0]
        for key in ("code", "message", "hint", "details"):
            if payload.get(key) not in (None, ""):
                meta[key] = payload[key]
        if payload.get("status") and not meta["status"]:
            meta["status"] = payload["status"]

    # httpx response wrappers occasionally attach .response.
    response = getattr(exc, "response", None)
    if response is not None:
        status = getattr(response, "status_code", None)
        if status and not meta["status"]:
            meta["status"] = status

    return meta


def _classify_rpc_error(exc: BaseException) -> str:
    """Return a short category tag for one RPC exception.

    Categories:
        TIMEOUT           - request timed out on network or Postgres side
        UNAUTHORIZED      - 401 / invalid JWT / missing API key
        FORBIDDEN         - 403 / RLS violation / insufficient privilege
        NOT_INSTALLED     - PGRST202 (schema cache says function is missing)
        DB_ERROR          - Postgres SQLSTATE / 5xx / query structure error
        NETWORK           - connection refused, DNS, TLS handshake
        UNKNOWN           - fall-through for surprising exceptions
    """
    meta = _extract_error_meta(exc)
    message = (meta.get("message") or "").lower()
    code = str(meta.get("code") or "").upper()
    status = meta.get("status")

    if isinstance(exc, TimeoutError) or "timeout" in message or "timed out" in message:
        return "TIMEOUT"
    if status == 401 or code in {"PGRST301", "PGRST303"} or "jwt" in message or "unauthorized" in message or "invalid api key" in message:
        return "UNAUTHORIZED"
    if status == 403 or code == "42501" or "row-level security" in message or "forbidden" in message:
        return "FORBIDDEN"
    if code == "PGRST202" or "could not find the function" in message:
        return "NOT_INSTALLED"
    if isinstance(status, int) and 500 <= status < 600:
        return "DB_ERROR"
    # PostgreSQL SQLSTATE is 5 alphanumeric characters, e.g. 42P01, 23505, 08006.
    # PostgREST codes (PGRST202 / PGRST301) are 8 chars so this doesn't collide.
    if len(code) == 5 and code.isalnum():
        return "DB_ERROR"
    if "structure of query does not match" in message or "ambiguous" in message or "syntax error" in message:
        return "DB_ERROR"
    if isinstance(exc, (ConnectionError, OSError)) and not status:
        return "NETWORK"
    if "connection refused" in message or "name resolution" in message or "handshake" in message:
        return "NETWORK"
    return "UNKNOWN"


def _describe_rpc_failure(rpc_name: str, params: dict[str, Any], exc: BaseException) -> str:
    """Build a compact, log-safe one-liner describing an RPC failure."""
    meta = _extract_error_meta(exc)
    category = _classify_rpc_error(exc)
    # Redact any obviously sensitive param values (search terms with PII, etc).
    safe_params = {key: value for key, value in params.items() if key != "p_search"}
    return (
        f"category={category} rpc='{rpc_name}' "
        f"exc={meta['type']} status={meta.get('status')} code={meta.get('code')} "
        f"message={meta.get('message')!r} hint={meta.get('hint')!r} "
        f"params={safe_params}"
    )


def _parse_iso(value: Any, fallback: date | None = None) -> str:
    """Normalize incoming filter dates to ISO YYYY-MM-DD strings."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    text = str(value or "").strip()[:10]
    if text:
        return text
    return (fallback or date.today()).isoformat()


def _call_rpc(client: Any, name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Invoke a Postgres RPC through Supabase, mapping missing RPCs to a fallback.

    Every failure path emits a structured `FAST-PATH RPC ERROR` log line
    that includes a classification tag (TIMEOUT / UNAUTHORIZED / FORBIDDEN
    / NOT_INSTALLED / DB_ERROR / NETWORK / UNKNOWN) so operators can
    triage from the log without repro. Missing RPCs are re-raised as
    `FastPathUnavailable` so callers can silently fall back to the bridge.
    """
    try:
        response = client.rpc(name, params).execute()
    except Exception as exc:
        details = _describe_rpc_failure(name, params, exc)
        category = _classify_rpc_error(exc)
        if category == "NOT_INSTALLED":
            # Expected condition when a project hasn't run the master
            # SQL script yet - log at INFO so it doesn't wake anyone up.
            print(f"[MOBILE-FAST] FAST-PATH RPC NOT INSTALLED ({details}); falling back to bridge.")
            log.info("fast-path rpc not installed: %s", details)
            raise FastPathUnavailable(name) from exc

        # Every other category is unexpected. Print for stdout consumers
        # (dev / basic FastAPI) plus a structured error log with the full
        # traceback for aggregators (prod). The outer `try_run_fast_report`
        # will *not* re-log the traceback so we stay noise-free.
        print(f"[MOBILE-FAST] FAST-PATH RPC ERROR: {details}")
        log.error("fast-path rpc failed: %s", details, exc_info=exc)
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


def _run_cash_book(
    client: Any,
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Cash Book via `f_cash_book` RPC.

    Mirrors `CashBookLogic.get_cash_book` on the desktop:
      * cash-account is discovered inside the RPC (Cash Account, then Cash).
      * per-entry contra-account lookup is done in SQL via a scalar
        subquery so we don't need a Python round-trip per row.
      * running balance and opening/total/closing figures are computed
        server-side with window functions.

    The RPC returns:
      * `out_row_type='entry'`  rows carrying real entry data.
      * one trailing `out_row_type='summary'` row that always exists,
        even when the entry set is empty, so callers still receive
        opening/closing balances.
    """
    from_date = _parse_iso(filters.get("from_date"))
    to_date = _parse_iso(filters.get("to_date"))
    raw = _call_rpc(
        client,
        "f_cash_book",
        {
            "p_company_id": int(company_id),
            "p_from_date": from_date,
            "p_to_date": to_date,
        },
    )

    entries: list[dict[str, Any]] = []
    summary = {
        "opening_balance": 0.0,
        "total_receipts": 0.0,
        "total_payments": 0.0,
        "closing_balance": 0.0,
    }

    def _f(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    for row in raw:
        row_type = str(row.get("out_row_type") or "entry").strip().lower()
        if row_type == "summary":
            # Only the trailing summary row carries these fields.
            summary["opening_balance"] = _f(row.get("out_opening_balance"))
            summary["total_receipts"] = _f(row.get("out_total_receipts"))
            summary["total_payments"] = _f(row.get("out_total_payments"))
            summary["closing_balance"] = _f(row.get("out_closing_balance"))
            continue
        # Entry row: strip the `out_` prefix so downstream column
        # rendering / QA parity finds the same keys the bridge emits.
        entries.append(
            {
                "voucher_date": row.get("out_voucher_date"),
                "voucher_no": row.get("out_voucher_no") or "",
                "voucher_type": row.get("out_voucher_type") or "",
                "particulars": row.get("out_particulars") or "Unknown",
                "narration": row.get("out_narration") or "",
                "debit": _f(row.get("out_debit")),
                "credit": _f(row.get("out_credit")),
                "running_balance": _f(row.get("out_running_balance")),
            }
        )

    return {
        "success": True,
        "message": "",
        "rows": entries,
        "summary": summary,
        "summary_labels": {
            "opening_balance": "Opening Balance",
            "total_receipts": "Total Receipts",
            "total_payments": "Total Payments",
            "closing_balance": "Closing Balance",
        },
        "data_source": "supabase_view",
    }


def try_run_fast_report(
    client_factory: Callable[[], Any],
    slug: str,
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any] | None:
    """Run one fast-path report or return None so the caller falls back.

    Every exit reason is logged with an explicit tag so we can trace why
    a given request bypassed the fast path:
        - SKIPPED           : slug is not on the fast-path allow list
        - RPC_NOT_INSTALLED : function missing on Supabase (expected)
        - RPC_ERROR         : anything else that came back from PostgREST
        - HANDLER_ERROR     : the fast-path handler itself blew up in Python
    """
    handler_key = FAST_PATH_HANDLERS.get(slug)
    if not handler_key:
        log.debug("fast-path SKIPPED for '%s' (no handler mapped)", slug)
        return None
    client = client_factory()
    try:
        if handler_key == "trial_balance":
            result = _run_trial_balance(client, company_id, filters)
        elif handler_key == "monthly_analysis":
            result = _run_monthly_analysis(client, company_id, filters)
        elif handler_key == "cash_book":
            result = _run_cash_book(client, company_id, filters)
        else:
            return None
    except FastPathUnavailable as exc:
        # _call_rpc already logged category=NOT_INSTALLED for us; here we
        # just add the slug context so the two lines line up in the log.
        print(f"[MOBILE-FAST] slug='{slug}' RPC_NOT_INSTALLED rpc='{exc}'; using bridge.")
        log.info("fast-path RPC_NOT_INSTALLED slug=%s rpc=%s", slug, exc)
        return None
    except Exception as exc:
        # _call_rpc already emitted the traceback via log.error(exc_info=exc).
        # Here we just add a slug-scoped summary so operators can grep by slug.
        category = _classify_rpc_error(exc)
        print(
            f"[MOBILE-FAST] FAST-PATH RPC ERROR: slug='{slug}' category={category} "
            f"exc={type(exc).__name__} message={str(exc)!r}"
        )
        log.error("fast-path failed slug=%s category=%s exc=%s", slug, category, exc)
        return None

    payload = build_slug_table_payload(slug, result.get("rows") or [], handler=handler_key, filters=filters)
    return {**result, **payload}

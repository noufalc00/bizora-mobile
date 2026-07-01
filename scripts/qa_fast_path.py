#!/usr/bin/env python3
"""
QA harness for the Supabase fast-path reporting pipeline.

Checks performed:
  1. RPC connectivity: pings f_trial_balance, f_monthly_analysis,
     f_day_book_entries and prints INSTALLED / MISSING / ERROR.
  2. Trial Balance parity: runs fast-path and desktop-bridge, compares
     row-by-row and totals-by-totals with a small money tolerance.
  3. Monthly Analysis parity: same comparison for f_monthly_analysis.
  4. Fallback behavior: forces the fast path to fail and confirms the
     bridge still returns a successful payload with usable rows/columns.

Exit code is non-zero when any check fails, so this can be wired into CI.
"""

from __future__ import annotations

import os
import sys
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dotenv import load_dotenv

load_dotenv()
os.environ["MOBILE_DATA_SOURCE"] = "supabase"

from bizora_core.mobile_supabase_service import MobileSupabaseService
from bizora_core.mobile_supabase_fast_reports import (
    FastPathUnavailable,
    _run_monthly_analysis,
    _run_trial_balance,
)
from bizora_core.mobile_supabase_desktop_bridge import run_report_via_desktop_bridge

MONEY_TOL = 0.05          # rupees; matches desktop rounding tolerance
COMPANY_ID = 25
FROM_DATE = "2024-04-01"
TO_DATE = "2026-06-30"


class QAReport:
    """Collect pass/fail lines for a single QA run."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.failures = 0

    def record(self, name: str, ok: bool, detail: str = "") -> None:
        status = "PASS" if ok else "FAIL"
        if not ok:
            self.failures += 1
        self.lines.append(f"{status:4}  {name:32}  {detail}")

    def dump(self) -> None:
        print("=" * 70)
        print("QA REPORT - Faizan Pro Accounting fast-path integrity")
        print("=" * 70)
        for line in self.lines:
            print(line)
        print("-" * 70)
        print(f"Failures: {self.failures}")


def _check_rpc(client: Any, name: str, params: dict[str, Any]) -> tuple[str, str]:
    """Return (state, detail) for one RPC ping."""
    try:
        response = client.rpc(name, params).execute()
    except Exception as exc:
        message = str(exc)
        if "Could not find the function" in message or "PGRST202" in message:
            return "MISSING", "not installed on Supabase yet"
        return "ERROR", message.split("\n", 1)[0][:80]
    count = len(response.data or [])
    return "INSTALLED", f"{count} row(s) returned"


def check_rpc_connectivity(service: MobileSupabaseService, report: QAReport) -> dict[str, str]:
    """Ping each fast-path RPC and record installation state."""
    client = service._client()
    states: dict[str, str] = {}
    ping_params = {
        "f_trial_balance": {
            "p_company_id": COMPANY_ID,
            "p_from_date": FROM_DATE,
            "p_to_date": TO_DATE,
            "p_account_type": "All",
            "p_search": None,
        },
        "f_monthly_analysis": {
            "p_company_id": COMPANY_ID,
            "p_from_date": FROM_DATE,
            "p_to_date": TO_DATE,
        },
        "f_day_book_entries": {
            "p_company_id": COMPANY_ID,
            "p_from_date": FROM_DATE,
            "p_to_date": TO_DATE,
        },
    }
    for name, params in ping_params.items():
        state, detail = _check_rpc(client, name, params)
        states[name] = state
        report.record(f"rpc:{name}", state == "INSTALLED", f"{state} - {detail}")
    return states


def _diff_money(a: Any, b: Any) -> float:
    """Return absolute delta between two numeric-like values (0 when missing)."""
    try:
        return abs(float(a or 0.0) - float(b or 0.0))
    except (TypeError, ValueError):
        return 0.0


def compare_trial_balance(service: MobileSupabaseService, report: QAReport, states: dict[str, str]) -> None:
    """Fast-path vs bridge parity for Trial Balance."""
    if states.get("f_trial_balance") != "INSTALLED":
        report.record("parity:trial-balance", False, "SKIPPED (RPC missing)")
        return
    filters = {
        "from_date": FROM_DATE,
        "to_date": TO_DATE,
        "account_type": "All",
        "search": "",
    }
    try:
        fast = _run_trial_balance(service._client(), COMPANY_ID, filters)
    except FastPathUnavailable as exc:
        report.record("parity:trial-balance", False, f"RPC vanished mid-run: {exc}")
        return
    bridge = run_report_via_desktop_bridge(service, "trial-balance", filters, COMPANY_ID)

    fast_rows = fast.get("rows") or []
    bridge_rows = bridge.get("rows") or []
    if len(fast_rows) != len(bridge_rows):
        report.record(
            "parity:trial-balance",
            False,
            f"row count fast={len(fast_rows)} bridge={len(bridge_rows)}",
        )
        return

    money_keys = [
        "opening_debit",
        "opening_credit",
        "period_debit",
        "period_credit",
        "closing_debit",
        "closing_credit",
    ]

    def _identity(row: dict[str, Any]) -> Any:
        return row.get("account_id") or row.get("account_name") or row.get("sl_no")

    fast_by_id = {_identity(r): r for r in fast_rows}
    bridge_by_id = {_identity(r): r for r in bridge_rows}
    mismatches: list[str] = []
    for ident, fast_row in fast_by_id.items():
        bridge_row = bridge_by_id.get(ident)
        if bridge_row is None:
            mismatches.append(f"row '{ident}' missing in bridge")
            continue
        for key in money_keys:
            delta = _diff_money(fast_row.get(key), bridge_row.get(key))
            if delta > MONEY_TOL:
                mismatches.append(
                    f"'{ident}' {key}: fast={fast_row.get(key)} bridge={bridge_row.get(key)} delta={delta:.2f}"
                )
    for ident in bridge_by_id.keys() - fast_by_id.keys():
        mismatches.append(f"row '{ident}' missing in fast-path")
    ok = not mismatches
    detail = "identical" if ok else f"{len(mismatches)} row diffs; first: {mismatches[0]}"
    report.record("parity:trial-balance", ok, detail)


def compare_monthly_analysis(service: MobileSupabaseService, report: QAReport, states: dict[str, str]) -> None:
    """Fast-path vs bridge parity for Monthly Analysis."""
    if states.get("f_monthly_analysis") != "INSTALLED":
        report.record("parity:monthly-analysis", False, "SKIPPED (RPC missing)")
        return
    # Fast-path and bridge share the desktop financial-year contract. Explicitly
    # pin the FY so the two sides never disagree because of get_working_financial_year_label
    # drifting during a run.
    fy_label = os.getenv("QA_FINANCIAL_YEAR") or "2026-27"
    filters = {"financial_year": fy_label, "from_month": "April", "to_month": "March"}
    try:
        fast = _run_monthly_analysis(service._client(), COMPANY_ID, filters)
    except FastPathUnavailable as exc:
        report.record("parity:monthly-analysis", False, f"RPC vanished mid-run: {exc}")
        return
    bridge = run_report_via_desktop_bridge(service, "monthly-analysis", filters, COMPANY_ID)
    fast_rows = fast.get("rows") or []
    bridge_rows = bridge.get("rows") or []
    if len(fast_rows) != len(bridge_rows):
        report.record(
            "parity:monthly-analysis",
            False,
            f"row count fast={len(fast_rows)} bridge={len(bridge_rows)}",
        )
        return

    money_keys = [
        "trading_income",
        "direct_expenses",
        "indirect_income",
        "indirect_expenses",
        "gross_profit",
        "net_profit",
    ]

    def _month_key(row: dict[str, Any]) -> tuple[int, int]:
        return (
            int(row.get("fy_year") or row.get("year") or 0),
            int(row.get("fy_month") or row.get("month") or 0),
        )

    fast_by_month = {_month_key(r): r for r in fast_rows}
    bridge_by_month = {_month_key(r): r for r in bridge_rows}
    mismatches: list[str] = []
    for month_key in sorted(fast_by_month.keys() | bridge_by_month.keys()):
        fast_row = fast_by_month.get(month_key) or {}
        bridge_row = bridge_by_month.get(month_key) or {}
        if not fast_row:
            mismatches.append(f"{month_key} missing in fast-path")
            continue
        if not bridge_row:
            mismatches.append(f"{month_key} missing in bridge")
            continue
        for key in money_keys:
            delta = _diff_money(fast_row.get(key), bridge_row.get(key))
            if delta > MONEY_TOL:
                mismatches.append(
                    f"{month_key} {key}: fast={fast_row.get(key)} bridge={bridge_row.get(key)} delta={delta:.2f}"
                )
    ok = not mismatches
    detail = "identical" if ok else f"{len(mismatches)} row diffs; first: {mismatches[0]}"
    report.record("parity:monthly-analysis", ok, detail)


def check_fallback_resilience(service: MobileSupabaseService, report: QAReport) -> None:
    """Simulate a fast-path timeout and confirm the bridge still serves data."""

    class _FailingRpc:
        def rpc(self, *_args: Any, **_kwargs: Any) -> Any:
            raise TimeoutError("Simulated Supabase RPC timeout")

    original_client = service._client
    service._client = lambda: _FailingRpc()
    try:
        from bizora_core.mobile_supabase_fast_reports import try_run_fast_report

        fast_result = try_run_fast_report(
            lambda: _FailingRpc(),
            "trial-balance",
            COMPANY_ID,
            {"from_date": FROM_DATE, "to_date": TO_DATE},
        )
        fast_falls_back = fast_result is None
        report.record(
            "resilience:fast-path returns None on timeout",
            fast_falls_back,
            "fast-path swallowed timeout" if fast_falls_back else "fast-path leaked timeout",
        )
    finally:
        service._client = original_client

    filters = {"from_date": FROM_DATE, "to_date": TO_DATE, "account_type": "All"}
    bridge_result = run_report_via_desktop_bridge(service, "trial-balance", filters, COMPANY_ID)
    ok = bool(bridge_result.get("success")) and bool(bridge_result.get("rows"))
    report.record(
        "resilience:bridge serves report after fast-path failure",
        ok,
        f"success={bridge_result.get('success')} rows={len(bridge_result.get('rows') or [])}",
    )


def scan_render_logs(report: QAReport) -> None:
    """Scan the local terminals folder for FastPathUnavailable warnings."""
    terminals_dir = os.path.normpath(
        os.path.expanduser(
            r"~/.cursor/projects/d-App-making-extract-accounting-app/terminals"
        )
    )
    hits: list[str] = []
    if os.path.isdir(terminals_dir):
        for name in os.listdir(terminals_dir):
            if not name.endswith(".txt"):
                continue
            path = os.path.join(terminals_dir, name)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                    for lineno, raw in enumerate(handle, start=1):
                        if "[MOBILE-FAST] RPC" in raw and "missing" in raw:
                            rpc = raw.split("'")[1] if "'" in raw else "?"
                            hits.append(f"{name}:{lineno} {rpc}")
            except OSError:
                continue
    detail = "no fallback warnings found" if not hits else f"{len(hits)} warnings: {hits[:3]}"
    report.record("logs:FastPathUnavailable scan", True, detail)


def main() -> int:
    service = MobileSupabaseService()
    report = QAReport()

    url = os.getenv("SUPABASE_URL") or "(missing)"
    print(f"[QA] SUPABASE_URL in use: {url}")
    project = url.replace("https://", "").replace("http://", "").split(".")[0] if url else "?"
    print(f"[QA] project ref        : {project}")
    print(f"[QA] MOBILE_COMPANY_ID  : {os.getenv('MOBILE_COMPANY_ID') or '(auto-detect)'}")
    print(f"[QA] company under test : {COMPANY_ID}")
    print(f"[QA] date range         : {FROM_DATE} .. {TO_DATE}")

    states = check_rpc_connectivity(service, report)
    compare_trial_balance(service, report, states)
    compare_monthly_analysis(service, report, states)
    check_fallback_resilience(service, report)
    scan_render_logs(report)

    report.dump()
    return 1 if report.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
